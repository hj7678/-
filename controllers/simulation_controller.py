"""
仿真控制器 - Simulation Controller
核心仿真逻辑控制器

支持:
- 19条皮带
- 18个接近开关传感器
- 7个中转斗
- 5个上料点
- 9条上料路线
- 28仓高位配料站

物料流向:
- 物料从各上料点/储料仓出发
- 经过皮带的直线运动
- 到达中转斗时短暂停留后转移到下一皮带
- 最终到达高位配料站

故障模拟:
- 传感器故障诊断系统
- 可模拟传感器卡在低电平或随机值
- 自动检测路线上的传感器故障
"""

import math
import random
import sys
import traceback
from typing import Dict, List, Optional, Set, Tuple
from PyQt5.QtCore import QObject, QTimer, QElapsedTimer, pyqtSignal
import config
import pos
from models.material import Material, MaterialFactory, MaterialType
from sensor_fault_diagnosis import SensorFaultDiagnosis, FaultMode
from sensor_data_manager import SensorDataManager, get_data_manager
from sensor_data_generator import SensorDataGenerator, get_data_generator
from controllers.route_state_manager import RouteState, get_route_state_manager, RouteStateManager
from control_strategy_generator import ControlStrategyGenerator, get_control_strategy_generator
from tcp_data_sender import TcpDataSender
from udp_binary_sender import UdpBinarySender
from fault_diagnosis import DiagnosisEngine
from controllers.fault_diagnosis_adapter import FaultDiagnosisAdapter
from controllers.tcp_diagnosis_client import TcpDiagnosisClient
from controllers.tcp_scheduling_client import TcpSchedulingClient
from scheduling.bin_config import BELT_BINS
from scheduling.config import SILO_MAX_CAP


class Conveyor:
    """皮带模型
    
    每条皮带使用自己的像素/米比例来计算速度，确保物料以真实的速度移动。
    """

    def __init__(self, conv_id: str, conv_config: dict):
        self.id = conv_id
        self.name = conv_config['name']
        self.length = conv_config['length']  # 米
        self.pixel_length = conv_config['pixel_length']  # 像素
        self.start_pos = conv_config['start_pos']
        self.end_pos = conv_config['end_pos']
        self.direction = conv_config.get('direction', 'forward')
        self.color = conv_config.get('color', '#FFFFFF')

        # 当前速度（像素/秒）
        self.current_speed_pps = 0
        self.is_running = False
        self.materials_on_belt: List[Material] = []

    @property
    def current_speed(self) -> float:
        return self.current_speed_pps

    @property
    def is_vertical(self) -> bool:
        return self.start_pos[0] == self.end_pos[0]

    def start(self, speed_mps: float):
        """启动皮带

        Args:
            speed_mps: 速度（米/秒）
        """
        meter_to_pixel = self.pixel_length / self.length if self.length > 0 else 1
        self.current_speed_pps = speed_mps * meter_to_pixel
        self.is_running = True

    def stop(self):
        """停止皮带"""
        self.is_running = False
        self.current_speed_pps = 0

    def get_position_at_distance(self, pixel_distance: float) -> tuple:
        """根据像素距离获取位置"""
        if self.pixel_length == 0:
            return self.start_pos

        t = min(pixel_distance / self.pixel_length, 1.0)
        x = self.start_pos[0] + (self.end_pos[0] - self.start_pos[0]) * t
        y = self.start_pos[1] + (self.end_pos[1] - self.start_pos[1]) * t
        return (x, y)

    def get_cart_stop_position(self, bin_id: str) -> tuple:
        """根据目标小仓获取小车停靠位置（像素）"""
        # 解析 bin_id (如 "P1-3" -> row=2)
        parts = bin_id.split('-')
        if len(parts) != 2:
            return self.end_pos

        row_num = int(parts[1]) - 1  # 1-7 -> 0-6

        # 计算皮带上每个小仓对应的距离
        # P1-1 对应皮带终点（顶部），P1-7 对应皮带起点（底部）
        conveyor_height = abs(self.end_pos[1] - self.start_pos[1])
        segment_height = conveyor_height / 7

        # 计算Y坐标
        target_y = self.end_pos[1] + row_num * segment_height

        return (self.end_pos[0], target_y)

    def get_distance_for_bin(self, bin_id: str) -> float:
        """根据目标小仓获取物料需要停止的像素距离"""
        parts = bin_id.split('-')
        if len(parts) == 2:
            row_num = int(parts[1]) - 1  # 1-7 -> 0-6

            conveyor_height = abs(self.end_pos[1] - self.start_pos[1])
            segment_height = conveyor_height / 7
            stop_y = self.end_pos[1] + row_num * segment_height

            # 计算从起点到停止点的像素距离
            dx = self.end_pos[0] - self.start_pos[0]
            dy = stop_y - self.start_pos[1]
            return math.sqrt(dx * dx + dy * dy)

        # 高位储料仓格式：S1-S12，D6皮带上需要根据小车位置计算停止距离
        if bin_id.startswith('S') and bin_id[1:].isdigit():
            # 这需要在SimulationController中获取小车4位置
            # 这里返回估算值，实际距离在_check_material_at_cart4_position中计算
            return self.pixel_length

        return self.pixel_length


class Sensor:
    """接近开关传感器模型"""

    def __init__(self, sensor_id: str, sensor_config: dict):
        self.sensor_id = sensor_id
        self.name = sensor_config['name']
        # 支持 position 或 x/y 两种格式
        if 'position' in sensor_config:
            self.position = sensor_config['position']
        else:
            self.position = (sensor_config['x'], sensor_config['y'])
        self.conveyor = sensor_config['conveyor']
        self.distance_from_start = sensor_config.get('distance_from_start', 0)

        self.is_active = False  # 展示给UI的状态（可能受故障模拟影响）
        self.real_state = False  # 真实的物理状态
        self.trigger_count = 0
        self.last_trigger_time = 0
        self.hold_timer = 0  # 传感器保持时间(ms)

    def trigger(self, time_ms: int):
        """触发传感器"""
        if not self.real_state:
            self.real_state = True
            self.trigger_count += 1
            self.last_trigger_time = time_ms
            self.hold_timer = 200  # 保持200ms

    def update(self, delta_time: int):
        """更新传感器状态（延迟释放）"""
        if self.hold_timer > 0:
            self.hold_timer -= delta_time
            if self.hold_timer <= 0:
                self.hold_timer = 0
                self.real_state = False

    def release(self):
        """释放传感器"""
        self.real_state = False
        self.hold_timer = 0


class TransferHopper:
    """中转斗模型"""

    def __init__(self, hopper_id: str, hopper_config: dict):
        self.id = hopper_id
        self.hopper_id = hopper_id  # 别名，用于匹配route_hoppers配置
        self.name = hopper_config['name']
        self.position = hopper_config['position']
        self.width = hopper_config['width']
        self.height = hopper_config['height']
        self.input_conveyor = hopper_config['input_conveyor']  # 可输入的皮带列表
        self.output_conveyor = hopper_config['output_conveyor']  # 输出皮带

        # 容量配置（吨）：8500kg
        self.capacity_tons = 8.5
        self.current_weight = 0.0  # 当前重量（吨）
        self.fill_rate = 0.195  # 进料速率 t/s

        # 斗开关状态：
        # - is_open: 用户手动设置的开关状态（UI显示用）
        # - switch_fault_mode: 故障模式（实际作用于上料过程，对UI不可见）
        # 实际生效状态 = 故障模式? (故障状态) : (手动设置)
        self.is_open = True  # 用户手动设置的开关状态
        self._manual_switch_state = True  # 记录用户手动设置的开关状态

        # 称重传感器值
        self.weight = 0.0

        # 清空阶段计算出的余料重量（吨）
        # 当开关关闭时，用于显示皮带上剩余物料的重量
        self.residual_weight = 0.0

        self.is_active = False

        # 故障相关属性
        self.switch_fault_mode = None
        self.weight_fault_mode = None
        self.weight_offset = 0.0
        self.belt_speed_multiplier = 1.0

        # 斗内暂存的物料列表（当开关卡住时使用）
        self.stored_materials = []  # [{'material': Material, 'arrival_time': float}, ...]

    @property
    def stored_count(self) -> int:
        """存储的物料数量"""
        return len(self.stored_materials)
    def capacity(self) -> float:
        """兼容旧代码，返回整数容量"""
        return int(self.capacity_tons)

    @property
    def current_level(self) -> float:
        """兼容旧代码，返回整数料位"""
        return int(self.current_weight)

    @property
    def level_percent(self) -> float:
        return (self.current_weight / self.capacity_tons) * 100

    @property
    def is_full(self) -> bool:
        return self.current_weight >= self.capacity_tons

    def get_display_weight(self) -> float:
        """获取显示用的称重值

        逻辑：
        - 开关打开时（正常补料）：返回 stored_materials 数量对应的重量
        - 开关关闭时（清空余料）：返回当前存储的物料重量
        - 考虑故障模式的影响
        """
        if self.weight_fault_mode == 'stuck_zero':
            return 0.0

        # 基于存储的物料数量计算重量
        # 每个物料 0.1t
        stored_weight = len(self.stored_materials) * config.MATERIAL_WEIGHT

        if self.weight_fault_mode == 'offset':
            import random
            effective_weight = stored_weight * random.uniform(0.8, 1.2) + self.weight_offset
            return effective_weight
        return stored_weight

    def add_stored_weight(self, weight_tons: float):
        """增加存储的物料重量"""
        self.residual_weight += weight_tons

    def subtract_stored_weight(self, weight_tons: float):
        """减少存储的物料重量"""
        self.residual_weight = max(0, self.residual_weight - weight_tons)

    def get_stored_material_count(self) -> int:
        """获取存储的物料数量"""
        return len(self.stored_materials)

    def get_current_weight(self) -> float:
        """获取当前重量（吨）"""
        return self.current_weight

    def get_effective_switch_state(self) -> bool:
        """
        获取实际生效的开关状态（实际作用于上料过程）
        优先级：故障模式 > 用户手动设置
        """
        # 故障模式决定实际状态
        if self.switch_fault_mode == 'stuck_closed':
            return False  # 卡在关
        elif self.switch_fault_mode == 'stuck_open':
            return True   # 卡在开
        # 无故障时，使用用户手动设置的状态
        return self.is_open

    def get_display_switch_state(self) -> bool:
        """
        获取显示用的开关状态（用于UI显示）
        返回用户手动设置的状态，而不是故障后的状态
        """
        return self.is_open

    def store_material(self, material: Material, current_time: float):
        """物料进入斗中存储（当开关关闭时）"""
        self.stored_materials.append({
            'material': material,
            'arrival_time': current_time
        })
        # 累加到余料重量（用于显示）
        self.residual_weight += config.MATERIAL_WEIGHT
        self.current_weight = len(self.stored_materials) * config.MATERIAL_WEIGHT
        self.weight = self.current_weight
        self.is_active = True

    def can_release_material(self) -> bool:
        """检查是否可以释放物料"""
        if not self.get_effective_switch_state():
            return False  # 开关关着，不能释放
        if self.current_weight <= 0 and len(self.stored_materials) == 0:
            return False
        return True

    def release_material(self) -> Optional[Material]:
        """释放一个物料到下一皮带"""
        if not self.can_release_material():
            return None
        if len(self.stored_materials) == 0:
            return None

        stored = self.stored_materials.pop(0)
        material = stored['material']
        # 减少重量
        self.current_weight -= config.MATERIAL_WEIGHT
        self.current_weight = max(self.current_weight, 0)
        # 同步更新 residual_weight
        self.residual_weight = self.current_weight
        self.weight = self.current_weight
        return material

    def receive_material_direct(self):
        """物料直通通过（开关开着时）"""
        self.is_active = True

    def calculate_residual_weight(self, conveyors: dict, route_hoppers: list, route_conveyors: list, route_id: str = None) -> float:
        """计算该中转斗在CLEARING状态下的余料称重

        Args:
            conveyors: 皮带字典 {conv_id: Conveyor对象}
            route_hoppers: 路线的所有中转斗列表，如 [None, 'hopper1', 'hopper3', 'hopper4', None]
            route_conveyors: 路线的所有皮带列表，如 ['E5', 'E8', 'E10', 'D7']
            route_id: 路线ID，用于从 CLEARING_ROUTE_CONVEYORS 获取皮带对应关系

        Returns:
            余料重量（吨）

        规则：
        - 如果 CLEARING_ROUTE_CONVEYORS 中有该(中转斗,路线)组合的配置，累加所有皮带
        - 否则使用原来的逻辑：只计算当前中转斗对应的一段皮带
        """
        import pos
        hopper_id = self.hopper_id

        # 尝试从 CLEARING_ROUTE_CONVEYORS 获取多皮带配置（仅清空余料模式）
        if route_id:
            key = (hopper_id, route_id)
            conveyor_ids = pos.CLEARING_ROUTE_CONVEYORS.get(key)
            if conveyor_ids:
                total_weight = 0.0
                for conv_id in conveyor_ids:
                    conv = conveyors.get(conv_id)
                    if conv and hasattr(conv, 'length'):
                        material_count = (conv.length / 2.5) * 2
                        total_weight += material_count * 0.1
                return total_weight

        # 回退：使用原来的单皮带逻辑
        if hopper_id not in route_hoppers:
            return 0.0

        hopper_idx = route_hoppers.index(hopper_id)

        if hopper_idx < len(route_conveyors):
            conv_id = route_conveyors[hopper_idx]
            conv = conveyors.get(conv_id)
            if conv and hasattr(conv, 'length'):
                total_length = conv.length
                material_count = (total_length / 2.5) * 2
                return material_count * 0.1

        return 0.0

    def reset(self):
        """重置中转斗"""
        self.current_weight = 0.0
        self.weight = 0.0
        self.residual_weight = 0.0
        self.is_open = True
        self._manual_switch_state = True
        self.is_active = False
        self.stored_materials = []


class SmallBin:
    """高位配料站小仓模型"""

    def __init__(self, bin_id: str, bin_config: dict):
        self.id = bin_id
        self.name = bin_config['name']
        self.column = bin_config['column']
        self.row = bin_config['row']
        self.target_conveyor = bin_config['target_conveyor']  # D7/D8/D9
        self.capacity = bin_config.get('capacity', config.BATCHING_BIN_CAPACITY)  # 容量（吨）
        self.current_level = 0.0  # 当前料位（吨）
        self.consumption_rate = 0.01  # 消耗速度 (t/s)

    @property
    def level_percent(self) -> float:
        """料位百分比"""
        return (self.current_level / self.capacity) * 100 if self.capacity > 0 else 0

    @property
    def is_full(self) -> bool:
        """是否满仓"""
        return self.current_level >= self.capacity

    def receive_material(self, weight_tons: float = None) -> bool:
        """
        接收物料（按吨计算）

        Args:
            weight_tons: 物料重量（吨），每个物料 0.1t

        Returns:
            是否接收成功
        """
        if weight_tons is None:
            weight_tons = config.MATERIAL_WEIGHT  # 每个物料 0.1t

        new_level = self.current_level + weight_tons
        if new_level >= self.capacity:
            self.current_level = self.capacity
            return False
        self.current_level = new_level
        return True

    def reset(self):
        """重置小仓"""
        self.current_level = 0.0
        self.consumption_rate = 0.01


class SimulationController(QObject):
    """仿真控制器"""

    material_spawned = pyqtSignal(object)
    material_moved = pyqtSignal(object)
    material_arrived = pyqtSignal(object, str)
    sensor_triggered = pyqtSignal(str, bool)
    alarm_raised = pyqtSignal(str, str)
    state_changed = pyqtSignal(str, dict)
    route_started = pyqtSignal(str)
    route_stopped = pyqtSignal(str)
    route_state_changed = pyqtSignal(str, str, str)  # route_id, old_state, new_state

    def __init__(self):
        super().__init__()

        self.conveyors: Dict[str, Conveyor] = {}
        self.sensors: Dict[str, Sensor] = {}
        self.hoppers: Dict[str, TransferHopper] = {}
        self.small_bins: Dict[str, SmallBin] = {}
        self.feed_points: Dict[str, dict] = {}

        self.materials: List[Material] = []
        self.active_materials: List[Material] = []

        self.speed = config.DEFAULT_SPEED
        self.is_running = False
        self.active_routes: Set[str] = set()
        self.total_runtime = 0  # 实际运行时间（秒）
        self.total_materials_sent = 0
        self.alarm_count = 0
        self.active_alarms: Set[str] = set()  # 当前活跃的报警键
        self.total_feed_weight = 0.0  # 累计上料重量（吨）

        # 高精度计时器 - 用于跟踪实际运行时间
        self._runtime_timer = QElapsedTimer()
        self._runtime_timer.start()
        self._last_runtime_ms = 0  # 上次累计的时间戳（毫秒）

        # 脏标记：用于通知UI需要更新
        self._dirty = False

        # 上料速率 0.195 t/s
        self.feed_rate = 0.195

        self.feed_timer = QTimer()
        self.feed_timer.timeout.connect(self._spawn_materials)
        self.feed_interval = 500  # 每秒生成2个物料

        self.route_material_map: Dict[str, List[Material]] = {}

        # 路线⑤⑦⑨的物料类型缓存（启动时随机选择，只上一次）
        self.route_material_cache: Dict[str, str] = {}

        # 路线到小仓的映射
        self.route_to_bin: Dict[str, str] = {}

        # 路线⑧⑨的起点发料仓映射（S仓，物料来源）
        self.route_silo_bin: Dict[str, str] = {}

        # 传感器故障诊断系统（故障注入，仿真侧）
        self.fault_diagnosis = SensorFaultDiagnosis()
        self.diagnosis_result: List[Tuple[str, str]] = []

        # 独立诊断引擎 + 适配器（跨传感器一致性故障检测）
        self.diagnosis_engine = DiagnosisEngine()
        self.fault_diagnosis_adapter = FaultDiagnosisAdapter(self.diagnosis_engine)
        self._accumulated_diagnosis: Dict[str, tuple] = {}  # key → (insert_time, DiagnosisResult)

        # 传感器数据管理器（读写JSON文件）
        self.sensor_data_manager = get_data_manager()

        # 传感器数据生成器（根据仿真状态生成数据）
        self.sensor_data_generator = get_data_generator(self.sensor_data_manager)
        # 设置故障诊断系统引用（用于生成包含故障的数据）
        self.sensor_data_generator.set_fault_diagnosis(self.fault_diagnosis)

        # 路线状态管理器
        self.route_state_manager = get_route_state_manager()
        self.route_state_manager.set_state_change_callback(self._on_route_state_change)

        # 控制策略数据生成器
        self.control_strategy_generator = get_control_strategy_generator(self.sensor_data_manager)
        self.control_strategy_generator.set_controller(self)

        # TCP 数据发送器（向下位机发送传感器数据）
        self.tcp_sender = TcpDataSender()
        # UDP 二进制帧发送器
        self.udp_sender = UdpBinarySender()

        # TCP 诊断客户端（远程诊断服务 :8890）
        self._tcp_diagnosis_client = None
        # TCP 调度客户端（调度算法服务 :8891/:8892/:8893）
        self._tcp_scheduling_client = None
        # 诊断模式："local" / "tcp"
        self._diagnosis_mode = "local"
        # 最新调度结果 belt_id → dict
        self._tcp_schedules: Dict[str, dict] = {}

        # 自动上料状态
        self._auto_feeding_active = False
        self._auto_mode = False  # 手动/自动模式标志（兼容保留）
        self._belt_auto_mode: Dict[str, bool] = {  # 每条终点皮带独立的手动/自动模式
            'D6': False, 'D7': False, 'D8': False, 'D9': False,
        }
        self._executing_bin: Dict[str, str] = {}     # belt_id → bin_id
        self._executing_route: Dict[str, str] = {}    # belt_id → route_id
        self._scheduled_sequence: Dict[str, list] = {}   # belt_id → [剩余待执行料仓序列]
        self._last_auto_schedule_request: Dict[str, float] = {}  # belt_id → timestamp（自动调度请求冷却）
        self._last_emergency_schedule: Dict[str, float] = {}  # belt_id → timestamp（紧急调度独立冷却）

        # 检修状态
        self._maintenance_bins: Set[str] = set()

        # 是否启用传感器数据生成（写入JSON）
        self.enable_sensor_data_generation = True
        self._last_sensor_write_time = 0.0  # 上次传感器数据写入时间（秒）

        # 激光测距仪传感器状态管理（保留兼容，上料控制信号由控制策略生成）
        self.laser_sensor_states: Dict[str, bool] = config.FEED_POINT_LASER_STATES.copy()

        # 小车4状态管理（D6皮带上的水平分料小车）
        self.cart4_position = 1  # 逻辑位置（用于判断是否需要移动）
        self.cart4_target_position = 1  # 目标位置
        self.cart4_is_moving = False  # 是否在移动中
        self.cart4_sensor_position = 1  # 传感器报告的位置（等小车实际到达后才更新）

        # Cart1/2/3位置管理（虚拟小车，位置由物料决定）
        self.cart_positions: Dict[str, int] = {
            'Cart1': 1,
            'Cart2': 1,
            'Cart3': 1,
        }
        self.cart_target_positions: Dict[str, int] = {
            'Cart1': 1,
            'Cart2': 1,
            'Cart3': 1,
        }
        # 传感器报告的位置（等小车实际到达后才更新）
        self.cart_sensor_positions: Dict[str, int] = {
            'Cart1': 1,
            'Cart2': 1,
            'Cart3': 1,
        }
        # 分料传感器状态（持久化，不依赖当前路线）
        self.cart_divert: Dict[str, tuple] = {
            'Cart1': (True, False),
            'Cart2': (True, False),
            'Cart3': (False, True),
        }

        self._consumption_rates: Dict[str, float] = {}  # bin_id -> rate (t/s)
        self._consumption_active = False  # 消耗开关

        # 料位阈值（从config读取或使用默认值）
        self.level_threshold_with_hopper = config.ALARM_THRESHOLDS.get('batching_full', 95)  # 有中转斗：95%
        self.level_threshold_without_hopper = config.ALARM_THRESHOLDS.get('silo_full', 90)  # 无中转斗：90%

        # 待停止路线集合（等待余料清空后停止）
        self._pending_stop_routes: Set[str] = set()
        # 待停止：小车 MOVING_TO_TARGET 时等到达后再停该路线全部皮带
        self._pending_stop_after_cart_arrival: Set[str] = set()

        self._init_components()

    def _init_components(self):
        """初始化组件"""
        for conv_id, conv_config in config.CONVEYORS.items():
            conveyor = Conveyor(conv_id, conv_config)
            self.conveyors[conv_id] = conveyor

        for sensor_id, sensor_config in config.SENSORS.items():
            sensor = Sensor(sensor_id, sensor_config)
            self.sensors[sensor_id] = sensor

        for hp_id, hp_config in config.TRANSFER_HOPPERS.items():
            hopper = TransferHopper(hp_id, hp_config)
            self.hoppers[hp_id] = hopper

        # 初始化小仓（从高位配料站配置动态生成）
        bs = config.BATCHING_STATION
        columns = bs.get('columns', 4)
        rows = bs.get('rows', 7)
        col_names = bs.get('col_names', ['P1', 'P2', 'P3', 'P4'])

        # 目标皮带分配（4列对应D7/D8/D9/？）
        target_conveyors = ['D7', 'D8', 'D9', 'D7']  # 第4列回环到D7

        bin_id = 0
        for row in range(rows):
            for col in range(columns):
                bin_id_str = f"{col_names[col]}-{row + 1}"
                bin_config = {
                    'name': bin_id_str,
                    'column': col,
                    'row': row,
                    'target_conveyor': target_conveyors[col % len(target_conveyors)],
                    'capacity': config.BATCHING_BIN_CAPACITY,
                }
                small_bin = SmallBin(bin_id_str, bin_config)
                self.small_bins[bin_id_str] = small_bin
                bin_id += 1

        # 初始化小仓料位（从sensor_data_manager读取）
        self._load_initial_levels()
        # 初始化小车位置与分料状态
        self._load_initial_cart_positions()
        # 初始化消耗速度
        self._load_initial_consumption_rates()

        self.feed_points = config.FEED_POINTS.copy()

    def _load_initial_levels(self):
        """从sensor_data_manager加载初始料位"""
        try:
            level_sensors = self.sensor_data_manager.read_all_level_sensors()
            for bin_id, level_percent in level_sensors.items():
                # level_percent 是百分比（0-100）
                if level_percent > 0:
                    # 更新small_bins的料位（百分比 -> 吨）
                    if bin_id in self.small_bins:
                        capacity = self.small_bins[bin_id].capacity
                        self.small_bins[bin_id].current_level = level_percent * capacity / 100
                    # 更新view中的silo_compartments（百分比 -> 吨）
                    if hasattr(self, 'view') and self.view and hasattr(self.view, 'silo_compartments'):
                        if bin_id in self.view.silo_compartments:
                            capacity = self.view.silo_compartments[bin_id].get('capacity', 110)
                            self.view.silo_compartments[bin_id]['current_level'] = level_percent * capacity / 100
                    # 更新到控制策略生成器
                    self.control_strategy_generator.set_level_sensor(bin_id, level_percent)
        except Exception as e:
            print(f"[初始化] 加载料位失败: {e}", flush=True)

    def _load_initial_cart_positions(self):
        """从sensor_data_manager加载小车位置与分料状态"""
        try:
            cart_sensors = self.sensor_data_manager.read_cart_sensors()
            for cart_id in ('Cart1', 'Cart2', 'Cart3', 'Cart4'):
                if cart_id in cart_sensors:
                    data = cart_sensors[cart_id]
                    pos = data.get('position', 1)
                    left_div = data.get('left_divert', False)
                    right_div = data.get('right_divert', False)
                    if cart_id == 'Cart4':
                        self.cart4_position = pos
                        self.cart4_target_position = pos
                        self.cart4_sensor_position = pos
                    else:
                        self.cart_positions[cart_id] = pos
                        self.cart_target_positions[cart_id] = pos
                        self.cart_sensor_positions[cart_id] = pos
                        self.cart_divert[cart_id] = (left_div, right_div)
        except Exception as e:
            print(f"[初始化] 加载小车位置失败: {e}", flush=True)

    def _load_initial_consumption_rates(self):
        """从sensor_data_manager加载消耗速度"""
        try:
            rates = self.sensor_data_manager.read_consumption_rates()
            self._consumption_rates.update(rates)
            for bin_id, rate in rates.items():
                if bin_id in self.small_bins:
                    self.small_bins[bin_id].consumption_rate = rate
        except Exception as e:
            print(f"[初始化] 加载消耗速度失败: {e}", flush=True)

    def _on_route_state_change(self, route_id: str, old_state, new_state):
        """路线状态变更回调"""
        self.route_state_changed.emit(route_id, old_state.value, new_state.value)

    def start_route(self, route_id: str) -> bool:
        """启动指定路线"""
        if route_id not in config.FEED_ROUTES:
            return False

        route = config.FEED_ROUTES[route_id]

        # 检查上料点是否存在
        feed_point = route.get('feed_point')
        if feed_point and feed_point not in ('silo', 'silo_out'):
            if feed_point not in self.feed_points:
                return False

        # 检查上料点是否有原料（根据激光传感器状态）
        if feed_point and feed_point != 'silo_out':
            if not self.is_route_available(route_id):
                print(f"[启动失败] {route_id} 上料点{feed_point}无原料", flush=True)
                return False

        # 获取目标料仓
        target_bin = self.route_to_bin.get(route_id)
        if not target_bin:
            # 如果没有设置目标料仓，默认设为第一个
            if route_id in ('route1', 'route2', 'route3'):
                target_bin = 'P1-1'    # D7 → P1
            elif route_id == 'route4':
                target_bin = 'P4-1'    # D9 → P4
            elif route_id == 'route5':
                target_bin = 'S1'      # D6 → silo
            elif route_id == 'route6':
                target_bin = 'P2-1'    # D8 → P2/P3
            elif route_id == 'route7':
                target_bin = 'P4-1'    # D9 → P4 (silo_out)
            elif route_id == 'route8':
                target_bin = 'P2-1'    # D8 → P2/P3 (silo_out)
            else:
                target_bin = 'P1-1'
            self.route_to_bin[route_id] = target_bin

        # 通过路线状态机启动路线（进入MOVING_TO_TARGET状态）
        if not self.route_state_manager.start_route(route_id, target_bin):
            print(f"[启动失败] {route_id} 资源被占用（中转斗被其他路线锁定）", flush=True)
            return False

        # 获取小车ID
        ctx = self.route_state_manager.get_route_context(route_id)
        cart_id = ctx.assigned_cart if ctx else None

        # 确定终点皮带（小车所在的皮带）
        final_conveyor = route['conveyors'][-1] if route['conveyors'] else None

        # 启动非终点皮带（这些皮带一直在运行）
        for conv_id in route['conveyors']:
            if conv_id != final_conveyor:
                if conv_id in self.conveyors:
                    self.conveyors[conv_id].start(self.speed)

        # 终点皮带初始停止（小车所在皮带）
        if final_conveyor and final_conveyor in self.conveyors:
            self.conveyors[final_conveyor].stop()

        # 设置小车目标位置（根据是否需要移动决定是否触发状态转换）
        self._set_cart_target_position(route_id, target_bin)

        self.active_routes.add(route_id)
        self.route_material_map[route_id] = []
        self.route_started.emit(route_id)

        if not self.is_running:
            self.is_running = True
            # 重置运行时计时器，确保从现在开始准确计时
            self._runtime_timer.restart()
            self._last_runtime_ms = 0
            self.feed_timer.start(self.feed_interval)

        return True

    def resume_route(self, route_id: str) -> bool:
        """从WAITING状态恢复路线继续上料"""
        if route_id not in config.FEED_ROUTES:
            return False

        # 检查路线状态
        ctx = self.route_state_manager.get_route_context(route_id)
        if not ctx or ctx.state not in (RouteState.WAITING, RouteState.STANDBY):
            return False

        # 获取目标料仓
        target_bin = self.route_to_bin.get(route_id)
        if not target_bin:
            return False

        route = config.FEED_ROUTES[route_id]

        # 获取小车ID
        cart_id = ctx.assigned_cart

        # 确定终点皮带
        final_conveyor = route['conveyors'][-1] if route['conveyors'] else None

        # 判断小车是否需要移动
        needs_cart_move = False
        if cart_id and cart_id != 'Cart4':
            # 高位配料站小车：根据目标位置判断
            position = 1
            if '-' in target_bin:
                parts = target_bin.split('-')
                if len(parts) == 2:
                    try:
                        position = int(parts[1])
                    except ValueError:
                        position = 1
                else:
                    position = 1
            current_pos = self.cart_positions.get(cart_id, 1)
            needs_cart_move = (current_pos != position)
        elif cart_id == 'Cart4':
            # 小车4：根据目标S仓判断
            if target_bin.startswith('S') and len(target_bin) <= 3:
                try:
                    num = int(target_bin[1:])
                    position = (num - 1) % 6 + 1
                except ValueError:
                    position = 1
            else:
                position = 1
            needs_cart_move = (self.cart4_position != position)

        # 更新目标料仓
        ctx.target_bin = target_bin

        if needs_cart_move:
            # 需要小车移动：进入MOVING_TO_TARGET状态
            self.route_state_manager._transition(ctx, RouteState.MOVING_TO_TARGET)
            ctx.cart_moving = True
            # 注意：不要清空 pending_release_weights！
            # 因为这是从上一轮上料（WAITING/CLEARING阶段）继承的余料数据
            # 下一轮FEEDING阶段需要使用这些数据来显示余料释放

            # 设置小车目标位置（不触发状态转换，因为已经在MOVING_TO_TARGET状态）
            self._set_cart_target_position_no_arrival(route_id, target_bin)

            # 小车移动时：停止终点皮带，关闭中转斗开关，非终点皮带继续运行
            final_conveyor = route['conveyors'][-1] if route['conveyors'] else None
            for conv_id in route['conveyors']:
                if conv_id in self.conveyors:
                    if conv_id == final_conveyor:
                        self.conveyors[conv_id].stop()  # 只停止终点皮带
                    # 非终点皮带保持运行
            # 关闭中转斗开关（小车移动时不能上料）
            for hopper_id in ctx.assigned_hoppers:
                if hopper_id in self.hoppers:
                    self.hoppers[hopper_id].is_open = False
        else:
            # 小车已在目标位置：直接进入FEEDING状态
            self.route_state_manager._transition(ctx, RouteState.FEEDING)
            ctx.clearing_strategy = self._resolve_clearing_strategy(route_id)
            # 只清空final_weights和current_weights（用于CLEARING阶段）
            # 保留pending_release_weights（从上一轮继承的余料，FEEDING阶段需要使用）
            ctx.final_weights.clear()
            ctx.current_weights.clear()
            ctx.feeding_start_time = self.total_runtime
            ctx.cart_moving = False

            # 启动所有皮带
            for conv_id in route['conveyors']:
                if conv_id in self.conveyors:
                    self.conveyors[conv_id].start(self.speed)
            # 打开中转斗开关（正常补料开始）
            for hopper_id in ctx.assigned_hoppers:
                if hopper_id in self.hoppers:
                    self.hoppers[hopper_id].is_open = True

        # 确保仿真运行中
        if not self.is_running:
            self.is_running = True
            self._runtime_timer.restart()
            self._last_runtime_ms = 0
            self.feed_timer.start(self.feed_interval)

        # 确保路线在活跃列表中
        self.active_routes.add(route_id)

        self.route_started.emit(route_id)
        return True

    def _get_cart_position_for_bin(self, cart_id: str, target_bin: str) -> int:
        """根据目标料仓计算小车物理位置"""
        if cart_id == 'Cart4':
            if target_bin.startswith('S'):
                # 支持 S1-S12 和 S1-1~S6-2 两种格式
                rest = target_bin[1:]
                if '-' in rest:
                    rest = rest.split('-')[0]
                try:
                    return (int(rest) - 1) % 6 + 1
                except ValueError:
                    return 1
            return 1
        if '-' in target_bin:
            parts = target_bin.split('-')
            if len(parts) == 2:
                try:
                    return int(parts[1])
                except ValueError:
                    return 1
        return 1

    def _set_cart_target_position(self, route_id: str, target_bin: str):
        """设置小车目标位置（根据目标料仓）"""
        ctx = self.route_state_manager.get_route_context(route_id)
        if not ctx or not ctx.assigned_cart:
            return

        cart_id = ctx.assigned_cart
        position = self._get_cart_position_for_bin(cart_id, target_bin)

        if cart_id == 'Cart4':
            self.cart4_target_position = position
            if self.cart4_position != position:
                self.cart4_is_moving = True
                ctx.cart_moving = True
            else:
                if ctx.state == RouteState.MOVING_TO_TARGET:
                    self._immediate_cart_arrival(route_id, 'Cart4')
        else:
            self.cart_target_positions[cart_id] = position
            current_pos = self.cart_positions.get(cart_id, 1)
            if current_pos != position:
                ctx.cart_moving = True
                ctx.cart_target_position = position
            else:
                if ctx.state == RouteState.MOVING_TO_TARGET:
                    self._immediate_cart_arrival(route_id, cart_id)

    def _set_cart_target_position_no_arrival(self, route_id: str, target_bin: str):
        """设置小车目标位置（不触发状态转换，用于resume_route中）"""
        ctx = self.route_state_manager.get_route_context(route_id)
        if not ctx or not ctx.assigned_cart:
            return

        cart_id = ctx.assigned_cart
        position = self._get_cart_position_for_bin(cart_id, target_bin)

        if cart_id == 'Cart4':
            self.cart4_target_position = position
            if self.cart4_position != position:
                self.cart4_is_moving = True
                ctx.cart_moving = True
            else:
                if ctx.state == RouteState.MOVING_TO_TARGET:
                    self._immediate_cart_arrival(route_id, 'Cart4')
        else:
            self.cart_target_positions[cart_id] = position
            current_pos = self.cart_positions.get(cart_id, 1)
            if current_pos != position:
                ctx.cart_moving = True
                ctx.cart_target_position = position

    def _immediate_cart_arrival(self, route_id: str, cart_id: str):
        """立即触发小车到达后的状态转换（当小车不需要移动时）"""
        ctx = self.route_state_manager.get_route_context(route_id)
        if not ctx:
            print(f"[到达] {route_id} ctx为None!", flush=True)
            return

        if ctx.state != RouteState.MOVING_TO_TARGET:
            print(f"[到达] {route_id} 状态={ctx.state.value} 非MOVING_TO_TARGET，跳过", flush=True)
            return

        if route_id in self._pending_stop_after_cart_arrival:
            print(f"[到达] {route_id} 在pending_stop中，执行停止", flush=True)
            self._pending_stop_after_cart_arrival.discard(route_id)
            self._complete_stop_route(route_id)
            return

        self.route_state_manager._transition(ctx, RouteState.FEEDING)
        ctx.cart_moving = False
        ctx.feeding_start_time = self.total_runtime
        ctx.clearing_strategy = self._resolve_clearing_strategy(route_id)

        if cart_id == 'Cart4':
            self.cart4_sensor_position = self.cart4_position
        else:
            self.cart_sensor_positions[cart_id] = self.cart_positions.get(cart_id, 1)

        route = config.FEED_ROUTES.get(route_id)
        if route and route['conveyors']:
            for conv_id in route['conveyors']:
                if conv_id in self.conveyors:
                    self.conveyors[conv_id].start(self.speed)
                    print(f"[到达] {route_id} 启动皮带 {conv_id}", flush=True)
            for hopper_id in ctx.assigned_hoppers:
                if hopper_id in self.hoppers:
                    self.hoppers[hopper_id].is_open = True
                    print(f"[到达] {route_id} 打开中转斗 {hopper_id}", flush=True)

    def set_route_silo_bin(self, route_id: str, silo_bin: str):
        """设置路线⑧⑨的起点发料仓（S仓）"""
        if route_id not in config.FEED_ROUTES:
            return
        if silo_bin.startswith('S') and len(silo_bin) >= 2 and silo_bin[1:].isdigit():
            self.route_silo_bin[route_id] = silo_bin

    def set_route_target_bin(self, route_id: str, bin_id: str):
        """设置路线的目标小仓"""
        if route_id not in config.FEED_ROUTES:
            return
        # 接受高位配料站小仓（P1-x, P2-x, P3-x, P4-x）或高位储料仓（S1-S12）
        is_small_bin = bin_id in self.small_bins
        is_high_silo = bin_id.startswith('S') and len(bin_id) >= 2 and bin_id[1:].isdigit()
        if is_small_bin or is_high_silo:
            self.route_to_bin[route_id] = bin_id

    def _get_or_select_silo_source(self, route_id: str):
        """获取或自动选择路线⑧⑨的发料S仓

        如果当前S仓有料则继续使用，否则自动选择同物料种类中序号最低的有料仓。
        """
        current = self.route_silo_bin.get(route_id)
        if current and self._silo_bin_has_material(current):
            return current
        new_source = self._auto_select_silo_source_bin(route_id)
        if new_source:
            self.route_silo_bin[route_id] = new_source
        return new_source

    def _silo_bin_has_material(self, bin_id: str) -> bool:
        if hasattr(self, 'view') and self.view:
            comp = self.view.silo_compartments.get(bin_id)
            if comp:
                return comp.get('current_level', 0) > 0
        return False

    def _auto_select_silo_source_bin(self, route_id: str):
        """根据目标P仓的物料种类自动选择发料S仓（料位最高优先）"""
        if route_id == 'route7':
            candidates = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6']
        elif route_id == 'route8':
            target_bin = self.route_to_bin.get(route_id)
            if target_bin and target_bin.startswith('P2-'):
                candidates = ['S7', 'S8']
            elif target_bin and target_bin.startswith('P3-'):
                candidates = ['S9', 'S10', 'S11', 'S12']
            else:
                return None
        else:
            return None
        best_bin = None
        best_level = 0
        for bin_id in candidates:
            if self._silo_bin_has_material(bin_id):
                comp = self.view.silo_compartments.get(bin_id)
                level = comp.get('current_level', 0) if comp else 0
                if level > best_level:
                    best_level = level
                    best_bin = bin_id
        return best_bin

    def _deduct_from_high_silo(self, bin_id: str):
        if hasattr(self, 'view') and self.view:
            comp = self.view.silo_compartments.get(bin_id)
            if comp:
                comp['current_level'] = max(0, comp['current_level'] - config.MATERIAL_WEIGHT)

    def stop_route(self, route_id: str):
        """停止指定路线（需要先清空余料）"""
        if route_id not in config.FEED_ROUTES:
            return

        route = config.FEED_ROUTES[route_id]
        ctx = self.route_state_manager.get_route_context(route_id)

        # 根据当前状态决定如何停止
        if ctx and ctx.state == RouteState.FEEDING:
            # FEEDING状态：进入CLEARING状态，继续清空余料
            # 不立即停止皮带，保持运转让余料清空
            self.route_state_manager.trigger_clearing(route_id)
            # 标记路线为待停止（等余料清空后停止）
            self._pending_stop_routes.add(route_id)

        elif ctx and ctx.state == RouteState.CLEARING:
            # CLEARING状态：继续清空，等待完成
            self._pending_stop_routes.add(route_id)

        elif ctx and ctx.state == RouteState.MOVING_TO_TARGET:
            # 小车移动中：等到达后再停该路线全部皮带（不立即 _complete_stop_route）
            self._pending_stop_after_cart_arrival.add(route_id)

        elif ctx and ctx.state in (RouteState.WAITING, RouteState.STANDBY):
            # WAITING/STANDBY状态：直接停止
            self._complete_stop_route(route_id)

        else:
            # IDLE状态：直接停止
            self._complete_stop_route(route_id)

        # 立即停止该路线的上料控制信号（JSON）；共用同一上料点的多条路线由生成器综合判断
        self.control_strategy_generator._generate_feed_signals(self.active_routes)

    def _complete_stop_route(self, route_id: str):
        """完成路线停止（真正停止皮带）"""
        if route_id not in config.FEED_ROUTES:
            return

        route = config.FEED_ROUTES[route_id]

        # 停止该路线上的全部皮带
        for conv_id in route.get('conveyors', []):
            if conv_id in self.conveyors:
                self.conveyors[conv_id].stop()

        # 从路线状态机停止
        self.route_state_manager.stop_route(route_id)

        # 移除待停止标记
        self._pending_stop_routes.discard(route_id)
        self._pending_stop_after_cart_arrival.discard(route_id)

        self.active_routes.discard(route_id)

        # 从画布/逻辑映射中移除该路线，否则 view 仍认为旧路线在运行，会保留旧小车又新建新路线小车（双车）
        self.route_to_bin.pop(route_id, None)
        self.route_silo_bin.pop(route_id, None)

        if not self.active_routes:
            self.is_running = False
            self.feed_timer.stop()

        self.control_strategy_generator._generate_feed_signals(self.active_routes)
        self.route_stopped.emit(route_id)

    def start(self):
        """启动仿真"""
        self.is_running = True
        # 重置运行时计时器，确保从现在开始准确计时
        self._runtime_timer.restart()
        self._last_runtime_ms = 0
        self.feed_timer.start(self.feed_interval)
        self.state_changed.emit('simulation', {'running': True})

    def stop(self):
        """停止仿真"""
        self.is_running = False
        self.feed_timer.stop()
        self.tcp_sender.stop()
        self.udp_sender.stop()
        self.state_changed.emit('simulation', {'running': False})

    def pause(self):
        """暂停仿真"""
        self.is_running = False
        self.feed_timer.stop()

    def reset(self):
        """重置仿真"""
        self.stop()

        for conveyor in self.conveyors.values():
            conveyor.stop()

        for sensor in self.sensors.values():
            sensor.is_active = False
            sensor.trigger_count = 0

        for hopper in self.hoppers.values():
            hopper.current_weight = 0.0
            hopper.is_active = False
            hopper.switch_fault_mode = None
            hopper.weight_fault_mode = None
            hopper.weight_offset = 0.0
            hopper.belt_speed_multiplier = 1.0
            hopper.stored_materials = []

        # 重置小仓
        for small_bin in self.small_bins.values():
            small_bin.reset()

        self.materials.clear()
        self.active_materials.clear()
        self.active_routes.clear()
        self.route_material_map.clear()
        self.route_material_cache.clear()
        self.route_to_bin.clear()
        self.route_silo_bin.clear()

        self.total_runtime = 0
        self.total_materials_sent = 0
        self.total_feed_weight = 0.0
        self.alarm_count = 0
        self.active_alarms.clear()

        # 重置高精度计时器
        self._runtime_timer.restart()
        self._last_runtime_ms = 0

        # 重置故障诊断系统
        self.fault_diagnosis.clear_all_faults()
        self.diagnosis_result.clear()
        self._accumulated_diagnosis.clear()
        self.diagnosis_engine.clear_history()
        # 持久化状态（reset_all_data会清空JSON，需提前保存）
        _saved_cart_positions = dict(self.cart_positions)
        _saved_cart_divert = dict(self.cart_divert)
        _saved_consumption_rates = dict(self._consumption_rates)

        # 清除数据管理器中的故障 + 重置传感器数据到初始状态
        self.sensor_data_manager.reset_all_data()
        self.control_strategy_generator.clear_all_fault_overrides()

        # 重置皮带手动状态
        for conv_id in config.CONVEYOR_STATES:
            config.CONVEYOR_STATES[conv_id] = None

        # 重置路线状态管理器
        self.route_state_manager.reset()

        self._pending_stop_routes.clear()
        self._pending_stop_after_cart_arrival.clear()

        # 重置小车位置（从持久化数据恢复）
        self.cart4_position = 1
        self.cart4_target_position = 1
        self.cart4_is_moving = False
        self.cart4_sensor_position = 1
        self.cart_positions = _saved_cart_positions
        self.cart_target_positions = dict(_saved_cart_positions)
        self.cart_sensor_positions = dict(_saved_cart_positions)
        self.cart_divert = _saved_cart_divert
        # 重写到JSON
        for cart_id in ('Cart1', 'Cart2', 'Cart3'):
            pos = _saved_cart_positions.get(cart_id, 1)
            ld, rd = _saved_cart_divert.get(cart_id, (False, False))
            self.sensor_data_manager.write_cart_position(cart_id, pos)
            self.sensor_data_manager.write_cart_left_divert(cart_id, ld)
            self.sensor_data_manager.write_cart_right_divert(cart_id, rd)
        # 恢复消耗速度
        self._consumption_rates = _saved_consumption_rates
        for bin_id, rate in _saved_consumption_rates.items():
            if bin_id in self.small_bins:
                self.small_bins[bin_id].consumption_rate = rate
        self.sensor_data_manager.write_consumption_rates(_saved_consumption_rates)
        if hasattr(self, '_cart_move_timers'):
            self._cart_move_timers.clear()

        MaterialFactory.reset_id_counter()
        self.state_changed.emit('reset', {})

    def set_speed(self, speed: float):
        """设置皮带速度"""
        self.speed = max(config.MIN_SPEED, min(config.MAX_SPEED, speed))
        for conveyor in self.conveyors.values():
            if conveyor.is_running:
                conveyor.start(self.speed)
        self.state_changed.emit('speed', {'speed': self.speed})

    def _spawn_materials(self):
        """自动供料到所有活跃路线"""
        for route_id in self.active_routes:
            self._spawn_material_for_route(route_id)

    def _spawn_material_for_route(self, route_id: str):
        """为指定路线生成物料"""
        route = config.FEED_ROUTES[route_id]

        if not route['conveyors']:
            return

        first_conv = route['conveyors'][0]

        for conv_id in route['conveyors']:
            conveyor = self.conveyors.get(conv_id)
            if not conveyor or not conveyor.is_running:
                return

        ctx = self.route_state_manager.get_route_context(route_id)
        if not ctx:
            return

        if ctx.state != RouteState.FEEDING:
            return

        # 路线⑧⑨：自动选择发料S仓并扣减料位
        if route_id in ('route7', 'route8'):
            source_bin = self._get_or_select_silo_source(route_id)
            if source_bin is None:
                return
            self._deduct_from_high_silo(source_bin)

        # 获取上料点位置
        start_pos = self._get_feed_point_position(route_id)
        if not start_pos:
            return

        # 创建物料
        material_types = route.get('material_types', ['stone_powder'])

        # 路线⑤：物料类型由目标S仓决定
        if route_id == 'route5':
            target_bin = self.route_to_bin.get(route_id)
            if target_bin and target_bin in pos.SILO_BIN_MATERIALS:
                mt = pos.SILO_BIN_MATERIALS[target_bin]
            else:
                mt = 'stone_powder'
        # 路线⑥⑧ (P2/P3)：根据选择的小仓列决定物料类型
        elif route_id in ('route6', 'route8') and material_types is None:
            target_bin = self.route_to_bin.get(route_id)
            if target_bin and target_bin.startswith('P2-'):
                mt = 'stone_powder'
            elif target_bin and target_bin.startswith('P3-'):
                mt = 'aggregate_10mm'
            else:
                mt = 'stone_powder'
        elif material_types is not None and len(material_types) > 1:
            if route_id not in self.route_material_cache:
                self.route_material_cache[route_id] = random.choice(material_types)
            mt = self.route_material_cache[route_id]
        else:
            mt = material_types[0]

        material = MaterialFactory.create_material(start_pos, mt)
        material.route_id = route_id

        # 进入第一条皮带
        material.enter_conveyor(first_conv, 0)
        material.total_distance = 0

        self.materials.append(material)
        self.active_materials.append(material)

        if route_id in self.route_material_map:
            self.route_material_map[route_id].append(material)

        # 增加上料重量（按物料数量计算）
        self.total_feed_weight += config.MATERIAL_WEIGHT

        self.material_spawned.emit(material)

        return True

    def _get_feed_point_position(self, route_id: str) -> Optional[tuple]:
        """获取路线的上料点位置
        
        注意：物料直接出现在第一条皮带的起点位置，
        确保物料移动速度与皮带设置速度一致，不会有额外的偏移时间。
        """
        route = config.FEED_ROUTES[route_id]
        
        # 特殊处理路线8和9：从高位储料仓的指定料仓出料
        if route_id in ('route7', 'route8'):
            # 使用起点仓（S仓）作为出料位置
            start_bin = self.route_silo_bin.get(route_id)
            if start_bin and start_bin.startswith('S') and start_bin[1:].isdigit():
                if hasattr(self, 'view') and self.view:
                    return self.view._get_high_silo_bin_position(start_bin)
            # 如果没有选择料仓，使用默认位置
            if hasattr(self, 'view') and self.view:
                return self.view._get_high_silo_bin_position('S1')
        
        # 直接使用第一个皮带的起始位置作为物料生成点
        first_conv_id = route['conveyors'][0] if route['conveyors'] else None
        if first_conv_id:
            conveyor = self.conveyors.get(first_conv_id)
            if conveyor:
                return conveyor.start_pos
        
        # 如果没有找到皮带配置，回退到原来的逻辑
        feed_point = route.get('feed_point')
        if feed_point and feed_point not in ('silo', 'silo_out'):
            fp_config = self.feed_points.get(feed_point)
            if fp_config:
                return fp_config['position']
        
        return None

    def update(self, delta_time: int):
        """更新仿真"""
        if not self.is_running:
            return

        # 使用高精度内部计时器跟踪实际运行时间（不依赖外部传入的delta_time）
        current_ms = self._runtime_timer.elapsed()
        delta_runtime_ms = current_ms - self._last_runtime_ms
        self._last_runtime_ms = current_ms
        delta_seconds = delta_runtime_ms / 1000.0

        # 累加到总运行时间
        self.total_runtime += delta_seconds

        self._update_hoppers(delta_seconds)
        self._update_materials(delta_seconds)
        self._update_sensors()
        self._update_cart_positions(delta_seconds)
        if self.active_routes:
            self._run_fault_diagnosis()
        self._check_alarms()

        # 料仓消耗（模拟搅拌站生产消耗）
        self._update_bin_consumption(delta_seconds)

        # 定期清理失效物料（每5秒，防止materials列表无限增长导致卡顿）
        if not hasattr(self, '_last_material_cleanup'):
            self._last_material_cleanup = 0.0
        if self.total_runtime - self._last_material_cleanup > 5.0:
            self._last_material_cleanup = self.total_runtime
            old_count = len(self.materials)
            active = [m for m in self.materials if m.is_active]
            self.materials.clear()
            self.materials.extend(active)
            if old_count != len(self.materials):
                print(f"[清理] materials: {old_count} → {len(self.materials)} (移除{old_count - len(self.materials)}个)", flush=True)

        # 检查料位是否达到阈值，触发清空状态
        self._check_level_thresholds()

        # 检查CLEARING状态是否完成余料清空
        self._check_clearing_completion()

        # 自动上料：空闲皮带检查是否有料仓低于70%需触发调度
        self._check_auto_feed_idle()

        # 检查待停止路线是否完成余料清空
        self._check_pending_stop_routes()

        # 生成传感器数据并写入JSON文件（每秒一次）
        if self.enable_sensor_data_generation:
            if self.total_runtime - self._last_sensor_write_time >= 1.0:
                sensor_delta = self.total_runtime - self._last_sensor_write_time
                self._generate_sensor_data(sensor_delta)
                self._last_sensor_write_time = self.total_runtime

        # 清空策略差异化动作（换列保持中转斗开启等）
        self._apply_clearing_strategy_actions()

        # 标记脏，通知UI需要更新
        self.mark_dirty()

    def _resolve_clearing_strategy(self, route_id: str) -> str:
        """根据缓存序列中下一料仓与当前料仓的关系确定清空策略: sequential / reverse / column_switch"""
        ctx = self.route_state_manager.get_route_context(route_id)
        if not ctx or not ctx.target_bin:
            return 'reverse'

        cart_to_belt = {'Cart1': 'D7', 'Cart2': 'D8', 'Cart3': 'D9'}
        belt_id = cart_to_belt.get(ctx.assigned_cart, '')
        if not belt_id:
            return 'reverse'

        # 从缓存序列中读取下一个料仓与当前料仓的关系，判断清空策略
        sequence = self._scheduled_sequence.get(belt_id, [])
        if not sequence:
            return 'reverse'

        next_bin = sequence[0]

        cur_col = ctx.target_bin.split('-')[0]
        next_col = next_bin.split('-')[0]

        if cur_col != next_col:
            return 'column_switch'

        cur_row = int(ctx.target_bin.split('-')[1])
        next_row = int(next_bin.split('-')[1])

        if next_row < cur_row and cur_row >= 4:
            if ctx.assigned_hoppers:
                return 'sequential'
            return 'reverse'
        return 'reverse'

    def _check_level_thresholds(self):
        """检查料位是否达到阈值，触发清空状态（支持动态策略阈值）"""
        strategy_thresholds = {'sequential': 98, 'reverse': 95, 'column_switch': 88}

        for route_id in list(self.active_routes):
            ctx = self.route_state_manager.get_route_context(route_id)
            if not ctx:
                continue

            if ctx.state != RouteState.FEEDING:
                continue

            feeding_start = getattr(ctx, 'feeding_start_time', 0.0)
            feeding_elapsed = self.total_runtime - feeding_start
            if feeding_elapsed < 3.0:
                continue

            # 使用 route_to_bin（实际投料目标），ctx.target_bin 可能不同步
            target_bin = self.route_to_bin.get(route_id) or ctx.target_bin
            if not target_bin:
                continue
            # 检测不同步情况
            ctx_bin = ctx.target_bin
            if ctx_bin and target_bin != ctx_bin:
                if not hasattr(self, '_target_mismatch_logged'):
                    self._target_mismatch_logged = set()
                key = (route_id, ctx_bin, target_bin)
                if key not in self._target_mismatch_logged:
                    self._target_mismatch_logged.add(key)
                    print(f"[WARN] {route_id} target_bin mismatch: ctx={ctx_bin} route_to_bin={target_bin}", flush=True)

            # 动态阈值：Cart1/2/3 使用策略阈值，Cart4 使用旧逻辑
            if ctx.assigned_cart in ('Cart1', 'Cart2', 'Cart3'):
                strategy = getattr(ctx, 'clearing_strategy', 'reverse')
                threshold = strategy_thresholds.get(strategy, 95)
                # D9 皮带（Cart3）：上料将满阈值固定 90%
                if ctx.assigned_cart == 'Cart3':
                    threshold = 90
            else:
                has_hopper = len(ctx.assigned_hoppers) > 0
                threshold = self.level_threshold_with_hopper if has_hopper else self.level_threshold_without_hopper

            level = 0.0
            if target_bin in self.small_bins:
                level = self.small_bins[target_bin].level_percent
            elif target_bin.startswith('S'):
                if hasattr(self, 'view') and self.view:
                    silo = self.view.silo_compartments.get(target_bin)
                    if silo:
                        level = (silo.get('current_level', 0) / silo.get('capacity', 100)) * 100

            # 缓存序列为空（最后一个料仓）且料位≥80%时，提前请求下一轮调度
            if ctx.assigned_cart in ('Cart1', 'Cart2', 'Cart3') and level >= 80.0:
                cart_to_belt = {'Cart1': 'D7', 'Cart2': 'D8', 'Cart3': 'D9'}
                belt_id = cart_to_belt.get(ctx.assigned_cart, '')
                if belt_id and belt_id not in self._scheduled_sequence:
                    print(f"[调度] {belt_id} 最后一个料仓{target_bin}料位{level:.0f}%≥80%，提前请求调度", flush=True)
                    self._request_immediate_scheduling(belt_id)

            # 每30秒打印一次诊断（帮助定位长时间FEEDING卡死问题）
            diag_key = f'_feed_diag_{route_id}'
            if not hasattr(self, diag_key):
                setattr(self, diag_key, 0.0)
            last_diag = getattr(self, diag_key)
            if feeding_elapsed > 60.0 and self.total_runtime - last_diag > 30.0:
                setattr(self, diag_key, self.total_runtime)
                belt_status = []
                route_cfg = config.FEED_ROUTES.get(route_id, {})
                for cid in route_cfg.get('conveyors', []):
                    cv = self.conveyors.get(cid)
                    belt_status.append(f"{cid}={'R' if cv and cv.is_running else 'S'}")
                print(f"[FEED-STUCK] {route_id} target={target_bin} level={level:.1f}% threshold={threshold}% "
                      f"elapsed={feeding_elapsed:.0f}s belts=[{','.join(belt_status)}] "
                      f"feed_timer={self.feed_timer.isActive()}", flush=True)

            if level >= threshold:
                self.route_state_manager.trigger_clearing(route_id)
                strategy = getattr(ctx, 'clearing_strategy', 'reverse')

                # 立即关闭所有中转斗（清空时物料只进不出，囤积在斗内）
                for hopper_id in ctx.assigned_hoppers:
                    if hopper_id in self.hoppers:
                        self.hoppers[hopper_id].is_open = False

                # 顺序策略：立即停止终点皮带
                if strategy == 'sequential':
                    route = config.FEED_ROUTES.get(route_id)
                    if route and route['conveyors']:
                        final_conveyor = route['conveyors'][-1]
                        if final_conveyor in self.conveyors:
                            self.conveyors[final_conveyor].stop()
                    ctx.clearing_start_time = self.total_runtime

    def _check_clearing_completion(self):
        """检查CLEARING状态的路线是否完成余料清空（支持策略差异化）"""
        for route_id in list(self.active_routes):
            ctx = self.route_state_manager.get_route_context(route_id)
            if not ctx or ctx.state != RouteState.CLEARING:
                continue

            strategy = getattr(ctx, 'clearing_strategy', 'reverse')
            route = config.FEED_ROUTES.get(route_id)
            if not route:
                continue

            should_complete = False

            route_conveyors = route.get('conveyors', [])
            final_conveyor = route_conveyors[-1] if route_conveyors else None

            if strategy == 'sequential':
                # D7/D8顺序策略：3s后进入MOVING_TO_TARGET，小车移动，非终点皮带保持运行清空余料
                cart_id = ctx.assigned_cart
                if cart_id in ('Cart1', 'Cart2') and not ctx.early_moved_from_clearing:
                    clearing_elapsed = self.total_runtime - ctx.clearing_start_time
                    if clearing_elapsed >= 3.0:
                        cart_to_belt = {'Cart1': 'D7', 'Cart2': 'D8', 'Cart3': 'D9'}
                        belt_id = cart_to_belt.get(cart_id, '')
                        seq = self._scheduled_sequence.get(belt_id, [])
                        if seq:
                            next_bin = seq.pop(0)
                            if not seq:
                                self._scheduled_sequence.pop(belt_id, None)
                            try:
                                next_pos = int(next_bin.split('-')[1])
                            except (ValueError, IndexError):
                                next_pos = 1
                            print(f"[提前移动] {route_id} 顺序清空3s，进入MOVING_TO_TARGET → {next_bin}", flush=True)
                            self.route_state_manager.early_move_from_clearing(route_id, next_bin, next_pos)
                            self.cart_target_positions[cart_id] = next_pos
                            self.route_to_bin[route_id] = next_bin
                            # 更新分料方向（跨列移动时切换P2↔P3）
                            expected_divert = self._calculate_cart_divert(cart_id, next_bin)
                            self.cart_divert[cart_id] = expected_divert
                            continue

                if ctx.early_moved_from_clearing:
                    continue

                # 顺序：终点皮带已停止，检查非终点皮带物料是否全部清空进入中转斗
                has_material = False
                for material in self.active_materials:
                    if not material.is_active or not material.current_conveyor:
                        continue
                    if material.current_conveyor in route_conveyors and material.current_conveyor != final_conveyor:
                        has_material = True
                        break
                if not has_material:
                    should_complete = True
            else:
                # 反序 / 换列：检查路线上所有皮带是否还有物料
                has_material = False
                for material in self.active_materials:
                    if not material.is_active or not material.current_conveyor:
                        continue
                    if material.current_conveyor in route_conveyors:
                        has_material = True
                        break
                if not has_material:
                    should_complete = True

            if should_complete:
                self.route_state_manager.complete_clearing(route_id)
                if route_id not in self._pending_stop_routes:
                    ctx_after = self.route_state_manager.get_route_context(route_id)
                    if ctx_after and ctx_after.state == RouteState.WAITING:
                        # 换列：清空完成后停止终点皮带并关闭中转斗
                        # 反序/顺序：同样关闭中转斗和终点皮带（顺序时皮带已停）
                        for hopper_id in ctx_after.assigned_hoppers:
                            if hopper_id in self.hoppers:
                                self.hoppers[hopper_id].is_open = False
                        if route and route['conveyors']:
                            final_conveyor = route['conveyors'][-1]
                            if final_conveyor in self.conveyors:
                                self.conveyors[final_conveyor].stop()

    def _apply_clearing_strategy_actions(self):
        """清空策略差异化动作：换列时保持中转斗和皮带开启，不屯料"""
        for route_id in list(self.active_routes):
            ctx = self.route_state_manager.get_route_context(route_id)
            if not ctx or ctx.state != RouteState.CLEARING:
                continue
            strategy = getattr(ctx, 'clearing_strategy', 'reverse')
            if strategy == 'column_switch':
                # 换列：覆盖控制策略生成器关闭中转斗的行为，保持开启不屯料
                for hopper_id in ctx.assigned_hoppers:
                    if hopper_id in self.hoppers:
                        hopper = self.hoppers[hopper_id]
                        hopper.is_open = True
                        hopper.current_weight = 0.0
                        # 阻止称重累加，换列时中转斗不屯料
                        ctx.current_weights[hopper_id] = 0.0
                        # 覆盖生成器写入的数据
                        self.sensor_data_manager.write_hopper_switch(hopper_id, True)
                        self.sensor_data_manager.write_hopper_weight(hopper_id, 0.0)
                # 确保终点皮带保持运行
                route = config.FEED_ROUTES.get(route_id)
                if route and route['conveyors']:
                    final_conveyor = route['conveyors'][-1]
                    if final_conveyor in self.conveyors:
                        conv = self.conveyors[final_conveyor]
                        if not conv.is_running:
                            conv.start(self.speed)

    def _check_pending_stop_routes(self):
        """检查待停止路线是否完成余料清空"""
        for route_id in list(self._pending_stop_routes):
            ctx = self.route_state_manager.get_route_context(route_id)
            if not ctx:
                # 路线不存在，完成停止
                self._pending_stop_routes.discard(route_id)
                continue

            # 检查是否到达WAITING状态（余料清空完成）
            if ctx.state == RouteState.WAITING:
                self._complete_stop_route(route_id)

    def _generate_sensor_data(self, delta_seconds: float = 0.0):
        """
        生成传感器数据并写入JSON文件
        使用控制策略生成器生成数据
        """
        # 获取小车位置
        cart_positions = {
            'Cart1': self.cart_positions.get('Cart1', 1),
            'Cart2': self.cart_positions.get('Cart2', 1),
            'Cart3': self.cart_positions.get('Cart3', 1),
            'Cart4': self.cart4_position,
        }

        # 使用控制策略生成器生成数据
        self.control_strategy_generator.generate_all_data(
            active_routes=self.active_routes,
            hoppers=self.hoppers,
            conveyors=self.conveyors,
            materials=self.active_materials,
            cart_positions=cart_positions,
            small_bins=self.small_bins,
            silo_compartments=self.view.silo_compartments if hasattr(self, 'view') and self.view else None,
            delta_seconds=delta_seconds
        )

        # 更新 TCP 发送器数据缓冲区
        self._update_tcp_data()

    def _update_tcp_data(self):
        """收集传感器数据并更新 TCP 发送器缓冲区"""
        data = {
            "sensors": self.sensor_data_manager.read_all_sensors(),
            "hoppers": self.sensor_data_manager.read_all_hopper_data(),
            "conveyor_sensors": self.sensor_data_manager.read_conveyor_speeds(),
            "cart_sensors": self.sensor_data_manager.read_cart_sensors(),
            "feed_signals": self.sensor_data_manager.read_feed_signals(),
            "route_states": self.route_state_manager.get_all_route_states(),
        }
        self.tcp_sender.update_data(data)

        if self._tcp_diagnosis_client is not None:
            self._tcp_diagnosis_client.update_data(data)

        # 调度数据推送已移至 push_scheduling_data()（由 main_window 定时调用）
        # 确保仿真未启动时也能正常收发调度数据

    def _build_bins_for_scheduling(self, belt_id: str) -> list:
        bin_ids = BELT_BINS.get(belt_id, [])
        bins = []
        for bin_id in bin_ids:
            maintenance = bin_id in self._maintenance_bins
            rate = self._consumption_rates.get(bin_id, 0.01)
            if belt_id == 'D6':
                if hasattr(self, 'view') and self.view:
                    comp = self.view.silo_compartments.get(bin_id)
                    if comp:
                        bins.append({
                            "bin_id": bin_id,
                            "stock": round(comp.get('current_level', 0), 2),
                            "consumption_rate": rate,
                            "maintenance": maintenance,
                            "has_future_order": False,
                        })
            else:
                sb = self.small_bins.get(bin_id)
                if sb:
                    bins.append({
                        "bin_id": bin_id,
                        "stock": round(sb.current_level, 2),
                        "consumption_rate": rate,
                        "maintenance": maintenance,
                        "has_future_order": False,
                    })
        return bins

    def start_tcp_sender(self):
        """启动 TCP 下位机通信"""
        self.tcp_sender.start()

    def stop_tcp_sender(self):
        """停止 TCP 下位机通信"""
        self.tcp_sender.stop()

    @property
    def is_tcp_connected(self) -> bool:
        return self.tcp_sender.is_connected

    def start_udp_sender(self):
        """启动 UDP 二进制帧发送"""
        self.udp_sender.start()

    def stop_udp_sender(self):
        """停止 UDP 二进制帧发送"""
        self.udp_sender.stop()

    @property
    def is_udp_sending(self) -> bool:
        return self.udp_sender._active

    # ============ TCP 诊断客户端 ============

    def set_diagnosis_mode(self, mode: str):
        self._diagnosis_mode = mode

    def start_tcp_diagnosis(self):
        if self._tcp_diagnosis_client is not None:
            return
        self._tcp_diagnosis_client = TcpDiagnosisClient()
        self._tcp_diagnosis_client.results_received.connect(self._on_tcp_diagnosis_results)
        self._tcp_diagnosis_client.start()

    def stop_tcp_diagnosis(self):
        if self._tcp_diagnosis_client is None:
            return
        self._tcp_diagnosis_client.stop()
        self._tcp_diagnosis_client = None

    def _on_tcp_diagnosis_results(self, results):
        now = self.total_runtime
        for r in results:
            if r.confidence >= 0.7:
                key = f"{r.sensor_id}:{r.fault_type}"
                self._accumulated_diagnosis[key] = (now, r)
                self._raise_alarm('SENSOR_FAULT', r.description, alarm_key=key)

        stale_keys = [
            k for k, (ts, _) in self._accumulated_diagnosis.items()
            if now - ts > 35.0
        ]
        for k in stale_keys:
            del self._accumulated_diagnosis[k]

        accumulated = [r for _, r in self._accumulated_diagnosis.values()]
        self.diagnosis_result = [
            (r.sensor_id, r.description) for r in accumulated
        ]
        self._full_diagnosis_results = accumulated

    def get_tcp_diagnosis_status(self) -> bool:
        if self._tcp_diagnosis_client is None:
            return False
        return self._tcp_diagnosis_client.is_connected

    # ============ 手动/自动模式切换 ============

    def set_belt_auto_mode(self, belt_id: str, enabled: bool):
        """设置单条终点皮带的自动/手动模式"""
        self._belt_auto_mode[belt_id] = enabled
        if enabled and self._auto_feeding_active and self._tcp_scheduling_client is not None:
            self._request_immediate_scheduling(belt_id)

    def is_belt_auto_mode(self, belt_id: str) -> bool:
        """查询单条终点皮带是否处于自动模式"""
        return self._belt_auto_mode.get(belt_id, False)

    def set_auto_mode(self, enabled: bool):
        """兼容包装：统一设置所有皮带模式"""
        for b in ['D6', 'D7', 'D8', 'D9']:
            self._belt_auto_mode[b] = enabled
        self._auto_mode = enabled
        if enabled and self._auto_feeding_active and self._tcp_scheduling_client is not None:
            for belt_id in ['D6', 'D7', 'D8', 'D9']:
                self._request_immediate_scheduling(belt_id)

    def is_auto_mode(self) -> bool:
        """兼容包装：任意皮带处于自动模式则返回True"""
        return any(self._belt_auto_mode.values())

    # ---- 检修管理 ----

    def add_maintenance_bin(self, bin_id: str):
        self._maintenance_bins.add(bin_id)

    def remove_maintenance_bin(self, bin_id: str):
        self._maintenance_bins.discard(bin_id)

    def add_maintenance_line(self, line_num: int):
        """产线检修：该产线的所有4个配料站料仓全部检修"""
        for col in ['P1', 'P2', 'P3', 'P4']:
            self._maintenance_bins.add(f"{col}-{line_num}")

    def remove_maintenance_line(self, line_num: int):
        for col in ['P1', 'P2', 'P3', 'P4']:
            self._maintenance_bins.discard(f"{col}-{line_num}")

    def get_maintenance_bins(self) -> list:
        return sorted(self._maintenance_bins)

    def is_bin_maintenance(self, bin_id: str) -> bool:
        return bin_id in self._maintenance_bins

    def push_scheduling_data(self):
        """推送料仓数据到调度客户端（独立于仿真运行状态）"""
        if self._tcp_scheduling_client is not None:
            cart_map = {'D7': 'Cart1', 'D8': 'Cart2', 'D9': 'Cart3'}
            for belt_id in ['D6', 'D7', 'D8', 'D9']:
                bins = self._build_bins_for_scheduling(belt_id)
                if belt_id == 'D6':
                    cart_pos = self.cart4_position
                    left_div, right_div = True, False
                else:
                    cart_id = cart_map.get(belt_id, '')
                    cart_pos = self.cart_positions.get(cart_id, 1)
                    left_div, right_div = self.cart_divert.get(cart_id, (False, False))
                self._tcp_scheduling_client.update_bins(belt_id, bins, cart_pos, left_div, right_div)

    # ============ TCP 调度客户端 ============

    def start_tcp_scheduling(self):
        if self._tcp_scheduling_client is not None:
            self._tcp_scheduling_client.stop()
            self._tcp_scheduling_client = None
        self._tcp_scheduling_client = TcpSchedulingClient()
        self._tcp_scheduling_client.schedule_received.connect(self._on_tcp_schedule_received)
        self._tcp_scheduling_client.connection_changed.connect(self._on_scheduling_connection_changed)
        self._tcp_scheduling_client.send_error.connect(self._on_scheduling_error)
        self._tcp_scheduling_client.start()
        self._auto_feeding_active = True
        # 启动调度服务时自动启用所有皮带自动模式
        for belt_id in ['D6', 'D7', 'D8', 'D9']:
            self._belt_auto_mode[belt_id] = True
        # 延迟0.5s等TCP连接建立后再请求调度
        def _delayed_request():
            import time
            time.sleep(0.5)
            for belt_id in ['D6', 'D7', 'D8', 'D9']:
                if self._tcp_scheduling_client:
                    self._request_immediate_scheduling(belt_id)
        import threading
        threading.Thread(target=_delayed_request, daemon=True).start()

    def _on_scheduling_connection_changed(self, belt_id: str, connected: bool):
        status = "已连接" if connected else "已断开"
        self._raise_alarm('SCHEDULING', f"调度服务 {belt_id} {status}",
                        alarm_key=f"sched_conn_{belt_id}")

    def _on_scheduling_error(self, belt_id: str, msg: str):
        self._raise_alarm('SCHEDULING', f"调度服务 {belt_id} 通信错误: {msg}",
                        alarm_key=f"sched_err_{belt_id}")

    def stop_tcp_scheduling(self):
        self._auto_feeding_active = False
        self._executing_bin.clear()
        self._executing_route.clear()
        if self._tcp_scheduling_client is None:
            return
        self._tcp_scheduling_client.stop()
        self._tcp_scheduling_client = None
        self._tcp_schedules.clear()
        self._scheduled_sequence.clear()

    def _on_tcp_schedule_received(self, belt_id, result):
        self._tcp_schedules[belt_id] = result

        if not self._auto_feeding_active or not self._belt_auto_mode.get(belt_id, False):
            return

        seq = result.get('sequence', [])
        if not seq:
            # D8皮带：下一轮无需补料时，当前FEEDING路线改用换列规则（阈值88%）
            if belt_id == 'D8' and belt_id in self._executing_route:
                route_id = self._executing_route[belt_id]
                ctx = self.route_state_manager.get_route_context(route_id)
                if ctx and ctx.state == RouteState.FEEDING:
                    # 当前序列还有剩余（非最后一仓）→ 换列清空
                    remaining = self._scheduled_sequence.get(belt_id, [])
                    if remaining:
                        ctx.clearing_strategy = 'column_switch'
                        print(f"[调度] {belt_id} 无需补料，当前{ctx.target_bin}清空策略→换列(88%)", flush=True)
            self._stop_waiting_route_conveyors(belt_id)
            self._scheduled_sequence.pop(belt_id, None)
            return

        # 皮带正忙（正在上料/清空中）：缓存完整序列，等当前路线完成后使用
        if belt_id in self._executing_route:
            # 若序列首项与当前执行料仓相同则跳过（服务端可能从当前仓开始）
            current_bin = self._executing_bin.get(belt_id)
            if current_bin and seq[0] == current_bin:
                self._scheduled_sequence[belt_id] = list(seq[1:])
            else:
                self._scheduled_sequence[belt_id] = list(seq)
            route_name = config.FEED_ROUTES.get(
                self._executing_route[belt_id], {}).get('name', belt_id)
            print(f"[调度] {belt_id} 收到序列: {seq} (已缓存，等待{route_name}完成)", flush=True)
            return

        # 皮带空闲：启动序列首项，成功后才缓存剩余
        first_bin = seq[0]
        remaining = list(seq[1:]) if len(seq) > 1 else []
        print(f"[调度] {belt_id} 收到序列: {seq} -> 立即执行{first_bin}", flush=True)
        if self._start_scheduled_route(belt_id, first_bin):
            if remaining:
                self._scheduled_sequence[belt_id] = remaining
            print(f"[调度] {belt_id} 缓存剩余序列: {remaining}", flush=True)
        else:
            self._scheduled_sequence.pop(belt_id, None)
            print(f"[调度] {belt_id} 启动失败，清除缓存等待下次触发", flush=True)

    def _start_scheduled_route(self, belt_id: str, first_bin: str) -> bool:
        """启动调度结果中指定的路线，返回是否成功启动"""
        if belt_id == 'D6':
            route_id = 'route5'
            feed_point = 'feed2_2'
        else:
            feed_point, route_id = self._select_feed_point(first_bin)
            if route_id is None:
                print(f"[调度] {belt_id} 无可用路线 for {first_bin}", flush=True)
                return False

        print(f"[调度] {belt_id} 选中 {route_id} feed={feed_point} 目标={first_bin}", flush=True)
        self.set_route_target_bin(route_id, first_bin)

        if not self.is_route_available(route_id):
            print(f"[调度] {belt_id} {route_id} 上料点无原料", flush=True)
            return False

        ctx = self.route_state_manager.get_route_context(route_id)
        print(f"[调度] {belt_id} {route_id} 当前状态={ctx.state.value if ctx else 'None'}, 分配={ctx.assigned_cart if ctx else 'None'}", flush=True)

        if ctx and ctx.state == RouteState.STANDBY:
            success = self._resume_from_standby(route_id, belt_id, first_bin, feed_point)
        else:
            success = self.start_route(route_id)
        if success:
            self._executing_route[belt_id] = route_id
            self._executing_bin[belt_id] = first_bin
            bin_name = first_bin
            route_name = config.FEED_ROUTES.get(route_id, {}).get('name', route_id)
            print(f"[上料] {route_name} → {bin_name} 开始（上料点：{feed_point}）", flush=True)
            return True
        return False

    def _select_feed_point(self, bin_id: str) -> tuple:
        available = config.BIN_TO_AVAILABLE_ROUTES.get(bin_id, [])
        if not available:
            return None, None

        prefix = bin_id.split('-')[0]
        priority_map = config.FEED_POINT_PRIORITY.get(prefix, {})

        candidates = []
        for feed_point, route_id in available:
            if feed_point in config.FEED_POINTS_WITH_LASER:
                has_material = self.laser_sensor_states.get(feed_point, False)
            else:
                has_material = True

            priority = priority_map.get(feed_point, 99)

            if prefix == 'P4' and feed_point == 'feed3':
                if self._p2p3_has_pending_task():
                    continue

            candidates.append((feed_point, route_id, has_material, priority))

        candidates.sort(key=lambda x: (not x[2], x[3]))

        if candidates:
            return candidates[0][0], candidates[0][1]
        return None, None

    def _p2p3_has_pending_task(self) -> bool:
        for belt_id in ['D8']:
            if belt_id in self._executing_bin:
                return True
        return False

    def _get_default_silo_bin(self, bin_id: str) -> str:
        parts = bin_id.split('-')
        if len(parts) == 2:
            row = parts[1]
            return f'S{row}'
        return 'S1'

    def _on_auto_feed_route_completed(self, route_id: str):
        for belt_id, r in list(self._executing_route.items()):
            if r == route_id:
                del self._executing_route[belt_id]
                del self._executing_bin[belt_id]

                # 从缓存序列中取出下一个料仓执行
                seq = self._scheduled_sequence.get(belt_id, [])
                if seq:
                    next_bin = seq.pop(0)
                    if not seq:
                        self._scheduled_sequence.pop(belt_id, None)
                    print(f"[调度] {belt_id} 使用缓存序列 -> {next_bin}，剩余{seq}", flush=True)
                    if not self._start_scheduled_route(belt_id, next_bin):
                        self._scheduled_sequence.pop(belt_id, None)
                        print(f"[调度] {belt_id} 启动{next_bin}失败，重新请求调度", flush=True)
                        self._request_immediate_scheduling(belt_id)
                else:
                    self._scheduled_sequence.pop(belt_id, None)
                    print(f"[调度] {belt_id} 序列耗尽，请求调度 (force)", flush=True)
                    self._request_immediate_scheduling(belt_id, force=True)
                break

    def _check_auto_feed_idle(self):
        """自动上料空闲检测：皮带无执行路线且无缓存序列时，检查料仓是否需要触发调度

        紧急规则：若皮带负责的任意料仓低于 10%（11t），立即重新请求调度（覆盖当前缓存）。
        """
        if not self._auto_feeding_active:
            return
        for belt_id in ['D6', 'D7', 'D8', 'D9']:
            if not self._belt_auto_mode.get(belt_id, False):
                continue
            # 紧急检测：任意料仓低于10%时立即重新请求调度
            bins = self._build_bins_for_scheduling(belt_id)
            any_emergency = any(b['stock'] < 11.0 for b in bins if not b.get('maintenance'))
            if any_emergency:
                last_req = self._last_emergency_schedule.get(belt_id, 0)
                if self.total_runtime - last_req >= 120.0:
                    self._last_emergency_schedule[belt_id] = self.total_runtime
                    print(f"[调度] {belt_id} 紧急触发: 存在料仓低于10%", flush=True)
                    self._request_immediate_scheduling(belt_id, force=True)
                continue

            # 空闲检测：有执行路线或有缓存序列则跳过
            if belt_id in self._executing_route:
                continue
            if belt_id in self._scheduled_sequence:
                continue  # 有缓存序列，按序执行（含空列表表示序列刚被清空等待确认）
            last_req = self._last_auto_schedule_request.get(belt_id, 0)
            if self.total_runtime - last_req < 10.0:
                continue
            # D6皮带（高位储料仓420t）使用80%阈值=336t，其他皮带70t
            idle_threshold = SILO_MAX_CAP * 0.8 if belt_id == 'D6' else 70.0
            any_below = any(b['stock'] < idle_threshold for b in bins if not b.get('maintenance'))
            if any_below:
                self._request_immediate_scheduling(belt_id)

    def _stop_waiting_route_conveyors(self, belt_id: str):
        """调度返回无需补料时，将WAITING路线转入STANDBY状态并停止全部皮带以节能"""
        for route_id in list(self.active_routes):
            ctx = self.route_state_manager.get_route_context(route_id)
            if not ctx or ctx.state != RouteState.WAITING:
                continue
            route = config.FEED_ROUTES.get(route_id)
            if not route or not route['conveyors']:
                continue
            if route['conveyors'][-1] == belt_id:
                self.route_state_manager.enter_standby(route_id)
                for conv_id in route['conveyors']:
                    if conv_id in self.conveyors:
                        self.conveyors[conv_id].stop()
                for hopper_id in ctx.assigned_hoppers:
                    if hopper_id in self.hoppers:
                        self.hoppers[hopper_id].is_open = False

    def _resume_from_standby(self, route_id: str, belt_id: str, first_bin: str, feed_point: str) -> bool:
        """从STANDBY恢复：退出待机，启动非终点皮带，设置小车目标"""
        route = config.FEED_ROUTES.get(route_id)
        if not route:
            return False

        if not self.route_state_manager.exit_standby(route_id):
            return False

        final_conveyor = route['conveyors'][-1] if route['conveyors'] else None
        for conv_id in route['conveyors']:
            if conv_id != final_conveyor:
                if conv_id in self.conveyors:
                    self.conveyors[conv_id].start(self.speed)
        if final_conveyor and final_conveyor in self.conveyors:
            self.conveyors[final_conveyor].stop()

        self._set_cart_target_position(route_id, first_bin)

        bin_name = first_bin
        route_name = route.get('name', route_id)
        print(f"[上料] {route_name} → {bin_name} 开始（上料点：{feed_point}，从待机恢复）", flush=True)
        return True

    def _request_immediate_scheduling(self, belt_id: str, force: bool = False):
        if self._tcp_scheduling_client is None:
            return
        last_req = self._last_auto_schedule_request.get(belt_id)
        if not force and last_req is not None and self.total_runtime - last_req < 120.0:
            return
        self._last_auto_schedule_request[belt_id] = self.total_runtime
        bins = self._build_bins_for_scheduling(belt_id)
        cart_map = {'D7': 'Cart1', 'D8': 'Cart2', 'D9': 'Cart3'}
        if belt_id == 'D6':
            cart_pos = self.cart4_position
            left_div, right_div = True, False
        else:
            cart_id = cart_map.get(belt_id, '')
            cart_pos = self.cart_positions.get(cart_id, 1)
            left_div, right_div = self.cart_divert.get(cart_id, (False, False))
        self._tcp_scheduling_client.update_bins(belt_id, bins, cart_pos, left_div, right_div)
        self._tcp_scheduling_client.request_schedule(belt_id)
        print(f"[调度] {belt_id} 请求调度计算... (pos={cart_pos} L={left_div} R={right_div})", flush=True)

    def get_tcp_scheduling_status(self) -> dict:
        if self._tcp_scheduling_client is None:
            return {}
        return dict(self._tcp_scheduling_client._connected)

    def get_latest_schedules(self) -> dict:
        return dict(self._tcp_schedules)

    def _update_hoppers(self, delta_seconds: float):
        """更新中转斗状态（释放速率 0.195 t/s，与上料点出料速度一致）"""
        for hopper_id, hopper in self.hoppers.items():
            effective_open = hopper.get_effective_switch_state()

            if effective_open and len(hopper.stored_materials) > 0:
                output_cons = hopper.output_conveyor
                if isinstance(output_cons, list):
                    output_conv_ids = output_cons
                else:
                    output_conv_ids = [output_cons]

                # 速率控制：累积释放预算（0.195 t/s）
                if not hasattr(hopper, '_release_budget'):
                    hopper._release_budget = 0.0
                hopper._release_budget += self.feed_rate * delta_seconds

                while hopper._release_budget >= config.MATERIAL_WEIGHT and len(hopper.stored_materials) > 0:
                    released = False
                    for output_id in output_conv_ids:
                        cv = self.conveyors.get(output_id)
                        if cv and cv.is_running:
                            released_material = hopper.release_material()
                            if released_material:
                                hopper._release_budget -= config.MATERIAL_WEIGHT
                                mt = released_material.material_type
                                nm = MaterialFactory.create_material(hopper.position, mt)
                                nm.route_id = released_material.route_id
                                nm.enter_conveyor(output_id, 0)
                                nm.total_distance = 0
                                nm.current_hopper = None
                                self.materials.append(nm)
                                self.active_materials.append(nm)
                                self.material_spawned.emit(nm)
                                released = True
                            break
                    if not released:
                        hopper._release_budget = 0.0
                        break

            # 更新故障诊断系统的中转斗状态
            self.fault_diagnosis.update_hopper_states(
                hopper_id,
                effective_open,
                hopper.get_display_weight(),
                hopper.belt_speed_multiplier
            )


    def _update_materials(self, delta_seconds: float):
        """更新物料位置"""
        # 先更新所有物料的位置，然后再更新小车4位置
        # 这样可以确保物料在当前帧的小车位置进行检查

        for material in self.active_materials[:]:
            if not material.is_active or not material.current_conveyor:
                continue

            # 检查物料是否在站台等待放料
            if material.waiting_at_station:
                material.discharge_timer += delta_seconds
                # 放料完成（缩短到0.1秒，每秒可处理10个物料）
                if material.discharge_timer >= 0.1:
                    self._discharge_material_to_bin(material)
                continue

            conveyor = self.conveyors.get(material.current_conveyor)
            if not conveyor:
                continue

            # 检查是否是D7/D8/D9皮带（需要检测小车位置）
            if material.current_conveyor in ('D7', 'D8', 'D9'):
                # 检查物料是否到达小车位置
                if self._check_material_at_cart_position(material, conveyor):
                    continue  # 物料已停止等待放料

            # 检查是否是D6皮带（路线⑤，用于高位储料仓补料）
            if material.current_conveyor == 'D6':
                # 检查物料是否到达小车4位置
                if self._check_material_at_cart4_position(material, conveyor):
                    continue  # 物料已停止等待放料

                # 防止物料越过小车4位置
                self._prevent_material_passing_cart4(material, conveyor)

            if not conveyor.is_running:
                continue

            # 计算移动距离（考虑皮带速度倍率）
            # 现在 conveyor.current_speed 是像素/秒，distance_on_conveyor 使用像素单位
            speed_multiplier = self._get_conveyor_speed_multiplier(material.current_conveyor)
            pixel_distance = conveyor.current_speed_pps * speed_multiplier * delta_seconds
            material.distance_on_conveyor += pixel_distance
            material.total_distance += pixel_distance

            # 检查是否到达皮带末端（使用像素长度）
            if material.distance_on_conveyor >= conveyor.pixel_length:
                self._handle_conveyor_end(material)
            else:
                # 更新位置
                new_pos = conveyor.get_position_at_distance(material.distance_on_conveyor)
                material.update_position(new_pos)
                self.material_moved.emit(material)

        # 更新小车4位置（在所有物料检查之后）
        self.update_cart4_position(delta_seconds)

    def _get_conveyor_speed_multiplier(self, conv_id: str) -> float:
        """获取皮带的故障速度倍率"""
        for hopper_id, hopper in self.hoppers.items():
            # 检查input_conveyor（可能是列表或单个值）
            input_cons = hopper.input_conveyor
            if isinstance(input_cons, list):
                in_list = conv_id in input_cons
            else:
                in_list = (input_cons == conv_id)

            # 检查output_conveyor（可能是列表或单个值）
            output_cons = hopper.output_conveyor
            if isinstance(output_cons, list):
                out_list = conv_id in output_cons
            else:
                out_list = (output_cons == conv_id)

            if in_list or out_list:
                return hopper.belt_speed_multiplier
        return 1.0

    def _check_material_at_cart_position(self, material: Material, conveyor) -> bool:
        """检查物料是否到达小车位置，如果是则停止并开始放料"""
        route_id = material.route_id
        target_bin_id = self.route_to_bin.get(route_id)

        if not target_bin_id:
            return False

        # 获取小车停靠位置的距离
        stop_distance = conveyor.get_distance_for_bin(target_bin_id)

        # 检查物料是否到达小车位置（误差范围内）
        if material.distance_on_conveyor >= stop_distance - 1:  # 1像素误差
            # 物料到达小车位置，停止在皮带上的移动
            material.distance_on_conveyor = stop_distance
            material.update_position(conveyor.get_position_at_distance(stop_distance))
            material.waiting_at_station = True
            material.discharge_timer = 0
            self.material_moved.emit(material)
            return True

        return False

    def _check_material_at_cart4_position(self, material: Material, conveyor) -> bool:
        """检查物料是否到达小车4位置（D6皮带，高位储料仓补料）

        路线⑤的物料在D6皮带上移动，当到达小车4位置时停止并放料到储料仓。
        """
        route_id = material.route_id

        # 只处理路线⑤
        if route_id != 'route5':
            return False

        target_bin_id = self.route_to_bin.get(route_id)
        if not target_bin_id:
            return False

        # 获取小车4位置对应的皮带距离
        # D6皮带长度对应的像素长度
        belt_pixel_length = conveyor.pixel_length

        # 小车4位置1-6对应皮带上的位置
        # 位置1在最左(皮带起点)，位置6在最右(皮带终点)
        cart4_position = self.cart4_position
        stop_distance = belt_pixel_length * (cart4_position / 6.0)

        # 检查物料是否到达小车4位置
        if material.distance_on_conveyor >= stop_distance - 1:  # 1像素误差
            # 物料到达小车4位置，停止在皮带上的移动
            material.distance_on_conveyor = stop_distance
            material.update_position(conveyor.get_position_at_distance(stop_distance))
            material.waiting_at_station = True
            material.discharge_timer = 0
            self.material_moved.emit(material)
            return True

        return False

    def _prevent_material_passing_cart4(self, material: Material, conveyor) -> bool:
        """防止物料越过小车4位置（路线⑤）

        在物料移动时检查并阻止物料越过小车4位置。
        """
        route_id = material.route_id

        # 只处理路线⑤
        if route_id != 'route5':
            return False

        target_bin_id = self.route_to_bin.get(route_id)
        if not target_bin_id:
            return False

        # 获取小车4位置对应的皮带距离
        belt_pixel_length = conveyor.pixel_length
        cart4_position = self.cart4_position
        stop_distance = belt_pixel_length * (cart4_position / 6.0)

        # 检查物料是否会越过小车4位置
        if material.distance_on_conveyor > stop_distance:
            # 物料越过了小车4位置，强制停止在小车4位置
            material.distance_on_conveyor = stop_distance
            material.update_position(conveyor.get_position_at_distance(stop_distance))
            material.waiting_at_station = True
            material.discharge_timer = 0
            self.material_moved.emit(material)
            return True

        return False

    def _get_bin_drop_position(self, material: Material) -> tuple:
        """获取物料下落的目标位置（小仓入口）"""
        route_id = material.route_id
        target_bin_id = self.route_to_bin.get(route_id)

        if not target_bin_id:
            return None

        # 检查是否是高位储料仓的料仓（S1-S12）
        if target_bin_id.startswith('S') and target_bin_id[1:].isdigit():
            return self._get_high_silo_drop_position(target_bin_id)

        # 获取小仓位置
        if hasattr(self, 'view') and self.view:
            bin_x, bin_y = self.view._get_small_bin_position(target_bin_id)
        else:
            # 计算小仓位置
            bs = config.BATCHING_STATION
            x, y = bs['position']
            w, h = bs['width'], bs['height']
            comp_w = (w - 20) / bs['columns']
            comp_h = (h - 30) / bs['rows']

            parts = target_bin_id.split('-')
            if len(parts) == 2:
                col_name = parts[0]
                row_num = int(parts[1]) - 1
                col_names = bs['column_names']
                if col_name in col_names:
                    col = col_names.index(col_name)
                else:
                    col = 0
                bin_x = x + 10 + col * comp_w + comp_w / 2
                bin_y = y + 20 + row_num * comp_h + comp_h / 2
            else:
                return None

        return (bin_x, bin_y)

    def _get_high_silo_drop_position(self, bin_id: str) -> tuple:
        """获取高位储料仓料仓的放料位置

        放料位置在小车4正上方，对着对应的料仓。
        """
        if not hasattr(self, 'view') or not self.view:
            return None

        # 获取料仓位置
        bin_x, bin_y = self.view._get_high_silo_bin_position(bin_id)

        # 放料位置在料仓入口上方
        # 小车4在皮带下方，落料需要向上到料仓
        drop_x = bin_x
        drop_y = bin_y - 30  # 在料仓中心上方

        return (drop_x, drop_y)

    def _discharge_material_to_bin(self, material: Material):
        """物料实际到达目标料仓时才增加料位（物料驱动，非时间驱动）"""
        route_id = material.route_id
        target_bin_id = self.route_to_bin.get(route_id)
        if not target_bin_id:
            material.is_active = False
            material.waiting_at_station = False
            return

        if target_bin_id in self.small_bins:
            small_bin = self.small_bins[target_bin_id]
            small_bin.receive_material(config.MATERIAL_WEIGHT)
            self.total_materials_sent += 1
            self.material_arrived.emit(material, target_bin_id)
        elif target_bin_id.startswith('S'):
            self._add_to_high_silo(target_bin_id, material)
            self.total_materials_sent += 1
            self.material_arrived.emit(material, target_bin_id)

        # 物料消失，从所有列表中清理
        material.is_active = False
        material.waiting_at_station = False
        if material in self.active_materials:
            self.active_materials.remove(material)
        if material in self.materials:
            self.materials.remove(material)
        if route_id and route_id in self.route_material_map:
            if material in self.route_material_map[route_id]:
                self.route_material_map[route_id].remove(material)

    def _add_to_high_silo(self, bin_id: str, material: Material):
        """将物料添加到高位储料仓的指定料仓（每个物料重量 0.1t）"""
        # 更新高位储料仓料仓的料位（每个物料重量）
        if hasattr(self, 'view') and self.view:
            if bin_id in self.view.silo_compartments:
                compartment = self.view.silo_compartments[bin_id]
                compartment['current_level'] = min(
                    compartment['current_level'] + config.MATERIAL_WEIGHT,
                    compartment['capacity']
                )

    def _handle_conveyor_end(self, material: Material):
        """处理物料到达皮带末端"""
        route_id = material.route_id
        if route_id not in config.FEED_ROUTES:
            material.is_active = False
            return

        route = config.FEED_ROUTES[route_id]
        current_conv = material.current_conveyor
        conveyors = route['conveyors']

        if current_conv not in conveyors:
            material.is_active = False
            return

        # 找到当前皮带在路线中的索引
        try:
            idx = conveyors.index(current_conv)
        except ValueError:
            material.is_active = False
            return

        # 检查是否有中转斗
        hoppers = route.get('hoppers', [])
        if hoppers and idx < len(hoppers):
            hopper_id = hoppers[idx]
            # 检查hopper_id是否有效（非空、非None、且在hoppers字典中）
            if hopper_id and hopper_id in self.hoppers:
                hopper = self.hoppers[hopper_id]
                effective_open = hopper.get_effective_switch_state()

                if effective_open:
                    # 开关开着：物料直通，不存储
                    hopper.receive_material_direct()
                    material.current_hopper = hopper_id
                    material.enter_hopper()
                    # 从所有列表中移除
                    if material in self.active_materials:
                        self.active_materials.remove(material)
                    if material in self.materials:
                        self.materials.remove(material)
                    # 立即在下一皮带上生成新物料
                    if idx + 1 < len(conveyors):
                        nc = conveyors[idx + 1]
                        cv = self.conveyors.get(nc)
                        if cv and cv.is_running:
                            sp = hopper.position
                            mt = material.material_type
                            nm = MaterialFactory.create_material(sp, mt)
                            nm.route_id = route_id
                            nm.enter_conveyor(nc, 0)
                            nm.total_distance = 0
                            nm.current_hopper = None
                            self.materials.append(nm)
                            self.active_materials.append(nm)
                            self.material_spawned.emit(nm)
                else:
                    # 开关关着：物料存储在斗中，不进入下一皮带
                    hopper.store_material(material, self.total_runtime)
                    material.current_hopper = hopper_id
                    material.enter_hopper()
                    # 从所有列表中移除
                    if material in self.active_materials:
                        self.active_materials.remove(material)
                    if material in self.materials:
                        self.materials.remove(material)
                    # 不生成新物料到下一皮带，因为斗被阻塞
                return

        # 没有中转斗，继续正常流程
        if idx + 1 < len(conveyors):
            next_conv = conveyors[idx + 1]
            next_conveyor = self.conveyors.get(next_conv)

            if next_conveyor and next_conveyor.is_running:
                material.current_conveyor = next_conv
                material.distance_on_conveyor = 0
            else:
                conveyor = self.conveyors[current_conv]
                material.update_position(conveyor.end_pos)
                material.distance_on_conveyor = conveyor.pixel_length
        else:
            # 到达终点（配料站或储料仓）
            conveyor = self.conveyors.get(current_conv)

            # 特殊处理D6皮带（路线⑤，高位储料仓补料）
            if current_conv == 'D6' and route_id == 'route5':
                target_bin_id = self.route_to_bin.get(route_id)
                if target_bin_id and conveyor:
                    # 计算小车4位置作为停止点
                    belt_pixel_length = conveyor.pixel_length
                    cart4_position = self.cart4_position
                    stop_distance = belt_pixel_length * (cart4_position / 6.0)
                    stop_pos = conveyor.get_position_at_distance(stop_distance)
                    material.update_position(stop_pos)
                    material.distance_on_conveyor = stop_distance
                    material.waiting_at_station = True
                    material.discharge_timer = 0
                    self.material_moved.emit(material)
                    return

            # 检查是否有目标小仓和对应的分料小车
            target_bin_id = self.route_to_bin.get(route_id)
            if target_bin_id and conveyor:
                # 计算小车停靠位置（物料应该停在皮带上小车所在的位置）
                stop_distance = conveyor.get_distance_for_bin(target_bin_id)
                stop_pos = conveyor.get_position_at_distance(stop_distance)
                material.update_position(stop_pos)
                material.distance_on_conveyor = stop_distance
                material.waiting_at_station = True  # 标记物料在站台等待放料

                # 触发物料到达站台信号（但不放料，让物料停留在皮带上）
                self.material_arrived.emit(material, target_bin_id)
            else:
                # 没有目标小仓，物料停在皮带终点
                if conveyor:
                    material.update_position(conveyor.end_pos)
                    material.distance_on_conveyor = conveyor.pixel_length
            return

        # 更新新位置
        conveyor = self.conveyors.get(material.current_conveyor)
        if conveyor:
            new_pos = conveyor.get_position_at_distance(material.distance_on_conveyor)
            material.update_position(new_pos)
        self.material_moved.emit(material)

    def _schedule_hopper_release(self, route_id: str, hopper_id: str, prev_conveyor_id: str):
        """安排中转斗放料到下一皮带（延迟模拟）"""
        route = config.FEED_ROUTES.get(route_id)
        if not route:
            return

        hoppers = route.get('hoppers', [])
        conveyors = route['conveyors']

        try:
            hopper_idx = hoppers.index(hopper_id)
        except ValueError:
            return

        # 找到下一个皮带
        if hopper_idx + 1 >= len(conveyors):
            return

        next_conv_id = conveyors[hopper_idx + 1]
        next_conveyor = self.conveyors.get(next_conv_id)
        if not next_conveyor or not next_conveyor.is_running:
            return

        # 创建新物料在中转斗出口位置
        hopper = self.hoppers.get(hopper_id)
        if hopper and hopper.current_level > 0:
            hopper.send_material()
            start_pos = hopper.position
            # 使用与起点相同的物料类型缓存
            material_types = route.get('material_types', ['stone_powder'])

            # 特殊处理路线7和9：根据选择的小仓列决定物料类型
            if route_id in ('route6', 'route8') and material_types is None:
                target_bin = self.route_to_bin.get(route_id)
                if target_bin and target_bin.startswith('P2-'):
                    material_types = ['stone_powder']
                elif target_bin and target_bin.startswith('P3-'):
                    material_types = ['aggregate_10mm']
                else:
                    material_types = ['stone_powder']

            if len(material_types) > 1:
                if route_id not in self.route_material_cache:
                    self.route_material_cache[route_id] = random.choice(material_types)
                material_type = self.route_material_cache[route_id]
            else:
                material_type = material_types[0] if material_types else 'stone_powder'
            material = MaterialFactory.create_material(start_pos, material_type)
            material.route_id = route_id
            material.current_conveyor = next_conv_id
            material.distance_on_conveyor = 0
            material.total_distance = 0
            material.current_hopper = None

            self.materials.append(material)
            self.active_materials.append(material)
            self.material_spawned.emit(material)

    def _update_sensors(self):
        """更新所有传感器状态"""
        for sensor_id, sensor in self.sensors.items():
            conveyor_id = sensor.conveyor
            conveyor = self.conveyors.get(conveyor_id)

            if not conveyor:
                sensor.release()
                continue

            # 检查是否有物料在当前皮带上
            matching_materials = [m for m in self.active_materials if m.current_conveyor == conveyor.id and m.is_active]
            if matching_materials and conveyor.is_running:
                has_material = self._check_material_on_sensor(conveyor, sensor)
            else:
                has_material = False

            was_real_active = sensor.real_state

            # 根据物料位置判断传感器状态
            if has_material and not sensor.real_state:
                sensor.trigger(0)
            elif has_material and sensor.real_state:
                # 物料仍在范围内，重置保持时间
                sensor.hold_timer = 200
            elif not has_material and sensor.real_state:
                # 物料不在范围内，延迟释放
                sensor.hold_timer -= 50
                if sensor.hold_timer <= 0:
                    sensor.release()

            # 应用故障模拟 - 使用故障后的状态用于UI展示
            original_state = sensor.real_state
            simulated_state = self.fault_diagnosis.update_sensor_state(sensor_id, original_state)
            sensor.is_active = simulated_state

            # 只有真实状态变化时才触发事件
            if was_real_active != sensor.real_state:
                self.sensor_triggered.emit(sensor_id, sensor.real_state)

    def _check_material_on_sensor(self, conveyor: Conveyor, sensor: Sensor) -> bool:
        """检查传感器位置是否有物料"""
        # distance_from_start 是 0-1 之间的比例值（表示皮带长度的百分比）
        # 需要转换为像素距离进行比较
        sensor_distance_ratio = sensor.distance_from_start  # 0-1 之间
        sensor_pixel_distance = conveyor.pixel_length * sensor_distance_ratio

        for material in self.active_materials:
            if material.current_conveyor == conveyor.id and material.is_active:
                mat_distance = material.distance_on_conveyor
                # 误差阈值：皮带长度的10%或至少10像素
                error_threshold = max(conveyor.pixel_length * 0.10, 10)
                diff = abs(mat_distance - sensor_pixel_distance)
                if diff < error_threshold:
                    return True

        return False

    def _check_alarms(self):
        """检查报警条件"""
        # 中转斗满载报警
        for hopper_id, hopper in self.hoppers.items():
            if hopper.current_weight >= hopper.capacity_tons * 0.95:
                alarm_key = f"HOPPER_OVERFLOW_{hopper_id}"
                if alarm_key not in self.active_alarms:
                    self._raise_alarm('HOPPER_OVERFLOW', f"{hopper.name} 接近满载")

            # 开关故障报警（斗关闭但皮带停止，应该无料但实际有料）
            if hopper.get_effective_switch_state() == False:
                # 检查所有输入皮带
                input_cons = hopper.input_conveyor
                if isinstance(input_cons, list):
                    input_conv_ids = input_cons
                else:
                    input_conv_ids = [input_cons]

                all_stopped = all(
                    self.conveyors.get(cid) and not self.conveyors.get(cid).is_running
                    for cid in input_conv_ids
                )

                if all_stopped and hopper.current_weight > 0.1:
                    alarm_key = f"HOPPER_WEIGHT_ANOMALY_{hopper_id}"
                    if alarm_key not in self.active_alarms:
                        self._raise_alarm('HOPPER_WEIGHT_ANOMALY',
                                        f"{hopper.name}: 皮带停止但斗有料(异常)")

        # 皮带打滑报警（速度异常）
        for hopper_id, hopper in self.hoppers.items():
            if hopper.belt_speed_multiplier < 0.8:
                alarm_key = f"BELT_SLIP_{hopper_id}"
                if alarm_key not in self.active_alarms:
                    self._raise_alarm('BELT_SLIP', f"{hopper.name}相关皮带打滑")

    def _run_fault_diagnosis(self):
        """运行故障诊断——使用独立诊断引擎"""
        if self._diagnosis_mode == "tcp":
            return
        cart_data = self.sensor_data_manager.read_cart_sensors()
        speed_data = self.sensor_data_manager.read_conveyor_speeds()

        results = self.fault_diagnosis_adapter.run_diagnosis(
            sensors=self.sensors,
            hoppers=self.hoppers,
            conveyors=self.conveyors,
            active_routes=self.active_routes,
            route_state_manager=self.route_state_manager,
            cart_data=cart_data,
            speed_data=speed_data,
            total_runtime=self.total_runtime,
        )

        now = self.total_runtime

        # 累积结果：新检测到的故障更新 dict，保持持续显示
        for r in results:
            if r.confidence >= 0.7:
                key = f"{r.sensor_id}:{r.fault_type}"
                self._accumulated_diagnosis[key] = (now, r)
                self._raise_alarm('SENSOR_FAULT', r.description, alarm_key=key)

        # 清除超过35秒未重新确认的结果（引擎去重周期为30秒）
        stale_keys = [
            k for k, (ts, _) in self._accumulated_diagnosis.items()
            if now - ts > 35.0
        ]
        for k in stale_keys:
            del self._accumulated_diagnosis[k]

        accumulated = [r for _, r in self._accumulated_diagnosis.values()]
        self.diagnosis_result = [
            (r.sensor_id, r.description) for r in accumulated
        ]
        self._full_diagnosis_results = accumulated

    def _build_route_hopper_sensor_map(self) -> Dict[str, Dict[str, Tuple[str, str]]]:
        """
        构建路线到中转斗传感器的映射

        Returns:
            {route_id: {hopper_id: (prev_sensor_id, next_sensor_id)}}
            即每个中转斗的前后传感器ID
        """
        route_map = {}

        for route_id, route in config.FEED_ROUTES.items():
            hoppers = route.get('hoppers', [])
            conveyors = route.get('conveyors', [])

            if not hoppers or not conveyors:
                continue

            hopper_sensor_map = {}

            for i, hopper_id in enumerate(hoppers):
                if hopper_id not in self.hoppers:
                    continue

                # 找到该中转斗对应的皮带位置
                # hopper在conveyors中的索引i对应hoppers[i]
                # 皮带i的末端传感器触发表示物料到达中转斗i
                # 皮带i+1的传感器触发表示物料离开中转斗i

                prev_sensor = None
                next_sensor = None

                # 找到皮带i上的传感器（物料进入中转斗前）
                if i < len(conveyors):
                    conv_id = conveyors[i]
                    for sensor_id, sensor in self.sensors.items():
                        if sensor.conveyor == conv_id:
                            prev_sensor = sensor_id
                            break

                # 找到皮带i+1上的传感器（物料离开中转斗后）
                if i + 1 < len(conveyors):
                    next_conv_id = conveyors[i + 1]
                    for sensor_id, sensor in self.sensors.items():
                        if sensor.conveyor == next_conv_id:
                            next_sensor = sensor_id
                            break

                if prev_sensor or next_sensor:
                    hopper_sensor_map[hopper_id] = (prev_sensor, next_sensor)

            if hopper_sensor_map:
                route_map[route_id] = hopper_sensor_map

        return route_map

    def _raise_alarm(self, alarm_type: str, message: str, alarm_key: str = None):
        """触发报警"""
        # 使用alarm_key去重，避免重复报警
        if alarm_key:
            if alarm_key in self.active_alarms:
                return  # 已经报警过，不再重复报警
            self.active_alarms.add(alarm_key)

        self.alarm_count += 1
        self.alarm_raised.emit(alarm_type, message)

    # ==================== 故障诊断相关方法 ====================

    def set_fault_mode(self, sensor_id: str, mode: FaultMode):
        """设置传感器故障模式"""
        self.fault_diagnosis.set_fault_mode(sensor_id, mode)
        if mode == FaultMode.STUCK_LOW:
            self.control_strategy_generator.set_fault_override(sensor_id, False)
        elif mode == FaultMode.STUCK_HIGH:
            self.control_strategy_generator.set_fault_override(sensor_id, True)
        elif mode == FaultMode.OFF:
            self.control_strategy_generator.clear_fault_override(sensor_id)
        else:
            self.control_strategy_generator.clear_fault_override(sensor_id)

    def clear_all_faults(self):
        """清除所有故障设置"""
        self.fault_diagnosis.clear_all_faults()
        self.diagnosis_result.clear()
        self._accumulated_diagnosis.clear()
        self.diagnosis_engine.clear_history()
        # 清除所有中转斗故障
        for hopper in self.hoppers.values():
            hopper.switch_fault_mode = None
            hopper.weight_fault_mode = None
            hopper.weight_offset = 0.0
            hopper.belt_speed_multiplier = 1.0
        # 清除数据管理器中的故障
        self.sensor_data_manager.clear_all_faults()
        self.control_strategy_generator.clear_all_fault_overrides()

    def reset_sensor_data(self):
        """重置传感器数据到初始状态（不停止仿真）"""
        self.sensor_data_manager.reset_all_data()
        self._accumulated_diagnosis.clear()
        self.diagnosis_engine.clear_history()
        self.diagnosis_result.clear()
        for conv_id in config.CONVEYOR_STATES:
            config.CONVEYOR_STATES[conv_id] = None

    def set_random_faults_on_active_routes(self, mode: FaultMode, count: int = 2):
        """在活跃路线上随机设置故障传感器"""
        self.fault_diagnosis.set_faults_on_active_routes(
            list(self.active_routes),
            mode,
            count
        )

    def get_faulty_sensors(self) -> Set[str]:
        """获取所有故障传感器ID"""
        return self.fault_diagnosis.get_faulty_sensor_ids()

    def get_diagnosis_result(self) -> List[Tuple[str, str]]:
        """获取诊断结果（兼容旧格式）"""
        return self.diagnosis_result.copy()

    def get_full_diagnosis_results(self) -> list:
        """获取完整诊断结果（含置信度、类别等信息）"""
        return getattr(self, '_full_diagnosis_results', [])

    def set_fault_config(self, config: dict):
        """设置故障配置（从控制面板接收）"""
        mode = config.get('mode', FaultMode.OFF)
        count = config.get('count', 0)
        faulty_sensors = config.get('faulty_sensors', [])
        hopper_faults = config.get('hopper_faults', [])

        # 清除所有现有故障
        self.fault_diagnosis.clear_all_faults()
        self._accumulated_diagnosis.clear()
        self.diagnosis_engine.clear_history()
        for hopper in self.hoppers.values():
            hopper.switch_fault_mode = None
            hopper.weight_fault_mode = None
            hopper.belt_speed_multiplier = 1.0
        self.sensor_data_manager.clear_all_faults()
        self.control_strategy_generator.clear_all_fault_overrides()

        # 处理传感器故障（不影响中转斗故障）
        if mode != FaultMode.OFF:
            if faulty_sensors:
                for sensor_id in faulty_sensors:
                    self.set_fault_mode(sensor_id, mode)
            else:
                self.fault_diagnosis.set_faults_on_active_routes(
                    list(self.active_routes),
                    mode,
                    count
                )
                for sensor_id in self.fault_diagnosis.get_faulty_sensor_ids():
                    if mode == FaultMode.STUCK_LOW:
                        self.control_strategy_generator.set_fault_override(sensor_id, False)
                    elif mode == FaultMode.STUCK_HIGH:
                        self.control_strategy_generator.set_fault_override(sensor_id, True)

        # 处理中转斗故障（独立于传感器故障）
        if hopper_faults:
            for hopper_fault in hopper_faults:
                hopper_id = hopper_fault.get('hopper_id')
                fault_type = hopper_fault.get('fault_type')
                if hopper_id and fault_type:
                    self.set_hopper_fault(hopper_id, fault_type)

    # ==================== 辅助方法 ====================

    def is_conveyor_on_route(self, conv_id: str) -> bool:
        """检查皮带是否在活跃路线上"""
        for route_id in self.active_routes:
            route = config.FEED_ROUTES.get(route_id)
            if route and conv_id in route['conveyors']:
                return True
        return False

    def is_hopper_active(self, hopper_id: str) -> bool:
        """检查中转斗是否活跃"""
        hopper = self.hoppers.get(hopper_id)
        if hopper:
            return hopper.is_active
        return False

    def get_sensor_state(self, sensor_id: str) -> bool:
        """获取传感器状态"""
        sensor = self.sensors.get(sensor_id)
        if sensor:
            return sensor.is_active
        return False

    def get_cart_sensor_state(self, cart_id: str) -> dict:
        """
        获取运料小车传感器状态
        Returns: {
            'position': int,  # 位置值1-7
            'left_limit': bool,  # 左极限传感器
            'right_limit': bool,  # 右极限传感器
            'left_divert': bool,  # 左分料传感器
            'right_divert': bool  # 右分料传感器
        }
        """
        # 使用传感器位置（等实际到达后才更新）
        position = self.cart_sensor_positions.get(cart_id, 1)

        # 计算极限传感器值
        if cart_id == 'Cart4':
            left_limit = position == 1
            right_limit = position == 6
        else:
            left_limit = position == 1
            right_limit = position == 7

        # 分料传感器由路线目标决定
        route_id = self._get_cart_route(cart_id)
        if route_id:
            target_bin = self.route_to_bin.get(route_id)
            if target_bin:
                ctx = self.route_state_manager.get_route_context(route_id)
                if ctx:
                    left_divert, right_divert = self._calculate_cart_divert(cart_id, target_bin)
                    self.cart_divert[cart_id] = (left_divert, right_divert)
                else:
                    left_divert, right_divert = self.cart_divert.get(cart_id, (False, False))
            else:
                left_divert, right_divert = self.cart_divert.get(cart_id, (False, False))
        else:
            left_divert, right_divert = self.cart_divert.get(cart_id, (False, False))

        return {
            'position': position,
            'left_limit': left_limit,
            'right_limit': right_limit,
            'left_divert': left_divert,
            'right_divert': right_divert
        }

    def _get_cart_route(self, cart_id: str) -> Optional[str]:
        """获取小车对应的路线ID"""
        for route_id, ctx in self.route_state_manager.routes.items():
            if ctx.assigned_cart == cart_id:
                return route_id
        return None

    def _calculate_cart_divert(self, cart_id: str, target_bin: str) -> tuple:
        """计算小车分料传感器值"""
        if cart_id == 'Cart1':
            return (True, False)
        elif cart_id == 'Cart2':
            if target_bin.startswith('P2'):
                return (True, False)
            elif target_bin.startswith('P3'):
                return (False, True)
            return (True, False)
        elif cart_id == 'Cart3':
            return (False, True)
        return (False, False)

    def get_conveyor_state(self, conv_id: str) -> dict:
        """获取皮带状态（通过皮带转速传感器数据判断）"""
        # 获取皮带对应的转速传感器ID
        speed_sensor_id = config.CONVEYOR_SPEED_SENSORS.get(conv_id)
        raw_speed = 0
        speed = 0.0
        is_running = False
        fault_type = None

        if speed_sensor_id:
            # 从传感器数据管理器读取转速（sint类型）
            raw_speed = self.sensor_data_manager.read_conveyor_speed(speed_sensor_id) or 0
            speed = raw_speed / config.SPEED_SCALE  # 转换为m/s

            # 检查手动设置的皮带状态
            manual_state = config.CONVEYOR_STATES.get(conv_id)

            if manual_state == 'stopped':
                # 手动设置为关闭
                is_running = False
                fault_type = 'stopped'
            elif manual_state == 'speed_abnormal':
                # 手动设置为转速异常
                is_running = True
                fault_type = 'speed_abnormal'
            elif raw_speed >= config.SPEED_NORMAL_MIN:
                # 正常运行时，检查是否转速异常
                is_running = True
                if raw_speed < config.SPEED_NORMAL_MIN + config.SPEED_NORMAL_RANGE:
                    fault_type = 'speed_abnormal'
            else:
                # 转速过低认为停止
                is_running = False

        return {
            'is_running': is_running,
            'speed': speed,
            'raw_speed': raw_speed,  # sint原始值
            'on_route': self.is_conveyor_on_route(conv_id),
            'fault_type': fault_type,
        }

    def get_hopper_level(self, hopper_id: str) -> float:
        """获取中转斗料位百分比

        逻辑：
        - 开关打开时（正常补料）：返回0（物料边进边出）
        - 开关关闭时（清空余料）：返回余料对应的料位百分比
        """
        hopper = self.hoppers.get(hopper_id)
        if hopper:
            effective_open = hopper.get_effective_switch_state()
            if effective_open:
                # 开关打开，物料边进边出，料位为0
                return 0.0
            else:
                # 开关关闭，使用余料计算料位百分比
                # 料位百分比 = (余料重量 / 容量) * 100
                return (hopper.residual_weight / hopper.capacity_tons) * 100
        return 0

    def get_hopper_weight(self, hopper_id: str) -> float:
        """获取中转斗称重传感器值（吨）"""
        hopper = self.hoppers.get(hopper_id)
        if hopper:
            return hopper.get_display_weight()
        return 0

    def get_hopper_switch_state(self, hopper_id: str) -> bool:
        """
        获取中转斗开关显示状态（用于UI显示）
        返回用户手动设置的状态，而非实际生效状态
        """
        hopper = self.hoppers.get(hopper_id)
        if hopper:
            return hopper.get_display_switch_state()
        return True

    def get_hopper_effective_switch_state(self, hopper_id: str) -> bool:
        """
        获取中转斗开关实际生效状态（用于上料过程）
        考虑故障模拟的影响
        """
        hopper = self.hoppers.get(hopper_id)
        if hopper:
            return hopper.get_effective_switch_state()
        return True

    def toggle_hopper_switch(self, hopper_id: str) -> bool:
        """切换中转斗开关状态"""
        hopper = self.hoppers.get(hopper_id)
        if hopper:
            hopper.is_open = not hopper.is_open
            hopper._manual_switch_state = hopper.is_open
            return hopper.is_open
        return True

    def set_hopper_switch_state(self, hopper_id: str, state: bool):
        """
        设置中转斗开关状态（由UI调用）
        state: True=开, False=关
        """
        hopper = self.hoppers.get(hopper_id)
        if hopper:
            hopper.is_open = state
            hopper._manual_switch_state = state

    def set_hopper_fault(self, hopper_id: str, fault_type: str):
        """设置中转斗故障类型"""
        hopper = self.hoppers.get(hopper_id)
        if not hopper:
            return

        if fault_type == 'none':
            hopper.switch_fault_mode = None
            hopper.weight_fault_mode = None
            hopper.weight_offset = 0.0
            hopper.belt_speed_multiplier = 1.0
            # 清除数据管理器中的故障（确保 generate_data.json 恢复正确值）
            self.sensor_data_manager.clear_fault(hopper_id=hopper_id)
        elif fault_type == 'switch_stuck_closed':
            hopper.switch_fault_mode = 'stuck_closed'
            self.sensor_data_generator.inject_hopper_switch_fault(hopper_id, stuck_closed=True)
        elif fault_type == 'switch_stuck_open':
            hopper.switch_fault_mode = 'stuck_open'
            self.sensor_data_generator.inject_hopper_switch_fault(hopper_id, stuck_closed=False)
        elif fault_type == 'weight_stuck_zero':
            hopper.weight_fault_mode = 'stuck_zero'
            self.sensor_data_generator.inject_hopper_weight_fault(hopper_id, stuck_zero=True)
        elif fault_type == 'weight_offset':
            hopper.weight_fault_mode = 'offset'
            hopper.weight_offset = random.uniform(-0.5, 0.5)
            self.sensor_data_generator.inject_hopper_weight_fault(hopper_id, stuck_zero=False, offset=hopper.weight_offset)

    # ==================== 小车4控制方法 ====================

    def get_cart4_state(self) -> dict:
        """
        获取小车4状态
        Returns: {
            'position': int,  # 位置值1-6
            'left_limit': bool,  # 左极限传感器
            'right_limit': bool,  # 右极限传感器
            'left_divert': bool,  # 左分料传感器
            'right_divert': bool  # 右分料传感器
        }
        """
        return {
            'position': int(self.cart4_position),  # 实际物理位置（实时）
            'left_limit': self.cart4_position < 1,
            'right_limit': self.cart4_position > 6,
            'left_divert': True,
            'right_divert': True,
        }

    def set_cart4_target_position(self, position: int):
        """
        设置小车4目标位置
        Args:
            position: 目标位置(1-6)
        """
        if 1 <= position <= 6:
            self.cart4_target_position = position
            if self.cart4_position != position:
                self.cart4_is_moving = True

    def update_cart4_position(self, delta_seconds: float = 1.0/60.0):
        """更新小车4位置（每帧调用）"""
        if not self.cart4_is_moving:
            return
        if not hasattr(self, '_cart4_move_timer'):
            self._cart4_move_timer = 0.0
        distance = abs(self.cart4_position - self.cart4_target_position)
        if distance <= 0:
            self.cart4_is_moving = False
            self._cart4_move_timer = 0.0
            print(f"[Cart4] 已到达目标位置 {self.cart4_position}", flush=True)
            return
        self._cart4_move_timer += delta_seconds
        if self._cart4_move_timer >= 18.0:
            self._cart4_move_timer = 0.0
            old_pos = self.cart4_position
            if self.cart4_position < self.cart4_target_position:
                self.cart4_position += 1
            else:
                self.cart4_position -= 1
            print(f"[Cart4] 移动: {old_pos} → {self.cart4_position} (目标={self.cart4_target_position})", flush=True)
            if self.cart4_position == self.cart4_target_position:
                self._check_cart_arrival('Cart4')
                self.cart4_is_moving = False

        # 使用计时器控制每18秒移动一位
        if not hasattr(self, '_cart4_move_timer'):
            self._cart4_move_timer = 0.0

        # 获取距离目标还剩多少位
        distance = abs(self.cart4_position - self.cart4_target_position)
    def _check_cart_arrival(self, cart_id: str):
        """检查小车到达后，触发相关路线的FEEDING状态"""
        print(f"[CartArrival] 检查 {cart_id} 到达...", flush=True)
        for route_id in list(self.active_routes):
            ctx = self.route_state_manager.get_route_context(route_id)
            if not ctx or ctx.assigned_cart != cart_id:
                continue
            print(f"[CartArrival] {cart_id} route={route_id} state={ctx.state.value} cart_moving={ctx.cart_moving}", flush=True)

            if ctx.state != RouteState.MOVING_TO_TARGET:
                print(f"[CartArrival] {cart_id} 跳过: state={ctx.state.value} != MOVING_TO_TARGET", flush=True)
                continue
            cart_is_moving = self.cart4_is_moving if cart_id == 'Cart4' else ctx.cart_moving
            if not cart_is_moving:
                print(f"[CartArrival] {cart_id} 跳过: cart_is_moving=False", flush=True)
                continue

            if route_id in self._pending_stop_after_cart_arrival:
                self._pending_stop_after_cart_arrival.discard(route_id)
                self._complete_stop_route(route_id)
                continue

            # 小车到达目标位置，切换到FEEDING状态
            print(f"[到达] {route_id} cart={cart_id} -> FEEDING, 启动皮带...", flush=True)
            self.route_state_manager._transition(ctx, RouteState.FEEDING)
            ctx.cart_moving = False
            ctx.feeding_start_time = self.total_runtime
            ctx.clearing_strategy = self._resolve_clearing_strategy(route_id)

            if cart_id == 'Cart4':
                self.cart4_sensor_position = self.cart4_position

            route = config.FEED_ROUTES.get(route_id)
            if route and route['conveyors']:
                for conv_id in route['conveyors']:
                    if conv_id in self.conveyors:
                        self.conveyors[conv_id].start(self.speed)
                        print(f"[到达] {route_id} 启动皮带 {conv_id}", flush=True)
                for hopper_id in ctx.assigned_hoppers:
                    if hopper_id in self.hoppers:
                        self.hoppers[hopper_id].is_open = True
                        print(f"[到达] {route_id} 打开中转斗 {hopper_id}", flush=True)

    def _update_cart_positions(self, delta_seconds: float):
        """更新所有小车位置（模拟移动）

        小车移动参数：
        - 皮带上相邻小仓间距为24像素
        - 移动一位需要的时间 = 18秒
        - 移动速度 = 24 / 18 = 1.333 px/s
        """
        # 每移动一格需要的时间（秒）
        move_one_position_time = 18.0

        # 更新Cart1/2/3的位置
        for cart_id in ['Cart1', 'Cart2', 'Cart3']:
            if cart_id not in self.cart_target_positions:
                continue

            target_pos = self.cart_target_positions.get(cart_id, 1)
            current_pos = self.cart_positions.get(cart_id, 1)

            # 检查是否有小车需要移动
            needs_moving = False
            for route_id in list(self.active_routes):
                ctx = self.route_state_manager.get_route_context(route_id)
                if ctx and ctx.assigned_cart == cart_id and ctx.cart_moving:
                    needs_moving = True
                    break

            if current_pos != target_pos and needs_moving:
                # 模拟小车每18秒（移动一位）更新一次位置
                if not hasattr(self, '_cart_move_timers'):
                    self._cart_move_timers = {}
                if cart_id not in self._cart_move_timers:
                    self._cart_move_timers[cart_id] = 0.0

                self._cart_move_timers[cart_id] += delta_seconds
                if self._cart_move_timers[cart_id] >= move_one_position_time:
                    self._cart_move_timers[cart_id] = 0.0
                    if current_pos < target_pos:
                        self.cart_positions[cart_id] = current_pos + 1
                    else:
                        self.cart_positions[cart_id] = current_pos - 1

                    # 检查是否有小车到达
                    self._check_virtual_cart_arrival(cart_id)

    def _check_virtual_cart_arrival(self, cart_id: str):
        """检查虚拟小车(Cart1/2/3)是否到达目标位置"""
        for route_id in list(self.active_routes):
            ctx = self.route_state_manager.get_route_context(route_id)
            if not ctx or ctx.assigned_cart != cart_id:
                continue

            if not ctx.cart_moving:
                continue
            # 允许 MOVING_TO_TARGET 或 CLEARING+early_moved 两种状态
            if ctx.state != RouteState.MOVING_TO_TARGET:
                if not (ctx.state == RouteState.CLEARING and ctx.early_moved_from_clearing):
                    continue
                print(f"[VirtualArrival] {cart_id} route={route_id} CLEARING+early_moved → 处理到达", flush=True)

            current_pos = self.cart_positions.get(cart_id, 1)
            if current_pos != ctx.cart_target_position:
                continue

            if route_id in self._pending_stop_after_cart_arrival:
                self._pending_stop_after_cart_arrival.discard(route_id)
                self._complete_stop_route(route_id)
                continue

            # 小车到达目标位置，切换到FEEDING状态
            ctx.previous_state = 'clearing'
            if ctx.early_moved_from_clearing:
                # 提前移动路线跳过了complete_clearing，将累加的余料转移到待释放
                for hopper_id, weight in ctx.current_weights.items():
                    if weight > 0:
                        ctx.pending_release_weights[hopper_id] = weight
                for hopper_id, weight in ctx.current_weights.items():
                    ctx.final_weights[hopper_id] = weight
            ctx.early_moved_from_clearing = False
            self.route_state_manager._transition(ctx, RouteState.FEEDING)
            ctx.cart_moving = False
            ctx.feeding_start_time = self.total_runtime
            ctx.clearing_strategy = self._resolve_clearing_strategy(route_id)
            # 更新传感器位置（只有实际到达后才更新）
            self.cart_sensor_positions[cart_id] = current_pos

            # 更新 executing_bin 追踪（提前移动路线跳过了 _on_auto_feed_route_completed）
            cart_to_belt = {'Cart1': 'D7', 'Cart2': 'D8', 'Cart3': 'D9'}
            belt_id = cart_to_belt.get(cart_id, '')
            if belt_id and belt_id in self._executing_route:
                self._executing_bin[belt_id] = ctx.target_bin

            # 启动所有皮带
            route = config.FEED_ROUTES.get(route_id)
            if route and route['conveyors']:
                for conv_id in route['conveyors']:
                    if conv_id in self.conveyors:
                        self.conveyors[conv_id].start(self.speed)
                print(f"[到达] {route_id} 提前移动小车到达，启动所有皮带，打开中转斗释放余料", flush=True)
                # 打开中转斗开关（正常补料开始，释放累积余料）
                for hopper_id in ctx.assigned_hoppers:
                    if hopper_id in self.hoppers:
                        self.hoppers[hopper_id].is_open = True

    def get_cart4_sensor_state(self, cart_id: str = 'Cart4') -> dict:
        """
        获取运料小车传感器状态（兼容Cart1-3的接口）
        对于Cart4，返回小车4的状态
        """
        if cart_id == 'Cart4':
            return self.get_cart4_state()
        return self.get_cart_sensor_state(cart_id)

    def get_status(self) -> dict:
        """获取仿真状态"""
        return {
            'is_running': self.is_running,
            'speed': self.speed,
            'active_routes': list(self.active_routes),
            'total_runtime': self.total_runtime,
            'total_feed_weight': self.total_feed_weight,
            'alarm_count': self.alarm_count,
            # 脏标记会在读取后清除
            'dirty': self._dirty,
        }

    def is_dirty(self) -> bool:
        """检查并清除脏标记"""
        dirty = self._dirty
        self._dirty = False
        return dirty

    def mark_dirty(self):
        """标记为脏（需要UI更新）"""
        self._dirty = True

    # ============ 传感器数据管理（读写JSON文件） ============

    def get_sensor_data_from_json(self) -> dict:
        """
        从JSON文件读取传感器数据（模拟从实际传感器读取）
        Returns: 传感器数据字典
        """
        sensors = self.sensor_data_manager.read_all_sensors()
        hoppers = self.sensor_data_manager.read_all_hopper_data()
        return {
            'sensors': sensors,
            'hoppers': hoppers,
            'timestamp': self.sensor_data_manager._current_data.get('timestamp', 0)
        }

    def set_sensor_data_mode(self, simulation_mode: bool):
        """设置传感器数据模式"""
        self.sensor_data_manager.set_simulation_mode(simulation_mode)
        self.enable_sensor_data_generation = simulation_mode

    def is_simulation_mode(self) -> bool:
        """检查是否为仿真模式"""
        return self.sensor_data_manager.is_simulation_mode()

    def get_data_file_path(self) -> str:
        """获取传感器数据文件路径"""
        return self.sensor_data_manager.get_data_file_path()

    def export_sensor_data(self) -> str:
        """导出传感器数据为JSON字符串"""
        return self.sensor_data_manager.export_data()

    # ============ 故障注入接口 ============

    def inject_sensor_fault(self, sensor_id: str, fault_mode: str, 
                           duration: float = -1.0, probability: float = 1.0):
        """注入接近开关传感器故障"""
        from sensor_data_manager import FaultMode as SDM_FaultMode
        mode_map = {
            'stuck_low': SDM_FaultMode.STUCK_LOW,
            'stuck_high': SDM_FaultMode.STUCK_HIGH,
            'random': SDM_FaultMode.RANDOM,
            'sensitivity_loss': SDM_FaultMode.SENSITIVITY_LOSS,
            'intermittent': SDM_FaultMode.INTERMITTENT,
        }
        mode = mode_map.get(fault_mode, SDM_FaultMode.STUCK_LOW)
        self.sensor_data_generator.inject_sensor_fault(sensor_id, mode, duration, probability)

    def inject_hopper_switch_fault(self, hopper_id: str, stuck_closed: bool = True,
                                   duration: float = -1.0):
        """注入中转斗开关故障"""
        self.sensor_data_generator.inject_hopper_switch_fault(hopper_id, stuck_closed, duration)

    def inject_hopper_weight_fault(self, hopper_id: str, stuck_zero: bool = True,
                                   offset: float = 0.0, duration: float = -1.0):
        """注入中转斗称重故障"""
        self.sensor_data_generator.inject_hopper_weight_fault(
            hopper_id, stuck_zero, offset, duration
        )

    def clear_all_sensor_faults(self):
        """清除所有传感器故障"""
        self.sensor_data_generator.clear_all_faults()
        self.control_strategy_generator.clear_all_fault_overrides()

    def get_sensor_fault_status(self) -> dict:
        """获取传感器故障状态"""
        return self.sensor_data_generator.get_fault_status()

    # ============ 运料小车传感器故障注入 ============

    def inject_cart_position_fault(self, cart_id: str, fault_type: str = 'position_stuck',
                                     stuck_value: int = 1, offset: int = 2,
                                     duration: float = -1.0):
        """注入小车位置传感器故障

        Args:
            cart_id: 小车ID（如 'Cart1', 'Cart2'）
            fault_type: 故障类型
                - 'position_stuck': 定位彻底失效（位置卡死不变）
                - 'position_inaccurate': 定位不准（在目标位置基础上随机偏移）
            stuck_value: 定位卡死时的固定位置值（1-7），仅 position_stuck 有效
            offset: 定位不准时的最大偏移量，仅 position_inaccurate 有效
            duration: 故障持续时间（秒），-1 表示持续直到手动清除
        """
        key = f"{cart_id}_position_fault"
        self.control_strategy_generator.set_fault_override(key, {
            'type': fault_type,
            'stuck_value': stuck_value,
            'offset': offset,
            'duration': duration,
        })

    def inject_cart_limit_fault(self, cart_id: str, side: str = 'left',
                                  stuck_value: bool = True, duration: float = -1.0):
        """注入小车极限传感器故障

        Args:
            cart_id: 小车ID（如 'Cart1', 'Cart2'）
            side: 侧别 'left'（左极限）或 'right'（右极限）
            stuck_value: 恒定输出值 True（恒为触发）或 False（恒为未触发）
            duration: 故障持续时间（秒），-1 表示持续直到手动清除
        """
        key = f"{cart_id}_{side}_limit"
        self.control_strategy_generator.set_fault_override(key, stuck_value)

    def inject_cart_divert_fault(self, cart_id: str, side: str = 'left',
                                    stuck_value: bool = True, duration: float = -1.0):
        """注入小车分料传感器故障

        Args:
            cart_id: 小车ID（如 'Cart1', 'Cart2'）
            side: 侧别 'left'（左分料）或 'right'（右分料）
            stuck_value: 恒定输出值 True 或 False
            duration: 故障持续时间（秒），-1 表示持续直到手动清除
        """
        key = f"{cart_id}_{side}_divert"
        self.control_strategy_generator.set_fault_override(key, stuck_value)

    def clear_cart_fault(self, cart_id: str, sensor_type: str):
        """清除指定小车的传感器故障

        Args:
            cart_id: 小车ID
            sensor_type: 传感器类型
                - 'position': 位置传感器
                - 'left_limit': 左极限
                - 'right_limit': 右极限
                - 'left_divert': 左分料
                - 'right_divert': 右分料
                - 'all': 该小车所有传感器故障
        """
        if sensor_type == 'all':
            for suffix in ['position_fault', 'left_limit', 'right_limit',
                          'left_divert', 'right_divert']:
                key = f"{cart_id}_{suffix}"
                self.control_strategy_generator.clear_fault_override(key)
        else:
            if sensor_type == 'position':
                key = f"{cart_id}_position_fault"
            else:
                key = f"{cart_id}_{sensor_type}"
            self.control_strategy_generator.clear_fault_override(key)

    def clear_all_cart_faults(self):
        """清除所有小车传感器故障"""
        for suffix in ['position_fault', 'left_limit', 'right_limit',
                      'left_divert', 'right_divert']:
            for cart_id in self.control_strategy_generator.cart_sensor_ids:
                key = f"{cart_id}_{suffix}"
                self.control_strategy_generator.clear_fault_override(key)

    def get_cart_fault_status(self) -> dict:
        """获取所有小车传感器故障状态"""
        result = {}
        for key, value in self.control_strategy_generator.fault_overrides.items():
            if any(key.startswith(cart_id) for cart_id in
                   self.control_strategy_generator.cart_sensor_ids):
                result[key] = value
        return result

    # ============ 激光测距仪传感器管理 ============

    def get_laser_sensor_state(self, sensor_id: str) -> bool:
        """获取激光传感器状态（True=有料，False=无料）

        Args:
            sensor_id: 激光传感器ID（如 'L-feed2_1'）或上料点ID（如 'feed2_1'）
        """
        # 首先尝试直接使用sensor_id作为键
        if sensor_id in self.laser_sensor_states:
            return self.laser_sensor_states[sensor_id]

        # 从LASER_SENSORS配置中找到对应的feed_point_id
        sensor_config = config.LASER_SENSORS.get(sensor_id)
        if sensor_config:
            feed_point = sensor_config.get('feed_point')
            if feed_point and feed_point in self.laser_sensor_states:
                return self.laser_sensor_states[feed_point]

        return False

    def set_laser_sensor_state(self, sensor_id: str, has_material: bool):
        """设置激光传感器状态（True=有料，False=无料）

        Args:
            sensor_id: 激光传感器ID（如 'L-feed2_1'）
            has_material: 是否有原料
        """
        # 从LASER_SENSORS配置中找到对应的feed_point_id
        sensor_config = config.LASER_SENSORS.get(sensor_id)
        if sensor_config:
            feed_point = sensor_config.get('feed_point')
            if feed_point and feed_point in self.laser_sensor_states:
                self.laser_sensor_states[feed_point] = has_material
                self.mark_dirty()
        # 也尝试直接使用sensor_id作为键
        elif sensor_id in self.laser_sensor_states:
            self.laser_sensor_states[sensor_id] = has_material
            self.mark_dirty()

    def get_feed_point_has_material(self, feed_point_id: str) -> bool:
        """获取上料点是否有原料

        Args:
            feed_point_id: 上料点ID（如 'feed2_1'）
        """
        if feed_point_id in self.laser_sensor_states:
            return self.laser_sensor_states[feed_point_id]
        return False

    def is_route_available(self, route_id: str) -> bool:
        """检查路线是否可用（根据上料点是否有原料）"""
        if route_id not in config.FEED_ROUTES:
            return False

        route = config.FEED_ROUTES[route_id]
        feed_point = route.get('feed_point')

        if not feed_point or feed_point == 'silo_out':
            # 储料仓出料不需要检查激光传感器
            return True

        # 检查该上料点的激光传感器状态
        return self.get_feed_point_has_material(feed_point)

    def get_laser_sensor_display_name(self, sensor_id: str) -> str:
        """获取激光传感器的显示名称"""
        sensor_config = config.LASER_SENSORS.get(sensor_id)
        if sensor_config:
            return sensor_config.get('name', sensor_id)
        return sensor_id

    def get_feed_point_display_name(self, feed_point_id: str) -> str:
        """获取上料点的显示名称"""
        feed_point = config.FEED_POINTS.get(feed_point_id)
        if feed_point:
            return feed_point.get('name', feed_point_id)
        return feed_point_id

    # ============ 路线状态管理接口 ============

    def get_route_state(self, route_id: str) -> str:
        """获取路线状态"""
        return self.route_state_manager.get_route_state(route_id).value

    def get_all_route_states(self) -> Dict[str, str]:
        """获取所有路线状态"""
        return self.route_state_manager.get_all_route_states()

    def recover_route(self, route_id: str) -> bool:
        """恢复路线供料（从WAITING转到FEEDING）"""
        return self.route_state_manager.recover_feeding(route_id)

    def get_route_context(self, route_id: str) -> Optional[dict]:
        """获取路线上下文信息"""
        ctx = self.route_state_manager.get_route_context(route_id)
        if ctx:
            return {
                'route_id': ctx.route_id,
                'state': ctx.state.value,
                'target_bin': ctx.target_bin,
                'assigned_hoppers': ctx.assigned_hoppers,
                'assigned_cart': ctx.assigned_cart,
                'feed_point': ctx.feed_point,
                'hopper_weights': ctx.hopper_weights,
            }
        return None

    def is_route_in_clearing(self, route_id: str) -> bool:
        """检查路线是否正在清空余料"""
        return self.route_state_manager.get_route_state(route_id) == RouteState.CLEARING

    def is_route_in_waiting(self, route_id: str) -> bool:
        """检查路线是否在等待状态"""
        return self.route_state_manager.get_route_state(route_id) == RouteState.WAITING

    # ============ 料位传感器接口 ============

    def get_level_sensor(self, bin_id: str) -> float:
        """获取料位传感器值"""
        return self.sensor_data_manager.read_level_sensor(bin_id) or 0.0

    def get_all_level_sensors(self) -> Dict[str, float]:
        """获取所有料位传感器值"""
        return self.sensor_data_manager.read_all_level_sensors()

    def set_level_sensor(self, bin_id: str, value: float):
        """设置料位传感器值"""
        self.sensor_data_manager.write_level_sensor(bin_id, value)
        self.control_strategy_generator.set_level_sensor(bin_id, value)

    def _iter_all_bin_ids_for_levels(self) -> List[str]:
        """配料站小仓 + 高位储料仓格，用于料位初始化"""
        ids = list(self.small_bins.keys())
        if hasattr(self, 'view') and self.view and hasattr(self.view, 'silo_compartments'):
            for bid in self.view.silo_compartments.keys():
                if bid not in ids:
                    ids.append(bid)
        return ids

    def _apply_level_percent_to_bin(self, bin_id: str, level_percent: float):
        """将料位百分比写入模型与传感器数据"""
        pct = round(max(0.0, min(100.0, float(level_percent))), 1)
        if bin_id in self.small_bins:
            cap = self.small_bins[bin_id].capacity
            self.small_bins[bin_id].current_level = round(pct * cap / 100.0, 4)
        if hasattr(self, 'view') and self.view and hasattr(self.view, 'silo_compartments'):
            if bin_id in self.view.silo_compartments:
                cap = self.view.silo_compartments[bin_id].get('capacity', 110)
                self.view.silo_compartments[bin_id]['current_level'] = round(pct * cap / 100.0, 4)
        self.set_level_sensor(bin_id, pct)

    def apply_bin_level_percent_uniform(self, percent: float):
        """所有料仓统一料位百分比（0–100，保留一位小数）"""
        pct = round(max(0.0, min(100.0, float(percent))), 1)
        for bin_id in self._iter_all_bin_ids_for_levels():
            self._apply_level_percent_to_bin(bin_id, pct)
        self.mark_dirty()

    def randomize_bin_levels_percent(self, low: float = 25.0, high: float = 90.0):
        """各料仓随机料位百分比，默认范围 25–90"""
        lo, hi = float(low), float(high)
        if lo > hi:
            lo, hi = hi, lo
        lo = max(0.0, min(100.0, lo))
        hi = max(0.0, min(100.0, hi))
        for bin_id in self._iter_all_bin_ids_for_levels():
            p = round(random.uniform(lo, hi), 1)
            self._apply_level_percent_to_bin(bin_id, p)
        self.mark_dirty()

    def _iter_all_bin_ids_for_consumption(self) -> List[str]:
        """返回所有需要消耗速度的料仓ID（P1-1~P4-7 + S1~S12）"""
        ids = list(self.small_bins.keys())
        if hasattr(self, 'view') and self.view and hasattr(self.view, 'silo_compartments'):
            for bid in self.view.silo_compartments.keys():
                if bid not in ids:
                    ids.append(bid)
        return ids

    def _apply_consumption_rate_to_bin(self, bin_id: str, rate: float):
        """将消耗速度写入模型与传感器数据"""
        r = round(max(0.0, float(rate)), 6)
        self._consumption_rates[bin_id] = r
        if bin_id in self.small_bins:
            self.small_bins[bin_id].consumption_rate = r
        self.sensor_data_manager.write_consumption_rates(self._consumption_rates)

    def apply_consumption_rate_uniform(self, rate: float):
        """所有料仓统一消耗速度 (t/s)"""
        r = round(max(0.0, float(rate)), 6)
        for bin_id in self._iter_all_bin_ids_for_consumption():
            self._apply_consumption_rate_to_bin(bin_id, r)

    def randomize_consumption_rates(self, low: float = 0.005, high: float = 0.01):
        """各料仓随机消耗速度，默认范围 0.005-0.01 t/s"""
        lo, hi = float(low), float(high)
        if lo > hi:
            lo, hi = hi, lo
        for bin_id in self._iter_all_bin_ids_for_consumption():
            r = round(random.uniform(lo, hi), 6)
            self._apply_consumption_rate_to_bin(bin_id, r)

    def toggle_consumption(self, active: bool):
        """启动/停止料仓消耗"""
        self._consumption_active = active
        state = "启动" if active else "停止"
        print(f"[消耗] 料仓消耗已{state}", flush=True)

    def is_consumption_active(self) -> bool:
        return self._consumption_active

    def _update_bin_consumption(self, delta_seconds: float):
        """实时消耗配料站料仓物料（仅P1-P4，高位储料仓不参与消耗）"""
        if not self._consumption_active:
            return

        # 收集正在上料的目标料仓（FEEDING状态）
        feeding_bins = set()
        for route_id in self.active_routes:
            ctx = self.route_state_manager.get_route_context(route_id)
            if ctx and ctx.state == RouteState.FEEDING and ctx.target_bin:
                feeding_bins.add(ctx.target_bin)

        for bin_id, sb in self.small_bins.items():
            if bin_id in feeding_bins:
                continue
            rate = self._consumption_rates.get(bin_id, 0.01)
            if rate <= 0:
                continue
            sb.current_level = max(0.0, sb.current_level - rate * delta_seconds)
            self.set_level_sensor(bin_id, sb.level_percent)

    # ============ 上料控制信号接口 ============

    def get_feed_signal(self, feed_id: str) -> bool:
        """获取上料控制信号值"""
        return self.sensor_data_manager.read_feed_signal(feed_id) or False

    def get_all_feed_signals(self) -> Dict[str, bool]:
        """获取所有上料控制信号"""
        return self.sensor_data_manager.read_feed_signals()
