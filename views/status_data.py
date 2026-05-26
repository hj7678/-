"""
状态监控数据契约模块

提供 StatusData 数据类和 collect_status_data 适配器函数，
使 StatusPanel 只依赖纯数据结构，不再直接依赖 SimulationController / config / sensor_data_manager。
"""
from dataclasses import dataclass, field
from typing import Any

import config
from sensor_data_manager import get_data_manager

# =============================================================================
# 静态配置常量（从 config 提取，StatusPanel 初始化所需）
# =============================================================================

CONVEYOR_IDS = list(config.CONVEYORS.keys())
SENSOR_IDS = list(config.SENSORS.keys())
HOPPER_IDS = list(config.TRANSFER_HOPPERS.keys())
LASER_SENSOR_IDS = list(config.LASER_SENSORS.keys())
CART_IDS = list(config.CART_SENSORS.keys())

# 完整配置字典，供 _create_*_cell 方法使用
TRANSFER_HOPPERS_CONFIG = config.TRANSFER_HOPPERS  # {hid: {name, position, ...}}
LASER_SENSORS_CONFIG = config.LASER_SENSORS         # {lid: {name, position, feed_point}}
CART_SENSORS_CONFIG = config.CART_SENSORS           # {cart_id: {name, destination, ...}}

# 上料点中文名称映射
FEED_POINT_DISPLAY_NAMES = {
    'feed1_1': '上料点1-1',
    'feed1_2': '上料点1-2',
    'feed2_1': '上料点2-1',
    'feed2_2': '上料点2-2',
    'feed3': '上料点3',
}

# 故障类别中文名
CATEGORY_CN = {
    'proximity': '接近开关',
    'hopper_switch': '中转斗开关',
    'hopper_weight': '中转斗称重',
    'cart': '小车传感器',
    'conveyor': '皮带转速',
    'cross_sensor': '跨传感器',
}


# =============================================================================
# StatusData 数据类
# =============================================================================

@dataclass
class StatusData:
    """StatusPanel 显示所需的全部数据"""

    # 皮带状态：{cid: {is_running, on_route, fault_type, raw_speed}}
    conveyors: dict[str, dict[str, Any]] = field(default_factory=dict)

    # 传感器状态：{sid: bool}
    sensors: dict[str, bool] = field(default_factory=dict)

    # 故障传感器ID集合
    faulty_sensors: set[str] = field(default_factory=set)

    # 中转斗：{hid: {level_percent, switch_open, weight}}
    hoppers: dict[str, dict[str, Any]] = field(default_factory=dict)

    # 小车传感器：{cart_id: {position, left_limit, right_limit, left_divert, right_divert}}
    cart_sensors: dict[str, dict[str, Any]] = field(default_factory=dict)

    # 激光传感器：{lid: bool}
    laser_sensors: dict[str, bool] = field(default_factory=dict)

    # 料位传感器：{bin_id: level_percent}
    level_sensors: dict[str, float] = field(default_factory=dict)

    # 调度结果
    schedules: dict[str, Any] = field(default_factory=dict)
    executing_bins: dict[str, str] = field(default_factory=dict)

    # 诊断结果
    diagnosis_faults: list[Any] = field(default_factory=list)
    full_diagnosis_results: list[Any] = field(default_factory=list)

    # 统计
    total_runtime: float = 0.0
    total_feed_weight: float = 0.0
    alarm_count: int = 0
    active_routes: list[str] = field(default_factory=list)


# =============================================================================
# 适配器函数
# =============================================================================

def collect_status_data(simulator) -> StatusData:
    """从 SimulationController 提取显示所需数据，填充 StatusData"""

    data_manager = get_data_manager()

    # 皮带状态
    conveyors = {}
    for cid in CONVEYOR_IDS:
        state = simulator.get_conveyor_state(cid)
        conveyors[cid] = {
            'is_running': state['is_running'],
            'on_route': state['on_route'],
            'fault_type': state.get('fault_type'),
            'raw_speed': state.get('raw_speed', 0),
        }

    # 传感器状态
    sensors = {}
    for sid in SENSOR_IDS:
        sensors[sid] = simulator.get_sensor_state(sid)

    # 故障传感器
    faulty_sensors = simulator.get_faulty_sensors() if hasattr(simulator, 'get_faulty_sensors') else set()

    # 中转斗数据（从 generate_data.json 实时读取开关和称重）
    hopper_json = data_manager.read_all_hopper_data()
    hoppers = {}
    for hid in HOPPER_IDS:
        level = simulator.get_hopper_level(hid)
        switch_data = hopper_json.get(hid, {})
        switch_open = switch_data.get('switch', True)
        weight_kg = switch_data.get('weight', 0)
        weight_tons = weight_kg / 1000.0
        hoppers[hid] = {
            'level_percent': level,
            'switch_open': switch_open,
            'weight': weight_tons,
        }

    # 小车传感器（从 generate_data.json 实时读取）
    cart_json = data_manager.read_cart_sensors()
    cart_sensors = {}
    for cart_id in CART_IDS:
        info = cart_json.get(cart_id, {})
        cart_sensors[cart_id] = {
            'position': info.get('position', 1),
            'left_limit': info.get('left_limit', False),
            'right_limit': info.get('right_limit', False),
            'left_divert': info.get('left_divert', False),
            'right_divert': info.get('right_divert', False),
        }

    # 激光传感器
    laser_sensors = {}
    for lid in LASER_SENSOR_IDS:
        laser_sensors[lid] = simulator.get_laser_sensor_state(lid) if hasattr(simulator, 'get_laser_sensor_state') else False

    # 料位传感器
    level_sensors = simulator.get_all_level_sensors() if hasattr(simulator, 'get_all_level_sensors') else {}

    # 调度
    schedules = simulator.get_latest_schedules() if hasattr(simulator, 'get_latest_schedules') else {}
    executing_bins = simulator._executing_bin if hasattr(simulator, '_executing_bin') else {}

    # 诊断
    diagnosis_faults = simulator.get_diagnosis_result() if hasattr(simulator, 'get_diagnosis_result') else []
    full_results = simulator.get_full_diagnosis_results() if hasattr(simulator, 'get_full_diagnosis_results') else []

    # 统计
    status = simulator.get_status()

    return StatusData(
        conveyors=conveyors,
        sensors=sensors,
        faulty_sensors=faulty_sensors,
        hoppers=hoppers,
        cart_sensors=cart_sensors,
        laser_sensors=laser_sensors,
        level_sensors=level_sensors,
        schedules=schedules,
        executing_bins=executing_bins,
        diagnosis_faults=diagnosis_faults,
        full_diagnosis_results=full_results,
        total_runtime=status['total_runtime'],
        total_feed_weight=status.get('total_feed_weight', 0.0),
        alarm_count=status['alarm_count'],
        active_routes=status.get('active_routes', []),
    )
