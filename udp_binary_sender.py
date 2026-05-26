"""
UDP 二进制帧发送器 - 将传感器数据编排为紧凑二进制帧通过 UDP 发送到下位机
所有阻塞 I/O 操作运行在独立工作线程，不阻塞 UI。
帧格式详见 CLAUDE.md 或计划文档。
"""
import socket
import struct
import time
from typing import Dict, Any, Optional, List

from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal

import config


_CONVEYOR_SPEED_IDS = [
    'S-CV-E1', 'S-CV-E2', 'S-CV-E4', 'S-CV-E5', 'S-CV-E6',
    'S-CV-E7', 'S-CV-E8', 'S-CV-E9', 'S-CV-E10',
    'S-CV-D1', 'S-CV-D2', 'S-CV-D3', 'S-CV-D4', 'S-CV-D5',
    'S-CV-D6', 'S-CV-D7', 'S-CV-D8', 'S-CV-D9', 'S-CV-D13',
]

_FRAME_SIZE = 57
_FRAME_MAGIC = 0xA55A
_FRAME_VERSION = 0x01


def _set_bit(buf: bytearray, byte_offset: int, bit: int, value: bool):
    """将 bool 值写入指定位（bit 0 = LSB）"""
    if value:
        buf[byte_offset] |= (1 << bit)
    else:
        buf[byte_offset] &= ~(1 << bit)


def _calc_crc16(data: bytes) -> int:
    """CRC16-IBM (0xA001) 简易校验"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


class UdpBinaryWorker(QObject):
    """工作线程：定时构建二进制帧并通过 UDP 发送"""

    connection_changed = pyqtSignal(bool)
    send_error = pyqtSignal(str)

    def __init__(self, host: str, port: int, interval_ms: int):
        super().__init__()
        self.host = host
        self.port = port
        self.interval_ms = interval_ms

        self._socket: Optional[socket.socket] = None
        self._timer: Optional[QTimer] = None
        self._seq_number = 0
        self._started = False

    def start_work(self):
        """在工作线程启动（由 QThread.started 触发）"""
        self._try_open_socket()
        self._seq_number = 0
        self._started = True

        self._timer = QTimer()
        self._timer.timeout.connect(self._on_tick)
        self._timer.setInterval(self.interval_ms)
        self._timer.start()

    def stop_work(self):
        """停止工作"""
        self._started = False
        if self._timer:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def _try_open_socket(self):
        """创建 UDP socket"""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.connection_changed.emit(True)
        except OSError as e:
            self._socket = None
            self.send_error.emit(str(e))
            self.connection_changed.emit(False)

    def _on_tick(self):
        """定时回调：构建帧 → UDP sendto"""
        if not self._socket or not self._started:
            return

        try:
            frame = self._build_frame()
            self._socket.sendto(frame, (self.host, self.port))
        except OSError as e:
            self.send_error.emit(str(e))

    def _build_frame(self) -> bytes:
        """从 data_manager 读取实时数据，编排为 57 字节帧"""
        buf = bytearray(_FRAME_SIZE)

        # --- 帧头 (0-1): uint16 大端 ---
        struct.pack_into('>H', buf, 0, _FRAME_MAGIC)

        # --- 版本号 (2) ---
        buf[2] = _FRAME_VERSION

        # --- 帧序号 (3) ---
        buf[3] = self._seq_number & 0xFF
        self._seq_number = (self._seq_number + 1) & 0xFF

        # --- 时间戳 (4-7): uint32 大端 Unix 秒 ---
        struct.pack_into('>I', buf, 4, int(time.time()))

        # --- 布尔量位域 (8-13): 43 位 ---
        self._pack_bool_fields(buf)

        # --- 皮带转速 (14-32): sint8 × 19 ---
        self._pack_conveyor_speeds(buf)

        # --- 中转斗称重 (33-46): uint16 × 7 大端 ---
        self._pack_hopper_weights(buf)

        # --- 小车位置 (47-50): uint8 × 4 ---
        self._pack_cart_positions(buf)

        # --- 保留 (51-54): 全 0 ---
        for i in range(51, 55):
            buf[i] = 0

        # --- CRC16 (55-56) ---
        crc = _calc_crc16(bytes(buf[:55]))
        struct.pack_into('>H', buf, 55, crc)

        return bytes(buf)

    def _pack_bool_fields(self, buf: bytearray):
        """填充布尔量位域（43 位，偏移 8~13）"""
        from sensor_data_manager import get_data_manager
        dm = get_data_manager()

        sensors = dm.read_all_sensors()
        hoppers = dm.read_all_hopper_data()
        carts = dm.read_cart_sensors()

        # 接近开关 (20个): 偏移8 bit0 ~ 偏移10 bit3
        sensor_ids = list(config.SENSORS.keys())
        for i, sid in enumerate(sensor_ids):
            byte_off = 8 + (i // 8)
            bit = i % 8
            _set_bit(buf, byte_off, bit, bool(sensors.get(sid, False)))

        # 中转斗开关 (7个): 偏移10 bit4 ~ 偏移11 bit2
        hopper_ids = ['hopper1', 'hopper2', 'hopper3', 'hopper4',
                       'hopper5', 'hopper6', 'hopper7']
        base_bit = 20  # 前20个接近开关
        for i, hid in enumerate(hopper_ids):
            bit_idx = base_bit + i
            byte_off = 8 + (bit_idx // 8)
            bit = bit_idx % 8
            switch_val = bool(hoppers.get(hid, {}).get('switch', False))
            _set_bit(buf, byte_off, bit, switch_val)

        # 小车限位/分料 (16个): 偏移11 bit3 ~ 偏移13 bit2
        cart_ids = ['Cart1', 'Cart2', 'Cart3', 'Cart4']
        cart_fields = ['left_limit', 'right_limit', 'left_divert', 'right_divert']
        base_bit = 27  # 前20个接近开关 + 7个中转斗开关
        idx = 0
        for cart_id in cart_ids:
            cart_data = carts.get(cart_id, {})
            for field in cart_fields:
                bit_idx = base_bit + idx
                byte_off = 8 + (bit_idx // 8)
                bit = bit_idx % 8
                _set_bit(buf, byte_off, bit, bool(cart_data.get(field, False)))
                idx += 1

    def _pack_conveyor_speeds(self, buf: bytearray):
        """填充皮带转速 (偏移 14~32, sint8 × 19)"""
        from sensor_data_manager import get_data_manager
        dm = get_data_manager()
        speeds = dm.read_conveyor_speeds()

        for i, sid in enumerate(_CONVEYOR_SPEED_IDS):
            raw = speeds.get(sid, 0)
            # sint8 范围 -128~127，钳制
            val = max(-128, min(127, int(raw)))
            buf[14 + i] = val & 0xFF

    def _pack_hopper_weights(self, buf: bytearray):
        """填充中转斗称重 (偏移 33~46, uint16 × 7 大端)"""
        from sensor_data_manager import get_data_manager
        dm = get_data_manager()
        hoppers = dm.read_all_hopper_data()

        hopper_ids = ['hopper1', 'hopper2', 'hopper3', 'hopper4',
                       'hopper5', 'hopper6', 'hopper7']
        for i, hid in enumerate(hopper_ids):
            weight = hoppers.get(hid, {}).get('weight', 0)
            val = max(0, min(65535, int(weight)))
            struct.pack_into('>H', buf, 33 + i * 2, val)

    def _pack_cart_positions(self, buf: bytearray):
        """填充小车位置 (偏移 47~50, uint8 × 4)"""
        from sensor_data_manager import get_data_manager
        dm = get_data_manager()
        carts = dm.read_cart_sensors()

        cart_ids = ['Cart1', 'Cart2', 'Cart3', 'Cart4']
        for i, cart_id in enumerate(cart_ids):
            pos = carts.get(cart_id, {}).get('position', 1)
            val = max(0, min(255, int(pos)))
            buf[47 + i] = val


class UdpBinarySender(QObject):
    """UDP 二进制帧发送器（主线程 facade，内部使用工作线程）"""

    connection_changed = pyqtSignal(bool)
    send_error = pyqtSignal(str)

    def __init__(self, host: str = None, port: int = None, interval: float = None):
        super().__init__()
        self.host = host or config.UDP_LOWER_HOST
        self.port = port or config.UDP_LOWER_PORT
        self.interval_ms = int((interval or config.UDP_SEND_INTERVAL) * 1000)

        self._worker: Optional[UdpBinaryWorker] = None
        self._thread: Optional[QThread] = None
        self._active = False

    def start(self):
        """启动 UDP 发送"""
        if self._active:
            return
        self._active = True

        self._thread = QThread()
        self._worker = UdpBinaryWorker(self.host, self.port, self.interval_ms)
        self._worker.moveToThread(self._thread)

        self._worker.connection_changed.connect(self._on_connection_changed)
        self._worker.send_error.connect(self._on_send_error)
        self._thread.started.connect(self._worker.start_work)
        self._thread.start()

    def stop(self):
        """停止 UDP 发送"""
        self._active = False

        if self._worker:
            self._worker.stop_work()
            self._worker.deleteLater()
            self._worker = None

        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread.deleteLater()
            self._thread = None

    def _on_connection_changed(self, connected: bool):
        self.connection_changed.emit(connected)

    def _on_send_error(self, msg: str):
        self.send_error.emit(msg)
