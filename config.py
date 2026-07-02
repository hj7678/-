"""
config.py - 配置文件 - 搅拌站上料系统仿真软件

注意: 布局坐标数据已移至 pos.py
本配置文件主要定义仿真参数和业务逻辑
"""

import os

# 获取项目根目录（config.py 的父目录）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
SENSOR_DATA_FILE = os.path.join(DATA_DIR, 'sensor_data.json')

# TCP 下位机通信配置
TCP_LOWER_HOST = '172.16.16.108'
TCP_LOWER_PORT = 8888
TCP_SEND_INTERVAL = 0.3  # 发送间隔 300ms

# UDP 下位机通信配置（二进制帧）
UDP_LOWER_HOST = '172.16.16.108'
UDP_LOWER_PORT = 8889
UDP_SEND_INTERVAL = 0.3  # 发送间隔 300ms

from enum import Enum
from typing import Dict, Tuple
import pos


class ConveyorState(Enum):
    """皮带状态"""
    STOPPED = 0
    RUNNING = 1
    FAULT = 2


class SensorState(Enum):
    """传感器状态"""
    OFF = 0
    ON = 1


# =============================================================================
# 仿真区域尺寸 - 从pos.py读取
# =============================================================================
SIMULATION_WIDTH = pos.CANVAS_WIDTH
SIMULATION_HEIGHT = pos.CANVAS_HEIGHT

# 仿真参数
DEFAULT_SPEED = 2.5
MIN_SPEED = 0.5
MAX_SPEED = 5.0
MATERIAL_SIZE = 10
MATERIAL_WEIGHT = 0.1  # 每个物料重量 0.1 t

# 配料站料仓容量（吨）
BATCHING_BIN_CAPACITY = 110.0  # 配料站小仓容量

# 高位储料仓料仓容量（吨）
HIGH_SILO_BIN_CAPACITY = 420.0  # 高位储料仓料仓容量

# 皮带进料速率（吨/秒）
FEED_RATE = 0.195  # 0.195 t/s

# =============================================================================
# 皮带配置 - 从pos.py读取
# =============================================================================
def _build_conveyors():
    """从pos.py构建皮带配置"""
    all_conv = pos.get_all_conveyors()
    result = {}
    for cid, c in all_conv.items():
        result[cid] = {
            'name': c.get('name', cid),
            'length': c.get('length', 20),
            'speed': c.get('speed', DEFAULT_SPEED),  # 使用 DEFAULT_SPEED 作为默认速度
            'pixel_length': _calc_pixel_length(c['start_pos'], c['end_pos']),
            'start_pos': c['start_pos'],
            'end_pos': c['end_pos'],
            'direction': c.get('direction', 'forward'),
            'color': '#FFFFFF',
            'type': c.get('type', 'NORMAL'),
        }
    return result

def _calc_pixel_length(p1, p2):
    """计算像素距离"""
    import math
    return int(math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2))

def _apply_external_overrides():
    """从 config.json 加载外部覆盖（透明地合并到 config_loader）"""
    try:
        from config_loader import get_config_loader
        loader = get_config_loader()
        loader.load()
        return loader
    except Exception:
        return None

_loader = _apply_external_overrides()

def _build_conveyors():
    """从pos.py构建皮带配置，config.json 中的 conveyors 节可覆盖 length/x/y"""
    all_conv = pos.get_all_conveyors()
    result = {}
    overrides = (_loader._overrides.get('conveyors', {}) if _loader else {})
    for cid, c in all_conv.items():
        ov = overrides.get(cid, {})
        result[cid] = {
            'name': c.get('name', cid),
            'length': ov.get('length', c.get('length', 20)),
            'speed': c.get('speed', DEFAULT_SPEED),
            'pixel_length': _calc_pixel_length(
                (ov.get('x1', c['start_pos'][0]), ov.get('y1', c['start_pos'][1])),
                (ov.get('x2', c['end_pos'][0]), ov.get('y2', c['end_pos'][1])),
            ),
            'start_pos': (ov.get('x1', c['start_pos'][0]), ov.get('y1', c['start_pos'][1])),
            'end_pos': (ov.get('x2', c['end_pos'][0]), ov.get('y2', c['end_pos'][1])),
            'direction': c.get('direction', 'forward'),
            'color': '#FFFFFF',
            'type': c.get('type', 'NORMAL'),
        }
    return result

CONVEYORS = _build_conveyors()

# =============================================================================
# 传感器配置 - 从pos.py读取，config.json 中的 sensors 节可覆盖 x/y/distance
# =============================================================================
def _build_sensors():
    """从pos.py构建传感器配置"""
    result = {}
    overrides = (_loader._overrides.get('sensors', {}) if _loader else {})
    for sid, s in pos.SENSORS.items():
        ov = overrides.get(sid, {})
        result[sid] = {
            'name': s['name'],
            'position': (ov.get('x', s['x']), ov.get('y', s['y'])),
            'conveyor': s.get('conveyor', sid),
            'distance_from_start': ov.get('distance_from_start', s.get('distance_from_start', 0)),
        }
    return result

SENSORS = _build_sensors()

# =============================================================================
# 中转斗配置 - 从pos.py读取（包含 input/output 皮带关联）
# =============================================================================
def _build_hoppers():
    """从pos.py构建中转斗配置，config.json 中的 hoppers 节可覆盖 x/y/width/height"""
    result = {}
    overrides = (_loader._overrides.get('hoppers', {}) if _loader else {})
    for hid, h in pos.TRANSFER_HOPPERS.items():
        ov = overrides.get(hid, {})
        result[hid] = {
            'name': h['name'],
            'position': (ov.get('x', h['x']), ov.get('y', h['y'])),
            'width': ov.get('width', h['width']),
            'height': ov.get('height', h['height']),
            'input_conveyor': h.get('input', []),
            'output_conveyor': h.get('output', ''),
            'capacity': 20,
        }
    return result

TRANSFER_HOPPERS = _build_hoppers()

# =============================================================================
# 上料点配置 - 从pos.py读取
# =============================================================================
def _build_feed_points():
    """从pos.py构建上料点配置"""
    result = {}
    for fid, f in pos.FEED_POINTS.items():
        result[fid] = {
            'name': f['name'],
            'position': (f['x'], f['y']),
            'output_conveyor': f.get('output'),
        }
    return result

FEED_POINTS = _build_feed_points()

# =============================================================================
# 高位配料站配置
# =============================================================================
BATCHING_STATION = {
    'name': pos.BATCHING_STATION['name'],
    'position': (pos.BATCHING_STATION['x'], pos.BATCHING_STATION['y']),
    'width': pos.BATCHING_STATION['width'],
    'height': pos.BATCHING_STATION['height'],
    'columns': pos.BATCHING_STATION['columns'],
    'rows': pos.BATCHING_STATION['rows'],
    'column_names': pos.BATCHING_STATION['col_names'],
    'compartments': {},
}

col_names = pos.BATCHING_STATION['col_names']

for col in range(BATCHING_STATION['columns']):
    for row in range(BATCHING_STATION['rows']):
        compartment_id = f"{col_names[col]}-{row + 1}"
        BATCHING_STATION['compartments'][compartment_id] = {
            'id': compartment_id,
            'column': col,
            'row': row,
            'capacity': BATCHING_BIN_CAPACITY,
            'current_level': 85,
        }

# =============================================================================
# 高位储料仓
# =============================================================================
HIGH_SILO = {
    'name': pos.HIGH_SILO['name'],
    'position': (pos.HIGH_SILO['x'], pos.HIGH_SILO['y']),
    'width': pos.HIGH_SILO['width'],
    'height': pos.HIGH_SILO['height'],
    'rows': pos.HIGH_SILO.get('rows', 2),
    'columns': pos.HIGH_SILO.get('columns', 6),
    'column_names': pos.HIGH_SILO.get('col_names', [f'S{i}' for i in range(1, 7)]),
    'compartments': {},
}

# 为每个小仓初始化数据（S1-S12，2行×6列）
for i in range(HIGH_SILO['rows']):
    for j in range(HIGH_SILO['columns']):
        comp_num = i * HIGH_SILO['columns'] + j + 1
        comp_id = f'S{comp_num}'
        HIGH_SILO['compartments'][comp_id] = {
            'id': comp_id,
            'row': i,
            'column': j,
            'capacity': HIGH_SILO_BIN_CAPACITY,
            'current_level': 85,
        }

# =============================================================================
# 激光测距仪传感器配置
# =============================================================================
# 激光传感器配置：检测上料点是否有原料
# 有料=True（传感器被遮挡），无料=False（传感器未遮挡）
def _build_laser_sensors():
    """从pos.py构建激光传感器配置"""
    result = {}
    for sid, s in pos.FEED_POINT_LASER_SENSORS.items():
        result[sid] = {
            'name': s['name'],
            'position': (s['x'], s['y']),
            'feed_point': s.get('feed_point', sid),  # 使用sid作为默认值
        }
    return result

LASER_SENSORS = _build_laser_sensors()

# =============================================================================
# 运料小车传感器配置
# =============================================================================
# 从pos.py读取运料小车传感器配置
def _build_cart_sensors():
    """从pos.py构建运料小车传感器配置"""
    result = {}
    for cart_id, cart_config in pos.CART_SENSORS.items():
        result[cart_id] = {
            'name': cart_config['name'],
            'conveyor': cart_config['conveyor'],
            'destination': cart_config['destination'],
            'position_sensor': cart_config['position_sensor'],
            'left_limit_sensor': cart_config['left_limit_sensor'],
            'right_limit_sensor': cart_config['right_limit_sensor'],
            'left_divert_sensor': cart_config['left_divert_sensor'],
            'right_divert_sensor': cart_config['right_divert_sensor'],
        }
    return result

CART_SENSORS = _build_cart_sensors()

# 小车位置范围
CART_POSITION_MIN = 1
CART_POSITION_MAX = 7

# 小车4位置范围（只有6个位置）
CART4_POSITION_MIN = 1
CART4_POSITION_MAX = 6

# 小车状态默认值
CART_DEFAULT_POSITION = 1
CART_DEFAULT_LEFT_LIMIT = False
CART_DEFAULT_RIGHT_LIMIT = False
CART_DEFAULT_LEFT_DIVERT = False
CART_DEFAULT_RIGHT_DIVERT = False

# =============================================================================
# 上料点激光传感器状态配置
# =============================================================================
# 默认状态：有原料（True=有料，False=无料）
FEED_POINT_LASER_STATES = {
    'feed1_1': True,   # 上料点1-1 有料
    'feed1_2': True,   # 上料点1-2 有料
    'feed2_1': True,   # 上料点2-1 有料
    # feed2_2: 三种物料
    'feed2_2_stone': True,   # 石粉
    'feed2_2_10mm': True,   # 10mm碎石
    'feed2_2_20mm': True,   # 20mm碎石
    # feed3: 两种物料
    'feed3_stone': True,   # 石粉
    'feed3_10mm': True,   # 10mm碎石
}

# =============================================================================
# 自动上料 —— 上料点优先级配置（服务于调度算法闭环控制）
# =============================================================================
# 上料点优先级（数字越小优先级越高）
FEED_POINT_PRIORITY = {
    'P1': {'feed2_1': 1, 'feed1_1': 2, 'feed1_2': 3},
    'P2': {'feed3': 1, 'silo_out': 2},
    'P3': {'feed3': 1, 'silo_out': 2},
    'P4': {'silo_out': 1, 'feed2_2': 2},
}

# 有激光传感器的上料点（silo_out 是储料仓，无激光传感器，默认为有料）
FEED_POINTS_WITH_LASER = ['feed1_1', 'feed1_2', 'feed2_1', 'feed2_2', 'feed3']

# feed3 优先供应 P2/P3 料仓（当 P2/P3 有调度任务时，P4 不使用 feed3）
FEED3_PRIORITY_BELTS = ['P2', 'P3']

# =============================================================================
# 高位储料仓料仓物料类型映射 - 从pos.py读取
# =============================================================================
SILO_BIN_MATERIALS = pos.SILO_BIN_MATERIALS.copy()

# =============================================================================
# 上料路线配置 - 从pos.py读取 (9条路线)
# =============================================================================
FEED_ROUTES = pos.FEED_ROUTES.copy()

# =============================================================================
# 小仓+上料点 -> 路线 反向映射
# 用于画布点击选择上料路线功能
# 注意：同一个上料点可能对应多个路线（如silo_out对应route8和route9）
# 因此使用列表形式 BIN_TO_AVAILABLE_ROUTES 来存储
# =============================================================================

# 简化版：直接从小仓获取可用路线列表
# 格式: {小仓ID: [(上料点, 路线ID), ...], ...}
def _build_bin_available_routes():
    """构建小仓到可用路线列表的映射"""
    result = {}

    # P1配料站 -> 路线①②③
    for row in range(1, 8):
        bin_id = f'P1-{row}'
        result[bin_id] = [
            ('feed1_1', 'route1'),
            ('feed1_2', 'route2'),
            ('feed2_1', 'route3'),
        ]

    # P4配料站 -> 路线④⑦ (D9皮带)
    for row in range(1, 8):
        bin_id = f'P4-{row}'
        result[bin_id] = [
            ('feed2_2', 'route4'),
            ('silo_out', 'route7'),
        ]

    # P2配料站 -> 路线⑥⑧ (D8皮带)
    for row in range(1, 8):
        bin_id = f'P2-{row}'
        result[bin_id] = [
            ('feed3', 'route6'),
            ('silo_out', 'route8'),
        ]

    # P3配料站 -> 路线⑥⑧ (D8皮带)
    for row in range(1, 8):
        bin_id = f'P3-{row}'
        result[bin_id] = [
            ('feed3', 'route6'),
            ('silo_out', 'route8'),
        ]

    # 高位储料仓 S1-S12 -> 路线⑤（仅补料）
    for i in range(1, 13):
        bin_id = f'S{i}'
        result[bin_id] = [('feed2_2', 'route5')]

    return result

# 小仓ID到可用路线列表的映射
BIN_TO_AVAILABLE_ROUTES = _build_bin_available_routes()

# =============================================================================
# 报警阈值
# =============================================================================
ALARM_THRESHOLDS = {
    'sensor_timeout': 10000,
    'batching_full': 95,   # 有中转斗的路线（高位配料站）：95%
    'silo_full': 88,       # 无中转斗的路线（高位储料仓）：88%
}

# =============================================================================
# 分料小车初始位置配置
# =============================================================================
# 小车启动时的默认位置设置（值为小仓行号1-7，或 'start' 表示皮带起点）
# 示例: 'D7': 3 表示D7皮带的1号小车初始停在P1-3位置
CART_INITIAL_POSITIONS = {
    'D7': 1,    # 石粉配料站 - 默认在第1行
    'D8': 1,    # P2/P3配料站 - 默认在第1行
    'D9': 1,    # 碎石配料站 - 默认在第1行
    'D6': 1,    # 高位储料仓小车4 - 默认在第1列
}

# =============================================================================
# 皮带故障配置
# =============================================================================
# 皮带状态: None=跟随仿真, 'normal'=正常启动, 'stopped'=关闭, 'speed_abnormal'=转速异常
CONVEYOR_STATES = {
    'E1': None, 'E2': None, 'E4': None, 'E5': None,
    'E6': None, 'E7': None, 'E8': None, 'E9': None, 'E10': None,
    'D1': None, 'D2': None, 'D3': None, 'D4': None,
    'D5': None, 'D6': None, 'D7': None, 'D8': None, 'D9': None, 'D13': None,
}
# 向后兼容的别名
CONVEYOR_FAULTS = CONVEYOR_STATES

# =============================================================================
# 皮带转速传感器配置
# =============================================================================
# 皮带ID -> 传感器ID 映射
CONVEYOR_SPEED_SENSORS = {
    'E1': 'S-CV-E1', 'E2': 'S-CV-E2', 'E4': 'S-CV-E4', 'E5': 'S-CV-E5',
    'E6': 'S-CV-E6', 'E7': 'S-CV-E7', 'E8': 'S-CV-E8', 'E9': 'S-CV-E9', 'E10': 'S-CV-E10',
    'D1': 'S-CV-D1', 'D2': 'S-CV-D2', 'D3': 'S-CV-D3', 'D4': 'S-CV-D4',
    'D5': 'S-CV-D5', 'D6': 'S-CV-D6', 'D7': 'S-CV-D7', 'D8': 'S-CV-D8', 'D9': 'S-CV-D9', 'D13': 'S-CV-D13',
}

# 转速正常范围阈值（sint类型，单位为0.01m/s，即数值100表示1m/s）
SPEED_NORMAL_MIN = 10   # 最小转速阈值，低于此值认为停止（0.1m/s = 10）
SPEED_NORMAL_RANGE = 50  # 正常转速波动范围（0.5m/s = 50）
SPEED_SCALE = 100        # 转速缩放因子（sint值 = 实际速度 * 100）

# 皮带转速传感器默认值配置
# 正常启动转速值（sint类型）
SPEED_NORMAL_VALUE = 500   # 正常运行时转速值
# 异常转速阈值，低于此值视为异常（sint类型）
SPEED_ABNORMAL_THRESHOLD = 450

# =============================================================================
# 日志配置
# =============================================================================
LOG_CONFIG = {
    'max_entries': 1000,
}

# =============================================================================
# 传感器配置
# =============================================================================
SENSOR_OFF_DELAY = 500

# =============================================================================
# 颜色定义
# =============================================================================
COLORS = {
    'background': '#0d1117',
    'panel': '#161b22',
    'panel_border': '#30363d',
    'conveyor': '#FFFFFF',
    'conveyor_running': '#00FF00',
    'conveyor_stopped': '#484F58',
    'conveyor_fault': '#E74C3C',
    'sensor_active': '#00FF00',
    'sensor_inactive': '#484F58',
    'material': '#F39C12',
    'hopper': '#8E44AD',
    'hopper_active': '#00FF00',
    'silo': '#16A085',
    'batching': '#E67E22',
    'batching_compartment': '#2C3E50',
    'text': '#E6EDF3',
    'text_secondary': '#8B949E',
    'warning': '#F39C12',
    'error': '#E74C3C',
    'success': '#00FF00',
    'feed_point': '#3498DB',
}
