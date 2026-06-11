"""
PLC运行时主扫描循环 —— 将所有子模块串联为等效的 PLC 扫描周期

扫描周期结构（与真实 PLC 一致）：
  1. 读取输入快照（不可变）
  2. 执行逻辑（纯函数链）
  3. 写入输出（命令字典）

接口：
  scan(inputs: PlcInputs) → PlcOutputs

可直接翻译为 PLC 主程序（OB1）：
  - 皮带追踪 → 高速计数器 + 比较指令
  - 状态引擎 → 结构化文本 CASE 语句
  - 执行器命令 → 数字量输出线圈
"""
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

from controllers.plc_runtime.actuator import (
    ActuatorAction,
    compute_route_belt_commands,
    compute_endpoint_belt_stop_commands,
    compute_clear_completion_belt_commands,
    compute_hopper_commands,
    compute_cart_target_position,
    compute_cart4_target_position,
    should_move_cart,
    check_resource_availability,
    compute_emergency_stop_commands,
    RouteStateSnapshot,
)
from controllers.plc_runtime.material_tracker import (
    BeltState,
    BeltMaterial,
    tick_materials,
    add_material_to_belt,
    check_proximity_sensor,
    check_material_at_end,
    remove_arrived_materials,
    get_total_weight_on_belt,
)

# 延迟导入 — 仅在 scan() 中需要时导入
# state_transition_engine 和 route_state_manager 保持独立


@dataclass(frozen=True)
class PlcInputs:
    """PLC 扫描周期的输入快照 — 不可变

    所有传感器值、执行器状态、路线上下文在当前周期的快照。
    扫描期间不被修改，确保确定性。
    """
    time_ms: float                              # 当前时间戳（秒）
    delta_seconds: float                        # 距上次扫描的时间步长

    # 传感器读数
    level_sensors: Dict[str, float]             # bin_id → 料位百分比 (0-100)
    proximity_sensors: Dict[str, bool]           # sensor_id → 是否触发
    hopper_weights: Dict[str, float]             # hopper_id → 当前重量（吨）

    # 执行器状态
    conveyor_states: Dict[str, bool]             # conv_id → is_running
    conveyor_speeds: Dict[str, float]            # conv_id → speed_mps
    hopper_states: Dict[str, bool]               # hopper_id → is_open
    cart_positions: Dict[str, int]               # cart_id → 当前位置 (1-7)

    # 路线上下文
    active_routes: Set[str]                     # 活跃路线集
    route_states: Dict[str, str]                # route_id → state_name
    route_hoppers: Dict[str, List[str]]          # route_id → [hopper_id]
    route_carts: Dict[str, str]                  # route_id → cart_id
    route_targets: Dict[str, str]                # route_id → target_bin
    route_conveyors: Dict[str, List[str]]        # route_id → [conv_id]
    route_cart_moving: Dict[str, bool]           # route_id → cart_moving
    cleared_sensors: Dict[str, Set[str]]         # route_id → {cleared_sensor_ids}

    # 皮带追踪状态
    belt_materials: Dict[str, List[BeltMaterial]] = field(default_factory=dict)

    # 急停
    emergency_stop: bool = False


@dataclass
class PlcOutputs:
    """PLC 扫描周期的输出 — 执行器命令"""
    # 执行器命令
    conveyor_commands: Dict[str, ActuatorAction] = field(default_factory=dict)
    hopper_commands: Dict[str, ActuatorAction] = field(default_factory=dict)
    cart_targets: Dict[str, int] = field(default_factory=dict)

    # 状态变更通知
    route_state_changes: List[Tuple[str, str, str]] = field(default_factory=list)  # (route_id, old, new)
    sensor_events: List[Tuple[str, bool, List[str]]] = field(default_factory=list)  # (sensor_id, triggered, [material_ids])

    # 物料到达事件
    material_arrivals: Dict[str, List[BeltMaterial]] = field(default_factory=dict)  # conv_id → [arrived]

    # 急停标志
    emergency_stop_active: bool = False

    # 告警
    alarms: List[str] = field(default_factory=list)


class PlcRuntime:
    """PLC 运行时 — 模拟一个 PLC 扫描周期的主程序"""

    def __init__(self):
        # 内部皮带追踪状态
        self._belt_tracking: Dict[str, BeltState] = {}
        self._material_counter: int = 0

    def register_belt(self, belt_id: str, length_m: float):
        """注册一条皮带到追踪系统"""
        self._belt_tracking[belt_id] = BeltState(
            belt_id=belt_id,
            length_m=length_m,
        )

    def register_belts(self, belts: Dict[str, float]):
        """批量注册皮带 {belt_id: length_m}"""
        for bid, length in belts.items():
            self.register_belt(bid, length)

    def spawn_material(self, belt_id: str, weight_tons: float = 0.1,
                       current_time: float = 0.0) -> Optional[str]:
        """在上料点生成一个新物料

        Returns:
            物料ID，失败返回 None
        """
        self._material_counter += 1
        mat_id = f"mat_{self._material_counter}"
        ok = add_material_to_belt(
            self._belt_tracking, belt_id, mat_id,
            weight_tons=weight_tons, current_time=current_time,
        )
        return mat_id if ok else None

    def scan(self, inputs: PlcInputs) -> PlcOutputs:
        """执行一个 PLC 扫描周期

        Args:
            inputs: 本周期输入快照

        Returns:
            本周期输出命令
        """
        outputs = PlcOutputs()

        # ── 1. 急停检查 ──
        if inputs.emergency_stop:
            outputs.emergency_stop_active = True
            belt_cmds, hopper_cmds = compute_emergency_stop_commands(
                list(self._belt_tracking.keys()),
                list(inputs.hopper_states.keys()),
            )
            outputs.conveyor_commands = belt_cmds
            outputs.hopper_commands = hopper_cmds
            return outputs

        # ── 2. 同步皮带追踪状态 ──
        for belt_id, belt in self._belt_tracking.items():
            belt.is_running = inputs.conveyor_states.get(belt_id, False)
            belt.speed_mps = inputs.conveyor_speeds.get(belt_id, 0.0)

        # ── 3. 物料位置更新 ──
        arrived = tick_materials(self._belt_tracking, inputs.delta_seconds)
        outputs.material_arrivals = arrived

        # ── 4. 接近开关检测 ──
        for belt_id, belt in self._belt_tracking.items():
            if not belt.is_running or not belt.materials:
                continue
            # 检测该皮带上是否有物料经过接近开关
            # sensor_config 中的 distance_from_start 需要外部提供
            # 此处由调用方负责将距离信息编码到 proximity_sensors 输入中

        # ── 5. 路线状态机处理 ──
        for route_id in inputs.active_routes:
            state = inputs.route_states.get(route_id, 'idle')
            cart_id = inputs.route_carts.get(route_id, '')
            cart_pos = inputs.cart_positions.get(cart_id, 1)
            target_bin = inputs.route_targets.get(route_id, '')

            # 小车目标位置计算
            if cart_id == 'Cart4':
                target_pos = compute_cart4_target_position(target_bin)
            else:
                target_pos = compute_cart_target_position(target_bin, cart_id)

            # 小车是否需要移动
            cart_moving = inputs.route_cart_moving.get(route_id, False)
            cart_at_target = not should_move_cart(cart_pos, target_pos)

            # 执行器命令
            conveyors = inputs.route_conveyors.get(route_id, [])
            final_conv = conveyors[-1] if conveyors else ''
            hoppers = inputs.route_hoppers.get(route_id, [])

            if state in ('feeding', 'clearing'):
                # 皮带命令
                belt_cmds = compute_route_belt_commands(
                    conveyors, final_conv,
                    is_feeding=(state == 'feeding'),
                    is_clearing=(state == 'clearing'),
                    cart_at_target=cart_at_target,
                )
                for cid, action in belt_cmds.items():
                    if action != ActuatorAction.NOOP:
                        outputs.conveyor_commands[cid] = action

                # 斗命令
                hopper_cmds = compute_hopper_commands(
                    hoppers,
                    is_feeding=(state == 'feeding'),
                    cart_at_target=cart_at_target,
                    hopper_states=inputs.hopper_states,
                )
                for hid, action in hopper_cmds.items():
                    outputs.hopper_commands[hid] = action

            # 小车目标位置
            if target_pos is not None:
                outputs.cart_targets[cart_id] = target_pos

        # ── 6. 清空完成检测 ──
        for route_id in inputs.active_routes:
            state = inputs.route_states.get(route_id, '')
            if state != 'clearing':
                continue
            cleared = inputs.cleared_sensors.get(route_id, set())
            conveyors = inputs.route_conveyors.get(route_id, [])
            # 所有传感器已清空 → 停止全部皮带
            all_cleared = len(conveyors) > 0  # 简化判定，实际由 route_state_manager 负责
            # 注：传感器清空判定由 route_state_manager 的 is_route_cleared 负责
            # PlcRuntime 只负责执行器控制部分

        return outputs

    def get_belt_weight(self, belt_id: str) -> float:
        """获取皮带上的物料总重量"""
        belt = self._belt_tracking.get(belt_id)
        return get_total_weight_on_belt(belt) if belt else 0.0

    def get_belt_material_count(self, belt_id: str) -> int:
        """获取皮带上的物料数量"""
        belt = self._belt_tracking.get(belt_id)
        return len(belt.materials) if belt else 0

    def reset(self):
        """重置所有内部状态"""
        self._belt_tracking.clear()
        self._material_counter = 0
