"""
PLC执行器控制与安全互锁 —— 纯函数，可直接翻译为 PLC 梯形图/ST语言

零依赖：不 import PyQt5、config、pos 或上位机模块。
所有函数接收当前状态快照，返回执行器命令字典。
"""
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum


class ActuatorAction(Enum):
    """执行器动作"""
    START = "start"
    STOP = "stop"
    OPEN = "open"
    CLOSE = "close"
    NOOP = "noop"


# ── 皮带控制 ──────────────────────────────────────────────

def compute_route_belt_commands(
    route_conveyors: List[str],
    final_conveyor: str,
    is_feeding: bool,
    is_clearing: bool,
    cart_at_target: bool,
    clearing_strategy: str = 'reverse',
) -> Dict[str, ActuatorAction]:
    """根据路线状态计算每条皮带的启停命令

    规则（安全互锁）：
    1. FEEDING + 小车在目标位置 → 全部皮带启动
    2. CLEARING 反序 → 全部皮带运行，终点皮带清空完成后停止
    3. CLEARING 顺序 → 终点皮带立即停止，其他皮带保持运行
    4. 小车移动中 → 非终点皮带运行，终点皮带停止
    5. STANDBY/WAITING → 全部皮带停止

    Args:
        route_conveyors: 路线上的皮带ID列表（按物料流向）
        final_conveyor: 终点皮带（小车所在皮带）
        is_feeding: 是否在补料状态
        is_clearing: 是否在清空状态
        cart_at_target: 小车是否已到达目标位置
        clearing_strategy: 清空策略 ('reverse' | 'sequential' | 'column_switch')

    Returns:
        {conv_id: ActuatorAction}
    """
    commands: Dict[str, ActuatorAction] = {}

    if is_feeding and cart_at_target:
        # 正常上料：全部皮带运行
        for cid in route_conveyors:
            commands[cid] = ActuatorAction.START

    elif is_clearing:
        if clearing_strategy == 'sequential':
            # 顺序清空：终点皮带立即停止（料不再进入小车），其他皮带继续运行排空余料
            for cid in route_conveyors:
                if cid == final_conveyor:
                    commands[cid] = ActuatorAction.STOP
                else:
                    commands[cid] = ActuatorAction.START
        else:
            # 反序/换列清空：全部皮带运行，终点皮带排空余料后停止
            for cid in route_conveyors:
                commands[cid] = ActuatorAction.START

    elif not cart_at_target:
        # 小车移动中：非终点皮带保持运行，终点皮带停止
        for cid in route_conveyors:
            if cid == final_conveyor:
                commands[cid] = ActuatorAction.STOP
            else:
                commands[cid] = ActuatorAction.START

    else:
        # 其他状态（STANDBY/WAITING/IDLE）：停止全部
        for cid in route_conveyors:
            commands[cid] = ActuatorAction.STOP

    return commands


def compute_clear_completion_belt_commands(
    route_conveyors: List[str],
    all_sensors_cleared: bool,
) -> Dict[str, ActuatorAction]:
    """清空完成时：停止全部皮带"""
    if all_sensors_cleared:
        return {cid: ActuatorAction.STOP for cid in route_conveyors}
    return {}


def compute_endpoint_belt_stop_commands(
    final_conveyor: str,
) -> Dict[str, ActuatorAction]:
    """仅停止终点皮带（用于触发清空时）"""
    return {final_conveyor: ActuatorAction.STOP}


# ── 中转斗控制 ────────────────────────────────────────────

def compute_hopper_commands(
    assigned_hoppers: List[str],
    is_feeding: bool,
    cart_at_target: bool,
    hopper_states: Dict[str, bool],  # hopper_id → current is_open
) -> Dict[str, ActuatorAction]:
    """根据路线状态计算中转斗开关命令

    规则：
    1. FEEDING + 小车到位 → 打开所有分配的中转斗
    2. 小车移动中 → 关闭所有斗（防止物料落在移动的小车上）
    3. CLEARING/WAITING/STANDBY → 关闭所有斗

    Args:
        assigned_hoppers: 路线分配的中转斗ID列表
        is_feeding: 是否在补料状态
        cart_at_target: 小车是否已到达目标位置
        hopper_states: 各斗当前开关状态

    Returns:
        {hopper_id: ActuatorAction} — 仅返回需要变更的斗
    """
    commands: Dict[str, ActuatorAction] = {}

    if is_feeding and cart_at_target:
        for hid in assigned_hoppers:
            if not hopper_states.get(hid, False):
                commands[hid] = ActuatorAction.OPEN
    else:
        for hid in assigned_hoppers:
            if hopper_states.get(hid, False):
                commands[hid] = ActuatorAction.CLOSE

    return commands


# ── 小车控制 ──────────────────────────────────────────────

def compute_cart_target_position(
    target_bin: str,
    cart_id: str,
) -> Optional[int]:
    """根据目标料仓计算小车应移动到的位置

    Args:
        target_bin: 目标料仓ID（如 "P1-5"）
        cart_id: 小车ID

    Returns:
        目标位置（1-7），或 None 表示不需要移动
    """
    if not target_bin or '-' not in target_bin:
        return None

    try:
        return int(target_bin.split('-')[1])
    except (ValueError, IndexError):
        return None


def compute_cart4_target_position(target_bin: str) -> Optional[int]:
    """D5/D6 小车4 的目标位置计算 (S1-S12)"""
    if not target_bin or not target_bin.startswith('S'):
        return None
    try:
        num = int(target_bin[1:])
        return (num - 1) % 6 + 1
    except ValueError:
        return None


def should_move_cart(
    current_position: int,
    target_position: Optional[int],
) -> bool:
    """判断小车是否需要移动"""
    if target_position is None:
        return False
    return current_position != target_position


# ── 安全互锁 ──────────────────────────────────────────────

def check_resource_availability(
    route_hoppers: List[str],
    resource_locks: Dict[str, Optional[str]],
    requesting_route: str,
) -> Tuple[bool, Optional[str]]:
    """检查路线所需资源（中转斗）是否可用

    PLC 等价：互锁继电器

    Args:
        route_hoppers: 需要的资源ID列表
        resource_locks: {资源ID: 占用路线ID 或 None}
        requesting_route: 请求资源的路线ID

    Returns:
        (可用?, 被占用的资源ID)
    """
    for rid in route_hoppers:
        owner = resource_locks.get(rid)
        if owner is not None and owner != requesting_route:
            return False, rid
    return True, None


def check_cart_busy(
    cart_id: str,
    active_routes: Dict[str, 'RouteStateSnapshot'],
    exclude_route: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """检查小车是否被其他路线占用（移动中或补料中）

    PLC 等价：小车运动互锁

    Args:
        cart_id: 小车ID
        active_routes: {route_id: RouteStateSnapshot}
        exclude_route: 排除的路线ID

    Returns:
        (繁忙?, 占用路线ID)
    """
    BUSY_STATES = {'moving_to_target', 'feeding', 'clearing'}
    for route_id, snap in active_routes.items():
        if route_id == exclude_route:
            continue
        if snap.cart_id != cart_id:
            continue
        if snap.state in BUSY_STATES or snap.cart_moving:
            return True, route_id
    return False, None


class RouteStateSnapshot:
    """路线状态快照 — 用于安全互锁检查"""

    __slots__ = ('route_id', 'state', 'cart_id', 'cart_moving', 'target_bin')

    def __init__(self, route_id: str, state: str, cart_id: str,
                 cart_moving: bool = False, target_bin: str = ''):
        self.route_id = route_id
        self.state = state
        self.cart_id = cart_id
        self.cart_moving = cart_moving
        self.target_bin = target_bin


def check_hopper_interlock(
    hopper_states: Dict[str, bool],
    downstream_hopper_ids: List[str],
    upstream_hopper_ids: List[str],
) -> List[str]:
    """中转斗联锁：防止上游斗开后物料冲入未准备好的下游斗

    规则：
    - 如果上游斗打开，下游斗也必须打开（或下游已满）
    - 如果下游斗关闭，上游斗必须关闭

    Args:
        hopper_states: {hopper_id: is_open}
        downstream_hopper_ids: 下游斗ID列表
        upstream_hopper_ids: 上游斗ID列表

    Returns:
        需要关闭的斗ID列表（违反互锁的上游斗）
    """
    violations: List[str] = []

    for upstream in upstream_hopper_ids:
        if not hopper_states.get(upstream, False):
            continue
        # 上游斗开着，检查所有下游斗
        for downstream in downstream_hopper_ids:
            if not hopper_states.get(downstream, False):
                violations.append(upstream)
                break

    return violations


def compute_emergency_stop_commands(
    conveyors: List[str],
    hoppers: List[str],
) -> Tuple[Dict[str, ActuatorAction], Dict[str, ActuatorAction]]:
    """急停命令：立即停止全部皮带、关闭全部斗

    PLC 等价：急停继电器触发后，所有输出置为安全状态

    Returns:
        (belt_commands, hopper_commands)
    """
    belt_cmds = {cid: ActuatorAction.STOP for cid in conveyors}
    hopper_cmds = {hid: ActuatorAction.CLOSE for hid in hoppers}
    return belt_cmds, hopper_cmds
