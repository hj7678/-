"""
传感器故障诊断模块 - Sensor Fault Diagnosis
故障检测和模拟功能
"""

import random
from enum import Enum
from typing import Dict, List, Set, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field
import config

if TYPE_CHECKING:
    from controllers.simulation_controller import TransferHopper, Sensor


class FaultType(Enum):
    """故障类型"""
    NONE = "none"           # 无故障
    STUCK_LOW = "stuck_low"     # 一直为0
    STUCK_HIGH = "stuck_high"   # 一直为1
    RANDOM_FLUCTUATION = "random"  # 随机0或1
    INTERMITTENT = "intermittent"  # 间歇性故障


class FaultMode(Enum):
    """故障模拟模式"""
    OFF = "off"                 # 关闭故障模拟

    # 传感器故障
    STUCK_LOW = "stuck_low"      # 传感器卡在低电平(一直为0)
    STUCK_HIGH = "stuck_high"    # 传感器卡在高电平(一直为1)
    RANDOM = "random"            # 随机值(随机为0或1)
    SENSITIVITY_LOSS = "sensitivity_loss"  # 灵敏度降低(偶尔漏检)
    RESPONSE_DELAY = "response_delay"      # 响应延迟
    INTERMITTENT = "intermittent"          # 间歇性故障

    # 中转斗相关故障
    HOPPER_SWITCH_STUCK_CLOSED = "hopper_switch_stuck_closed"  # 开关卡在关
    HOPPER_SWITCH_STUCK_OPEN = "hopper_switch_stuck_open"    # 开关卡在开
    HOPPER_WEIGHT_STUCK_ZERO = "hopper_weight_stuck_zero"    # 称重恒为0
    HOPPER_WEIGHT_OFFSET = "hopper_weight_offset"            # 称重偏移

    # 皮带故障
    BELT_SLIP = "belt_slip"           # 皮带打滑
    BELT_SPEED_VARIANCE = "belt_speed_variance"  # 皮带速度波动


@dataclass
class SensorFaultInfo:
    """传感器故障信息"""
    sensor_id: str
    fault_type: FaultType = FaultType.NONE
    fault_mode: FaultMode = FaultMode.OFF
    original_state: bool = False  # 原始状态（故障前的状态）
    simulated_state: bool = False  # 模拟状态（故障后的状态）
    is_faulty: bool = False
    fault_timer: float = 0.0  # 故障计时器（用于间歇性故障）
    last_state: bool = False  # 上一个状态

    def apply_fault_mode(self, delta_seconds: float = 0.05) -> bool:
        """根据故障模式计算模拟状态"""
        if not self.is_faulty:
            self.last_state = self.original_state
            return self.original_state

        if self.fault_mode == FaultMode.STUCK_LOW:
            # 卡在低电平
            self.last_state = False
            return False
        elif self.fault_mode == FaultMode.STUCK_HIGH:
            # 卡在高电平
            self.last_state = True
            return True
        elif self.fault_mode == FaultMode.RANDOM:
            # 随机值
            state = random.choice([True, False])
            self.last_state = state
            return state
        elif self.fault_mode == FaultMode.SENSITIVITY_LOSS:
            # 灵敏度降低：正常触发，但有30%概率漏检
            if self.original_state:
                return random.random() > 0.3  # 70%概率正常触发
            return False
        elif self.fault_mode == FaultMode.RESPONSE_DELAY:
            # 响应延迟：状态变化延迟500ms
            self.fault_timer += delta_seconds
            if self.fault_timer >= 0.5:  # 500ms延迟
                self.last_state = self.original_state
                return self.original_state
            return self.last_state
        elif self.fault_mode == FaultMode.INTERMITTENT:
            # 间歇性故障：每2秒随机切换是否故障
            self.fault_timer += delta_seconds
            if self.fault_timer >= 2.0:
                self.fault_timer = 0.0
                # 50%概率正常，50%概率卡在当前状态
            # 在故障期间，保持上一个正常状态
            if random.random() < 0.5:
                return self.last_state
            return self.original_state
        else:
            self.last_state = self.original_state
            return self.original_state


@dataclass
class HopperFaultInfo:
    """中转斗传感器故障信息"""
    hopper_id: str

    # 故障模式
    switch_fault_mode: FaultMode = FaultMode.OFF
    weight_fault_mode: FaultMode = FaultMode.OFF
    belt_fault_mode: FaultMode = FaultMode.OFF

    # 原始值
    original_switch_state: bool = True  # True=开
    original_weight: float = 0.0  # 吨
    original_belt_speed: float = 1.0  # 皮带速度倍率

    # 模拟值（故障后）
    simulated_switch_state: bool = True
    simulated_weight: float = 0.0
    simulated_belt_speed: float = 1.0

    is_switch_faulty: bool = False
    is_weight_faulty: bool = False
    is_belt_faulty: bool = False

    # 称重故障参数
    weight_offset: float = 0.0  # 称重偏移量

    def apply_switch_fault(self) -> bool:
        """应用开关故障"""
        if not self.is_switch_faulty:
            return self.original_switch_state

        if self.switch_fault_mode == FaultMode.HOPPER_SWITCH_STUCK_CLOSED:
            return False  # 卡在关
        elif self.switch_fault_mode == FaultMode.HOPPER_SWITCH_STUCK_OPEN:
            return True  # 卡在开
        return self.original_switch_state

    def apply_weight_fault(self, original_weight: float) -> float:
        """应用称重故障"""
        if not self.is_weight_faulty:
            return original_weight

        if self.weight_fault_mode == FaultMode.HOPPER_WEIGHT_STUCK_ZERO:
            return 0.0  # 恒为0
        elif self.weight_fault_mode == FaultMode.HOPPER_WEIGHT_OFFSET:
            # 添加随机偏移 ±20%
            return original_weight * random.uniform(0.8, 1.2) + self.weight_offset
        return original_weight

    def apply_belt_fault(self, original_speed: float) -> float:
        """应用皮带故障"""
        if not self.is_belt_faulty:
            return original_speed

        if self.belt_fault_mode == FaultMode.BELT_SLIP:
            return original_speed * 0.5  # 打滑，速度减半
        elif self.belt_fault_mode == FaultMode.BELT_SPEED_VARIANCE:
            # 速度波动 ±20%
            return original_speed * random.uniform(0.8, 1.2)
        return original_speed


@dataclass
class RouteSensorSequence:
    """路线上的传感器序列"""
    route_id: str
    sensors: List[str] = field(default_factory=list)  # 按顺序排列的传感器ID列表

    def get_neighbor_sensors(self, sensor_id: str, count: int = 2) -> Tuple[List[str], List[str]]:
        """
        获取指定传感器的邻居传感器
        Returns: (前两个邻居, 后两个邻居)
        """
        try:
            idx = self.sensors.index(sensor_id)
        except ValueError:
            return [], []

        # 前邻居
        start = max(0, idx - count)
        prev_sensors = self.sensors[start:idx]

        # 后邻居
        end = min(len(self.sensors), idx + count + 1)
        next_sensors = self.sensors[idx + 1:end]

        return prev_sensors, next_sensors


class SensorFaultDiagnosis:
    """
    传感器故障诊断系统

    诊断逻辑：
    1. 对于路线上的传感器，检查其前后相邻的传感器状态
    2. 如果前后传感器都处于正常状态(值为1)，但当前传感器值为0
    3. 则判定该传感器可能出现故障
    4. 如果传感器是路线第一个或最后一个，则根据后两个或前两个传感器作为参考
    """

    def __init__(self):
        self.sensors: Dict[str, SensorFaultInfo] = {}
        self.hopper_sensors: Dict[str, HopperFaultInfo] = {}
        self.route_sensor_sequences: Dict[str, RouteSensorSequence] = {}
        self.faulty_sensors: Set[str] = set()
        self._init_sensor_info()
        self._build_route_sensor_sequences()

    def _init_sensor_info(self):
        """初始化传感器信息"""
        for sensor_id in config.SENSORS.keys():
            self.sensors[sensor_id] = SensorFaultInfo(sensor_id=sensor_id)

        # 初始化中转斗传感器信息
        for hopper_id in config.TRANSFER_HOPPERS.keys():
            self.hopper_sensors[hopper_id] = HopperFaultInfo(hopper_id=hopper_id)

    def _build_route_sensor_sequences(self):
        """
        构建每条路线上的传感器序列
        基于路线的皮带顺序，找出每个皮带对应的传感器
        """
        for route_id, route in config.FEED_ROUTES.items():
            sensors_in_route = []

            # 遍历路线上的皮带，收集皮带上的传感器
            for conv_id in route['conveyors']:
                # 找到该皮带上的所有传感器
                for sensor_id, sensor_config in config.SENSORS.items():
                    if sensor_config.get('conveyor') == conv_id:
                        if sensor_id not in sensors_in_route:
                            sensors_in_route.append(sensor_id)

            self.route_sensor_sequences[route_id] = RouteSensorSequence(
                route_id=route_id,
                sensors=sensors_in_route
            )

    def get_sensor_sequences_for_routes(self, route_ids: List[str]) -> List[str]:
        """
        获取指定路线上的所有传感器（合并去重）
        """
        all_sensors = []
        for route_id in route_ids:
            if route_id in self.route_sensor_sequences:
                sensors = self.route_sensor_sequences[route_id].sensors
                for s in sensors:
                    if s not in all_sensors:
                        all_sensors.append(s)
        return all_sensors

    def set_fault_mode(self, sensor_id: str, mode: FaultMode):
        """设置传感器的故障模式"""
        if sensor_id in self.sensors:
            fault_info = self.sensors[sensor_id]
            fault_info.fault_mode = mode
            fault_info.is_faulty = (mode != FaultMode.OFF)
            fault_info.fault_timer = 0.0

            # 根据故障模式设置故障类型
            if mode == FaultMode.STUCK_LOW:
                fault_info.fault_type = FaultType.STUCK_LOW
            elif mode == FaultMode.STUCK_HIGH:
                fault_info.fault_type = FaultType.STUCK_HIGH
            elif mode == FaultMode.RANDOM:
                fault_info.fault_type = FaultType.RANDOM_FLUCTUATION
            elif mode == FaultMode.SENSITIVITY_LOSS:
                fault_info.fault_type = FaultType.RANDOM_FLUCTUATION
            elif mode == FaultMode.RESPONSE_DELAY:
                fault_info.fault_type = FaultType.INTERMITTENT
            elif mode == FaultMode.INTERMITTENT:
                fault_info.fault_type = FaultType.INTERMITTENT
            else:
                fault_info.fault_type = FaultType.NONE

            if fault_info.is_faulty:
                self.faulty_sensors.add(sensor_id)
            else:
                self.faulty_sensors.discard(sensor_id)

    def clear_all_faults(self):
        """清除所有故障设置"""
        for sensor_id in self.sensors:
            self.sensors[sensor_id].fault_mode = FaultMode.OFF
            self.sensors[sensor_id].is_faulty = False
            self.sensors[sensor_id].fault_type = FaultType.NONE
        self.faulty_sensors.clear()

    def set_random_faults(self, sensor_ids: List[str], mode: FaultMode, count: int = 2):
        """
        随机选择指定传感器列表中的传感器设置为故障

        Args:
            sensor_ids: 可选的传感器列表
            mode: 故障模式
            count: 故障传感器数量
        """
        self.clear_all_faults()

        if not sensor_ids:
            return

        # 随机选择count个传感器
        selected = random.sample(sensor_ids, min(count, len(sensor_ids)))

        for sensor_id in selected:
            self.set_fault_mode(sensor_id, mode)

    def set_faults_on_active_routes(self, active_routes: List[str], mode: FaultMode, count: int = 2):
        """
        在活跃路线上随机设置故障传感器

        Args:
            active_routes: 活跃路线ID列表
            mode: 故障模式
            count: 故障传感器数量（1-2个）
        """
        # 获取活跃路线上的所有传感器
        all_sensors = self.get_sensor_sequences_for_routes(active_routes)

        # 如果活跃路线上没有传感器，使用所有传感器
        if not all_sensors:
            all_sensors = list(config.SENSORS.keys())

        self.set_random_faults(all_sensors, mode, count)

    def update_sensor_state(self, sensor_id: str, original_state: bool,
                           delta_seconds: float = 0.05) -> bool:
        """
        更新传感器状态，如果设置了故障则返回模拟的故障状态

        Args:
            sensor_id: 传感器ID
            original_state: 原始物理状态
            delta_seconds: 时间步长（秒），用于响应延迟故障

        Returns:
            最终生效的状态（可能是故障模拟后的状态）
        """
        if sensor_id in self.sensors:
            fault_info = self.sensors[sensor_id]
            fault_info.original_state = original_state

            if fault_info.is_faulty:
                fault_info.simulated_state = fault_info.apply_fault_mode(delta_seconds)
                return fault_info.simulated_state

        return original_state

    def diagnose_sensor(self, sensor_id: str, active_routes: List[str],
                       sensor_states: Dict[str, bool],
                       sensor_trigger_counts: Dict[str, int] = None,
                       sensor_hold_timers: Dict[str, int] = None) -> Tuple[bool, Optional[str]]:
        """
        诊断传感器是否出现故障

        诊断逻辑：
        1. 如果传感器当前为活跃状态，正常
        2. 如果传感器的保持计时器仍在运行但状态为0（故障导致无法保持），判定为故障

        Args:
            sensor_id: 要诊断的传感器ID
            active_routes: 当前活跃的路线列表
            sensor_states: 所有传感器的当前状态字典
            sensor_trigger_counts: 传感器触发次数字典
            sensor_hold_timers: 传感器保持计时器字典

        Returns:
            (是否故障, 故障原因描述)
        """
        # 如果传感器当前为活跃状态，正常
        current_state = sensor_states.get(sensor_id, False)
        if current_state:
            return False, None

        # 检查该传感器是否在活跃路线上
        on_active_route = False
        route_name = ""
        for route_id in active_routes:
            if route_id in self.route_sensor_sequences:
                seq = self.route_sensor_sequences[route_id]
                if sensor_id in seq.sensors:
                    on_active_route = True
                    route_name = config.FEED_ROUTES[route_id]['name']
                    break

        if not on_active_route:
            return False, None

        # 获取触发次数和保持计时器
        trigger_count = sensor_trigger_counts.get(sensor_id, 0) if sensor_trigger_counts else 0
        hold_timer = sensor_hold_timers.get(sensor_id, 0) if sensor_hold_timers else 0

        # 如果传感器被触发过但保持计时器已到期且状态为0，说明物料已离开，不判定
        if trigger_count > 0 and hold_timer == 0:
            return False, None

        # 获取故障模式
        fault_mode = self.sensors[sensor_id].fault_mode

        # 如果传感器被触发过但状态为0，判定为故障
        if trigger_count > 0 and not current_state:
            if fault_mode == FaultMode.STUCK_LOW:
                return True, f"{route_name}: {sensor_id}传感器故障(卡在低电平)"
            elif fault_mode == FaultMode.STUCK_HIGH:
                return True, f"{route_name}: {sensor_id}传感器故障(卡在高电平)"
            elif fault_mode == FaultMode.SENSITIVITY_LOSS:
                return True, f"{route_name}: {sensor_id}传感器故障(灵敏度降低)"
            elif fault_mode == FaultMode.RESPONSE_DELAY:
                return True, f"{route_name}: {sensor_id}传感器故障(响应延迟)"
            elif fault_mode == FaultMode.INTERMITTENT:
                return True, f"{route_name}: {sensor_id}传感器故障(间歇性)"
            else:
                return True, f"{route_name}: {sensor_id}传感器故障"

        # 如果设置了卡高故障但实际状态为0
        if fault_mode == FaultMode.STUCK_HIGH and not current_state:
            return True, f"{route_name}: {sensor_id}传感器故障(应卡高但为低)"

        return False, None

    def diagnose_all_sensors(self, active_routes: List[str],
                             sensor_states: Dict[str, bool],
                             sensor_trigger_counts: Dict[str, int] = None,
                             sensor_hold_timers: Dict[str, int] = None) -> List[Tuple[str, str]]:
        """
        诊断所有传感器

        Returns:
            故障传感器列表 [(sensor_id, 故障原因), ...]
        """
        faults = []
        for sensor_id in sensor_states.keys():
            is_fault, reason = self.diagnose_sensor(sensor_id, active_routes, sensor_states, sensor_trigger_counts, sensor_hold_timers)
            if is_fault and reason:
                faults.append((sensor_id, reason))
        return faults

    def get_faulty_sensor_ids(self) -> Set[str]:
        """获取所有设置了故障模式的传感器ID"""
        return self.faulty_sensors.copy()

    def get_sensor_fault_info(self, sensor_id: str) -> SensorFaultInfo:
        """获取传感器故障信息"""
        return self.sensors.get(sensor_id, SensorFaultInfo(sensor_id=sensor_id))

    def is_sensor_faulty(self, sensor_id: str) -> bool:
        """检查传感器是否设置了故障模式"""
        return sensor_id in self.faulty_sensors

    def get_fault_summary(self) -> Dict:
        """获取故障摘要"""
        summary = {
            'total_faulty': len(self.faulty_sensors),
            'faulty_sensors': [],
            'by_mode': {
                'stuck_low': [],
                'random': []
            }
        }

        for sensor_id in self.faulty_sensors:
            fault_info = self.sensors[sensor_id]
            info = {
                'sensor_id': sensor_id,
                'mode': fault_info.fault_mode.value,
                'type': fault_info.fault_type.value
            }
            summary['faulty_sensors'].append(info)

            if fault_info.fault_mode == FaultMode.STUCK_LOW:
                summary['by_mode']['stuck_low'].append(sensor_id)
            elif fault_info.fault_mode == FaultMode.RANDOM:
                summary['by_mode']['random'].append(sensor_id)

        return summary

    def get_available_sensors_for_route(self, route_id: str) -> List[str]:
        """获取指定路线上的所有传感器"""
        if route_id in self.route_sensor_sequences:
            return self.route_sensor_sequences[route_id].sensors.copy()
        return []

    def get_route_sensor_info(self, route_id: str) -> Dict[str, dict]:
        """获取指定路线上所有传感器的详细信息"""
        result = {}
        if route_id in self.route_sensor_sequences:
            for sensor_id in self.route_sensor_sequences[route_id].sensors:
                fault_info = self.sensors.get(sensor_id)
                if fault_info:
                    result[sensor_id] = {
                        'is_faulty': fault_info.is_faulty,
                        'fault_mode': fault_info.fault_mode.value,
                        'fault_type': fault_info.fault_type.value
                    }
        return result

    # ============ 中转斗传感器故障相关方法 ============

    def set_hopper_switch_fault(self, hopper_id: str, mode: FaultMode):
        """设置中转斗开关故障"""
        if hopper_id in self.hopper_sensors:
            info = self.hopper_sensors[hopper_id]
            info.switch_fault_mode = mode
            info.is_switch_faulty = (mode not in [FaultMode.OFF, FaultMode.HOPPER_SWITCH_STUCK_OPEN])

            if mode == FaultMode.HOPPER_SWITCH_STUCK_CLOSED:
                info.simulated_switch_state = False  # 卡在关
            elif mode == FaultMode.HOPPER_SWITCH_STUCK_OPEN:
                info.simulated_switch_state = True  # 卡在开
                info.is_switch_faulty = True

    def set_hopper_weight_fault(self, hopper_id: str, mode: FaultMode):
        """设置中转斗称重传感器故障"""
        if hopper_id in self.hopper_sensors:
            info = self.hopper_sensors[hopper_id]
            info.weight_fault_mode = mode
            info.is_weight_faulty = (mode != FaultMode.OFF)

    def set_hopper_belt_fault(self, hopper_id: str, mode: FaultMode):
        """设置中转斗相关皮带故障"""
        if hopper_id in self.hopper_sensors:
            info = self.hopper_sensors[hopper_id]
            info.belt_fault_mode = mode
            info.is_belt_faulty = (mode != FaultMode.OFF)

    def update_hopper_states(self, hopper_id: str, switch_state: bool, weight: float,
                           belt_speed: float = 1.0):
        """更新中转斗传感器状态"""
        if hopper_id in self.hopper_sensors:
            info = self.hopper_sensors[hopper_id]
            info.original_switch_state = switch_state
            info.original_weight = weight
            info.original_belt_speed = belt_speed

            # 应用开关故障
            info.simulated_switch_state = info.apply_switch_fault()

            # 应用称重故障
            info.simulated_weight = info.apply_weight_fault(weight)

            # 应用皮带故障
            info.simulated_belt_speed = info.apply_belt_fault(belt_speed)

    def get_simulated_hopper_states(self, hopper_id: str) -> dict:
        """获取中转斗的模拟状态（故障后的状态）"""
        if hopper_id in self.hopper_sensors:
            info = self.hopper_sensors[hopper_id]
            return {
                'switch_open': info.simulated_switch_state,
                'weight': info.simulated_weight,
                'belt_speed': info.simulated_belt_speed,
                'is_switch_faulty': info.is_switch_faulty,
                'is_weight_faulty': info.is_weight_faulty,
                'is_belt_faulty': info.is_belt_faulty,
            }
        return {'switch_open': True, 'weight': 0, 'belt_speed': 1.0,
                'is_switch_faulty': False, 'is_weight_faulty': False, 'is_belt_faulty': False}

    def diagnose_hopper_sensors(self, hopper_id: str, route_name: str = "") -> List[Tuple[str, str]]:
        """诊断中转斗传感器故障"""
        faults = []
        if hopper_id not in self.hopper_sensors:
            return faults

        info = self.hopper_sensors[hopper_id]
        name = route_name or f"中转斗{hopper_id}"

        # 诊断开关故障
        if info.is_switch_faulty:
            if info.switch_fault_mode == FaultMode.HOPPER_SWITCH_STUCK_CLOSED:
                faults.append((f"{hopper_id}_switch", f"{name}: 开关故障(卡在关)"))
            elif info.switch_fault_mode == FaultMode.HOPPER_SWITCH_STUCK_OPEN:
                faults.append((f"{hopper_id}_switch", f"{name}: 开关故障(卡在开)"))

        # 诊断称重传感器故障
        if info.is_weight_faulty:
            if info.weight_fault_mode == FaultMode.HOPPER_WEIGHT_STUCK_ZERO:
                faults.append((f"{hopper_id}_weight", f"{name}: 称重传感器故障(显示0)"))
            elif info.weight_fault_mode == FaultMode.HOPPER_WEIGHT_OFFSET:
                faults.append((f"{hopper_id}_weight", f"{name}: 称重传感器故障(偏移)"))

        # 诊断皮带故障
        if info.is_belt_faulty:
            if info.belt_fault_mode == FaultMode.BELT_SLIP:
                faults.append((f"{hopper_id}_belt", f"{name}: 皮带打滑"))
            elif info.belt_fault_mode == FaultMode.BELT_SPEED_VARIANCE:
                faults.append((f"{hopper_id}_belt", f"{name}: 皮带速度波动"))

        return faults

    def clear_hopper_faults(self, hopper_id: str = None):
        """清除中转斗故障设置"""
        if hopper_id:
            if hopper_id in self.hopper_sensors:
                info = self.hopper_sensors[hopper_id]
                info.switch_fault_mode = FaultMode.OFF
                info.weight_fault_mode = FaultMode.OFF
                info.belt_fault_mode = FaultMode.OFF
                info.is_switch_faulty = False
                info.is_weight_faulty = False
                info.is_belt_faulty = False
        else:
            # 清除所有
            for info in self.hopper_sensors.values():
                info.switch_fault_mode = FaultMode.OFF
                info.weight_fault_mode = FaultMode.OFF
                info.belt_fault_mode = FaultMode.OFF
                info.is_switch_faulty = False
                info.is_weight_faulty = False
                info.is_belt_faulty = False

    def get_all_hopper_faults(self) -> List[Tuple[str, str]]:
        """获取所有中转斗的故障诊断结果"""
        faults = []
        for hopper_id in self.hopper_sensors.keys():
            faults.extend(self.diagnose_hopper_sensors(hopper_id))
        return faults

    # ============ 中转斗开关实际故障诊断（基于传感器状态对比）============

    def diagnose_hopper_switch_by_sensor(
        self,
        hopper_id: str,
        route_id: str,
        prev_sensor_id: str,
        prev_sensor_state: bool,
        next_sensor_id: str,
        next_sensor_state: bool,
        hopper_weight: float,
        ui_switch_state: bool,
        effective_switch_state: bool,
        hopper_name: str = ""
    ) -> Tuple[bool, Optional[str]]:
        """
        基于传感器状态对比诊断中转斗开关是否卡住

        诊断逻辑：
        通过对比状态栏设置(ui_switch_state)与实际生效状态(effective_switch_state)来判断：
        - 如果状态栏设置为"关"，但开关实际是"开"，物料持续流出 → 卡开
        - 如果状态栏设置为"开"，但开关实际是"关"，物料无法流出 → 卡关

        Args:
            hopper_id: 中转斗ID
            route_id: 路线ID
            prev_sensor_id: 前一个传感器ID
            prev_sensor_state: 前一个传感器状态
            next_sensor_id: 后一个传感器ID
            next_sensor_state: 后一个传感器状态
            hopper_weight: 中转斗称重值（吨）
            ui_switch_state: 状态栏设置的开关状态（True=开，False=关）
            effective_switch_state: 实际生效的开关状态（True=开，False=关）
            hopper_name: 中转斗中文名称

        Returns:
            (is_stuck, fault_description)
        """
        # 获取中文名称
        name = hopper_name or hopper_id

        # 情况1：卡开故障
        # 状态栏设置为关(ui_switch_state=False)，但物料仍持续流出
        # 现象：前传感器有料、后传感器有料、斗里无物料(称重=0)
        # 原因：开关实际卡在开的位置
        if (prev_sensor_state and next_sensor_state and hopper_weight < 0.1
                and not ui_switch_state and effective_switch_state):
            return True, f"{name}: 开关故障(卡在开)"

        # 情况2：卡关故障
        # 状态栏设置为开(ui_switch_state=True)，但物料无法流出
        # 现象：前传感器有料、后传感器无料、斗里开始有料(称重>0)
        # 原因：开关实际卡在关的位置
        # 注意：一旦称重开始增加（>0）就应立即诊断，无需等到最大值
        if (prev_sensor_state and not next_sensor_state and hopper_weight > 0
                and ui_switch_state and not effective_switch_state):
            return True, f"{name}: 开关故障(卡在关)"

        return False, None

    def diagnose_all_hoppers_by_sensors(
        self,
        hoppers: Dict[str, 'TransferHopper'],
        sensors: Dict[str, 'Sensor'],
        active_routes: List[str],
        route_hopper_sensor_map: Dict[str, Dict[str, Tuple[str, str]]]
    ) -> List[Tuple[str, str]]:
        """
        诊断所有中转斗的开关故障

        Args:
            hoppers: 中转斗字典
            sensors: 传感器字典
            active_routes: 活跃路线列表
            route_hopper_sensor_map: 路线到中转斗传感器的映射
                {route_id: {hopper_id: (prev_sensor_id, next_sensor_id)}}

        Returns:
            故障列表 [(hopper_id, fault_description), ...]
        """
        faults = []

        for route_id in active_routes:
            if route_id not in route_hopper_sensor_map:
                continue

            hopper_sensor_map = route_hopper_sensor_map[route_id]

            for hopper_id, (prev_sensor_id, next_sensor_id) in hopper_sensor_map.items():
                if hopper_id not in hoppers:
                    continue

                hopper = hoppers[hopper_id]

                # 获取传感器状态
                prev_sensor = sensors.get(prev_sensor_id)
                next_sensor = sensors.get(next_sensor_id)

                prev_state = prev_sensor.is_active if prev_sensor else False
                next_state = next_sensor.is_active if next_sensor else False

                # 获取中转斗称重值
                hopper_weight = hopper.get_display_weight()

                # 获取实际生效的开关状态（考虑故障）
                ui_state = hopper.is_open
                effective_state = hopper.get_effective_switch_state()

                # 获取中文名称
                hopper_name = hopper.name if hasattr(hopper, 'name') else hopper_id

                # 诊断
                is_stuck, fault_desc = self.diagnose_hopper_switch_by_sensor(
                    hopper_id, route_id,
                    prev_sensor_id, prev_state,
                    next_sensor_id, next_state,
                    hopper_weight, ui_state, effective_state, hopper_name
                )

                if is_stuck and fault_desc:
                    faults.append((hopper_id, fault_desc))

        return faults
