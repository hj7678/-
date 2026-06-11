"""
Modbus TCP 驱动 — PLC 通信层

通过 Modbus TCP 协议读写 PLC 寄存器，实现与 IOBus 兼容的 read/write 接口。

用法:
    driver = ModbusDriver('192.168.1.100', 502)
    driver.connect()
    level = driver.read("bin.P1-5.level")     # → 读保持寄存器40001
    driver.write("hopper.hopper1.switch", True) # → 写线圈02001

依赖: pymodbus (pip install pymodbus)
"""

import struct
import time
from typing import Any, Dict, Optional

from io_bus import IODriver


# =============================================================================
# Tag → Modbus 地址映射表
#
# 格式: { tag: (区域, 地址, 数据类型, 量程系数) }
#
# 区域: 'coil'     = 读写位 (0x区)
#       'discrete' = 只读位 (1x区)
#       'holding'  = 读写16位寄存器 (4x区)
#
# 量程系数: PLC寄存器值 × 系数 = 物理值
#   例: 料位 40001=985 → 985 × 0.1 = 98.5%
# =============================================================================

TAG_MAP: Dict[str, tuple] = {
    # ── 皮带运行控制 (线圈 01xxx) ──
    'belt.E1.running':    ('coil', 1001),
    'belt.E2.running':    ('coil', 1002),
    'belt.E4.running':    ('coil', 1003),
    'belt.E5.running':    ('coil', 1004),
    'belt.E6.running':    ('coil', 1005),
    'belt.E7.running':    ('coil', 1006),
    'belt.E8.running':    ('coil', 1007),
    'belt.E9.running':    ('coil', 1008),
    'belt.E10.running':   ('coil', 1009),
    'belt.D1.running':    ('coil', 1010),
    'belt.D2.running':    ('coil', 1011),
    'belt.D3.running':    ('coil', 1012),
    'belt.D4.running':    ('coil', 1013),
    'belt.D5.running':    ('coil', 1014),
    'belt.D6.running':    ('coil', 1015),
    'belt.D7.running':    ('coil', 1016),
    'belt.D8.running':    ('coil', 1017),
    'belt.D9.running':    ('coil', 1018),
    'belt.D13.running':   ('coil', 1019),

    # ── 中转斗开关控制 (线圈 02xxx) ──
    'hopper.hopper1.switch': ('coil', 2001),
    'hopper.hopper2.switch': ('coil', 2002),
    'hopper.hopper3.switch': ('coil', 2003),
    'hopper.hopper4.switch': ('coil', 2004),
    'hopper.hopper5.switch': ('coil', 2005),
    'hopper.hopper6.switch': ('coil', 2006),
    'hopper.hopper7.switch': ('coil', 2007),

    # ── 接近开关状态 (离散输入 1xxxx, 只读) ──
    'sensor.S-E1.active':  ('discrete', 1001),
    'sensor.S-E2.active':  ('discrete', 1002),
    'sensor.S-E4.active':  ('discrete', 1003),
    'sensor.S-E5.active':  ('discrete', 1004),
    'sensor.S-E6.active':  ('discrete', 1005),
    'sensor.S-E7.active':  ('discrete', 1006),
    'sensor.S-E8.active':  ('discrete', 1007),
    'sensor.S-E9.active':  ('discrete', 1008),
    'sensor.S-E10.active': ('discrete', 1009),
    'sensor.S-D1.active':  ('discrete', 1010),
    'sensor.S-D2.active':  ('discrete', 1011),
    'sensor.S-D2-2.active':('discrete', 1012),
    'sensor.S-D3.active':  ('discrete', 1013),
    'sensor.S-D4.active':  ('discrete', 1014),
    'sensor.S-D5.active':  ('discrete', 1015),
    'sensor.S-D6.active':  ('discrete', 1016),
    'sensor.S-D7.active':  ('discrete', 1017),
    'sensor.S-D8.active':  ('discrete', 1018),
    'sensor.S-D9.active':  ('discrete', 1019),
    'sensor.S-D13.active': ('discrete', 1020),

    # ── P1~P4 料仓料位 (保持寄存器 4xxxx, 量程×0.1) ──
    # 40001-40028: P1-1~P1-7, P2-1~P2-7, P3-1~P3-7, P4-1~P4-7
    # 寄存器值 = 料位% × 10 (如 985 = 98.5%)

    # ── 中转斗称重 (保持寄存器 4xxxx, 量程×0.01吨) ──
    'hopper.hopper1.weight': ('holding', 40051, 'uint16', 0.01),
    'hopper.hopper2.weight': ('holding', 40052, 'uint16', 0.01),
    'hopper.hopper3.weight': ('holding', 40053, 'uint16', 0.01),
    'hopper.hopper4.weight': ('holding', 40054, 'uint16', 0.01),
    'hopper.hopper5.weight': ('holding', 40055, 'uint16', 0.01),
    'hopper.hopper6.weight': ('holding', 40056, 'uint16', 0.01),
    'hopper.hopper7.weight': ('holding', 40057, 'uint16', 0.01),

    # ── 小车传感器 (保持寄存器 4xxxx) ──
    'cart.Cart1.position':      ('holding', 40101, 'uint16', 1.0),
    'cart.Cart2.position':      ('holding', 40102, 'uint16', 1.0),
    'cart.Cart3.position':      ('holding', 40103, 'uint16', 1.0),
    'cart.Cart4.position':      ('holding', 40104, 'uint16', 1.0),
    'cart.Cart1.left_divert':   ('coil', 3001),
    'cart.Cart1.right_divert':  ('coil', 3002),
    'cart.Cart2.left_divert':   ('coil', 3003),
    'cart.Cart2.right_divert':  ('coil', 3004),
    'cart.Cart3.left_divert':   ('coil', 3005),
    'cart.Cart3.right_divert':  ('coil', 3006),
    'cart.Cart4.left_divert':   ('coil', 3007),
    'cart.Cart4.right_divert':  ('coil', 3008),

    # ── 激光传感器 (离散输入 1xxxx) ──
    'laser.feed1_1.has_material': ('discrete', 2001),
    'laser.feed1_2.has_material': ('discrete', 2002),
    'laser.feed2_1.has_material': ('discrete', 2003),
    'laser.feed2_2.has_material': ('discrete', 2004),
    'laser.feed3.has_material':   ('discrete', 2005),
}

# 料仓 tag 动态生成函数
def _bin_tag(bin_id: str, attr: str = 'level') -> str:
    return f"bin.{bin_id}.{attr}"

# P1-P4 × 7行 = 28个料仓
_BIN_IDS = []
for col in ['P1', 'P2', 'P3', 'P4']:
    for row in range(1, 8):
        _BIN_IDS.append(f"{col}-{row}")

# 自动分配料仓寄存器地址 40001-40028
for i, bin_id in enumerate(_BIN_IDS):
    TAG_MAP[_bin_tag(bin_id, 'level')] = ('holding', 40001 + i, 'uint16', 0.1)
    TAG_MAP[_bin_tag(bin_id, 'current')] = ('holding', 40101 + i, 'uint16', 0.01)  # 当前重量(吨)
    TAG_MAP[_bin_tag(bin_id, 'capacity')] = ('holding', 40201 + i, 'uint16', 0.01)  # 容量(吨)

# S1-S12 储料仓 40301-40312
for i in range(1, 13):
    sid = f"S{i}"
    TAG_MAP[_bin_tag(sid, 'level')] = ('holding', 40300 + i, 'uint16', 0.1)
    TAG_MAP[_bin_tag(sid, 'current')] = ('holding', 40400 + i, 'uint16', 0.01)
    TAG_MAP[_bin_tag(sid, 'capacity')] = ('holding', 40500 + i, 'uint16', 0.01)

# S1-1~S6-2 储料仓隔间（复用 S1-S12 的映射）
for s in range(1, 7):
    for r in range(1, 3):
        sid = f"S{s}-{r}"
        base_idx = (s - 1) * 2 + r
        TAG_MAP[_bin_tag(sid, 'level')] = ('holding', 40300 + base_idx, 'uint16', 0.1)


# =============================================================================
# Modbus 驱动
# =============================================================================

class ModbusDriver(IODriver):
    """Modbus TCP 驱动"""

    def __init__(self, host: str = '127.0.0.1', port: int = 502):
        self._host = host
        self._port = port
        self._client = None
        self._connected = False
        self._tag_map = dict(TAG_MAP)  # 允许运行时添加自定义映射

    def add_tag(self, tag: str, area: str, addr: int, dtype: str = 'uint16',
                scale: float = 1.0):
        """注册自定义 tag 映射"""
        self._tag_map[tag] = (area, addr, dtype, scale)

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        try:
            from pymodbus.client import ModbusTcpClient
            self._client = ModbusTcpClient(self._host, self._port, timeout=2)
            self._connected = self._client.connect()
        except ImportError:
            print("[Modbus] pymodbus 未安装，使用仿真回退模式")
            self._connected = False
        except Exception as e:
            print(f"[Modbus] 连接失败 {self._host}:{self._port}: {e}")
            self._connected = False
        return self._connected

    def disconnect(self):
        if self._client:
            self._client.close()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # IODriver 接口
    # ------------------------------------------------------------------

    def read(self, tag: str) -> Any:
        if not self._connected or tag not in self._tag_map:
            return None

        entry = self._tag_map[tag]
        area = entry[0]
        addr = entry[1]

        try:
            if area == 'coil':
                result = self._client.read_coils(addr, 1)
                return result.bits[0] if not result.isError() else None

            elif area == 'discrete':
                result = self._client.read_discrete_inputs(addr, 1)
                return result.bits[0] if not result.isError() else None

            elif area == 'holding':
                dtype = entry[2] if len(entry) > 2 else 'uint16'
                scale = entry[3] if len(entry) > 3 else 1.0
                result = self._client.read_holding_registers(addr, 1)
                if result.isError():
                    return None
                raw = result.registers[0]
                if dtype == 'int16' and raw >= 32768:
                    raw -= 65536  # 有符号
                return raw * scale

        except Exception as e:
            print(f"[Modbus] 读 {tag} 失败: {e}")
            return None

    def write(self, tag: str, value: Any):
        if not self._connected or tag not in self._tag_map:
            return

        entry = self._tag_map[tag]
        area = entry[0]
        addr = entry[1]

        try:
            if area == 'coil':
                self._client.write_coil(addr, bool(value))

            elif area == 'holding':
                dtype = entry[2] if len(entry) > 2 else 'uint16'
                scale = entry[3] if len(entry) > 3 else 1.0
                raw = int(value / scale)
                if dtype == 'int16' and raw < 0:
                    raw += 65536
                raw = max(0, min(65535, raw))
                self._client.write_register(addr, raw)

        except Exception as e:
            print(f"[Modbus] 写 {tag}={value} 失败: {e}")
