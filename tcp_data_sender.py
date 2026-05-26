"""
TCP 数据发送器 - 将传感器数据发送到下位机
所有阻塞 I/O 操作（TCP 连接/发送、文件写入）运行在独立工作线程，不阻塞 UI。
"""
import json
import os
import socket
import time
from typing import Any, Dict, Optional

from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal, QMutex, QMutexLocker

import config


class TcpWorker(QObject):
    """工作线程：处理 TCP 连接、数据发送和文件写入"""

    connection_changed = pyqtSignal(bool)
    send_error = pyqtSignal(str)

    def __init__(self, host: str, port: int, interval_ms: int):
        super().__init__()
        self.host = host
        self.port = port
        self.interval_ms = interval_ms

        self._socket: Optional[socket.socket] = None
        self._connected = False
        self._data: Dict[str, Any] = {}
        self._mutex = QMutex()
        self._reconnect_backoff = 0
        self._timer: Optional[QTimer] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def update_data(self, data: Dict[str, Any]):
        """从主线程更新数据（线程安全）"""
        with QMutexLocker(self._mutex):
            self._data = data

    def start_work(self):
        """在工作线程启动（由 QThread.started 信号触发）"""
        self._timer = QTimer()
        self._timer.timeout.connect(self._on_tick)
        self._timer.setInterval(self.interval_ms)
        self._try_connect()
        self._timer.start()

    def stop_work(self):
        """停止工作"""
        if self._timer:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        self._disconnect()

    def _on_tick(self):
        """定时回调：写文件 + 尝试 TCP 发送"""
        self._save_to_file()

        if self._connected:
            self._send()
        elif self._reconnect_backoff <= 0:
            self._try_connect()
            self._reconnect_backoff = 10  # 每 10 个 tick 重试一次（3 秒）
        else:
            self._reconnect_backoff -= 1

    def _get_data(self) -> Dict[str, Any]:
        with QMutexLocker(self._mutex):
            return dict(self._data)

    def _prepare_json(self, indent=None) -> str:
        data = self._get_data()
        payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sensors": data.get("sensors", {}),
            "hoppers": data.get("hoppers", {}),
            "conveyor_sensors": data.get("conveyor_sensors", {}),
            "cart_sensors": data.get("cart_sensors", {}),
        }
        return json.dumps(payload, ensure_ascii=False, indent=indent)

    def _save_to_file(self):
        """保存数据到 data/to_lower.json（在工作线程执行）"""
        try:
            json_str = self._prepare_json(indent=2)
        except (TypeError, ValueError):
            return

        try:
            os.makedirs(config.DATA_DIR, exist_ok=True)
            filepath = os.path.join(config.DATA_DIR, "to_lower.json")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(json_str)
        except OSError:
            pass

    def _send(self):
        """发送 JSON 数据到下位机"""
        try:
            json_str = self._prepare_json()
        except (TypeError, ValueError):
            return

        try:
            self._socket.sendall((json_str + "\n").encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            self._connected = False
            self._disconnect()
            self.send_error.emit(str(e))
            self.connection_changed.emit(False)

    def _try_connect(self):
        """尝试连接下位机（工作线程上阻塞 1 秒）"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            sock.connect((self.host, self.port))
            sock.settimeout(None)
            self._socket = sock
            self._connected = True
            self._reconnect_backoff = 0
            self.connection_changed.emit(True)
        except (ConnectionRefusedError, socket.timeout, OSError):
            self._connected = False
            self._socket = None

    def _disconnect(self):
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        self._connected = False


class TcpDataSender(QObject):
    """TCP 数据发送器（主线程 facade，内部使用工作线程）"""

    connection_changed = pyqtSignal(bool)
    send_error = pyqtSignal(str)

    def __init__(self, host: str = None, port: int = None, interval: float = None):
        super().__init__()
        self.host = host or config.TCP_LOWER_HOST
        self.port = port or config.TCP_LOWER_PORT
        self.interval_ms = int((interval or config.TCP_SEND_INTERVAL) * 1000)

        self._worker: Optional[TcpWorker] = None
        self._thread: Optional[QThread] = None
        self._connected = False
        self._active = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def update_data(self, data: Dict[str, Any]):
        """更新待发送数据（线程安全）"""
        if self._worker:
            self._worker.update_data(data)

    def start(self):
        """启动 TCP 通信"""
        if self._active:
            return
        self._active = True

        self._thread = QThread()
        self._worker = TcpWorker(self.host, self.port, self.interval_ms)
        self._worker.moveToThread(self._thread)

        self._worker.connection_changed.connect(self._on_connection_changed)
        self._worker.send_error.connect(self._on_send_error)
        self._thread.started.connect(self._worker.start_work)
        self._thread.start()

    def stop(self):
        """停止 TCP 通信"""
        self._active = False
        self._connected = False

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
        self._connected = connected
        self.connection_changed.emit(connected)

    def _on_send_error(self, msg: str):
        self.send_error.emit(msg)
