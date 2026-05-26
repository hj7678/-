"""
路线状态机管理器 - Route State Manager
根据控制策略管理各路线的状态转换

状态定义:
- IDLE: 路线空闲，未启用
- FEEDING: 正常补料（状态一）
- CLEARING: 清空余料（状态二）
- WAITING: 停机待料（状态三）

状态转换:
- IDLE → FEEDING: 用户启动路线
- FEEDING → CLEARING: 料位达到阈值
- CLEARING → WAITING: 皮带余料清空完毕
- WAITING → FEEDING: 用户点击恢复上料
- CLEARING/WAITING → IDLE: 用户停止路线（需先完成余料清空）
"""

from enum import Enum
from typing import Dict, Optional, Set, List
from dataclasses import dataclass, field
import config


class RouteState(Enum):
    """路线状态枚举"""
    IDLE = "idle"           # 路线空闲
    FEEDING = "feeding"     # 正常补料
    CLEARING = "clearing"   # 清空余料
    WAITING = "waiting"     # 停机待料
    MOVING_TO_TARGET = "moving_to_target"  # 小车移动到目标位置中


@dataclass
class RouteContext:
    """路线上下文，存储路线相关数据"""
    route_id: str
    state: RouteState = RouteState.IDLE
    target_bin: Optional[str] = None          # 目标料仓
    assigned_hoppers: List[str] = field(default_factory=list)   # 分配的中转斗
    assigned_cart: Optional[str] = None         # 分配的小车
    feed_point: Optional[str] = None           # 上料点
    final_weights: Dict[str, float] = field(default_factory=dict)  # 各中转斗的最终称重 {hopper_id: weight}
    current_weights: Dict[str, float] = field(default_factory=dict)  # 各中转斗的当前称重
    pending_release_weights: Dict[str, float] = field(default_factory=dict)  # 待释放的余料重量 {hopper_id: weight}
    material_on_belt: Dict[str, float] = field(default_factory=dict)  # 各皮带余料量(吨)
    cleared_sensors: Set[str] = field(default_factory=set)  # 已清空的接近开关
    cart_target_position: int = 1               # 小车目标位置（Cart1-3使用）
    cart_moving: bool = False                  # 小车是否在移动中
    previous_state: Optional[str] = None       # 上一状态（用于检测CLEARING→FEEDING切换）


class RouteStateManager:
    """路线状态机管理器"""

    # 路线到中转斗的映射
    # 注意：中转斗对应关系应与pos.py中FEED_ROUTES的hoppers列表一致
    ROUTE_HOPPERS = {
        'route1': ['hopper1', 'hopper3', 'hopper4'],  # 无hopper5
        'route2': ['hopper1', 'hopper3', 'hopper4'],  # 无hopper5
        'route3': ['hopper1', 'hopper3', 'hopper4'],  # 无hopper5
        'route4': ['hopper2', 'hopper6'],
        'route5': ['hopper2', 'hopper6', 'hopper7'],
        'route6': [],  # 无中转斗
        'route7': ['hopper5'],
        'route8': [],  # 无中转斗
        'route9': ['hopper5'],
    }

    # 路线到终点小车的映射
    ROUTE_CARTS = {
        'route1': 'Cart1',
        'route2': 'Cart1',
        'route3': 'Cart1',
        'route4': 'Cart3',
        'route5': 'Cart4',
        'route6': 'Cart3',
        'route7': 'Cart2',
        'route8': 'Cart3',
        'route9': 'Cart2',
    }

    # 路线到上料点的映射
    ROUTE_FEED_POINTS = {
        'route1': 'feed1_1',
        'route2': 'feed1_2',
        'route3': 'feed2_1',
        'route4': 'feed2_2',
        'route5': 'feed2_2',
        'route6': 'feed3',
        'route7': 'feed3',
        'route8': 'silo_out',
        'route9': 'silo_out',
    }

    # 路线经过的皮带上接近开关列表
    ROUTE_PROXIMITY_SENSORS = {
        'route1': ['S-E1', 'S-E4', 'S-E8', 'S-E10', 'S-D7'],
        'route2': ['S-E2', 'S-E4', 'S-E8', 'S-E10', 'S-D7'],
        'route3': ['S-E5', 'S-E8', 'S-E10', 'S-D7'],
        'route4': ['S-E6', 'S-E7', 'S-E9', 'S-D9'],
        'route5': ['S-E6', 'S-E7', 'S-E9', 'S-D9', 'S-D5', 'S-D6'],
        'route6': ['S-D13', 'S-D1', 'S-D3', 'S-D9'],
        'route7': ['S-D13', 'S-D2', 'S-D4', 'S-D8'],
        'route8': ['S-D1', 'S-D3', 'S-D9'],
        'route9': ['S-D2', 'S-D4', 'S-D8'],
    }

    # 资源锁
    _resource_locks: Dict[str, Optional[str]] = {
        'hopper1': None, 'hopper2': None, 'hopper3': None, 'hopper4': None,
        'hopper5': None, 'hopper6': None, 'hopper7': None,
        'Cart1': None, 'Cart2': None, 'Cart3': None, 'Cart4': None,
    }

    def __init__(self):
        self.routes: Dict[str, RouteContext] = {}
        self._state_change_callback = None
        self._initialize_routes()

    def set_state_change_callback(self, callback):
        """设置状态变更回调 callback(route_id, old_state, new_state)"""
        self._state_change_callback = callback

    def _notify_state_change(self, route_id: str, old_state, new_state):
        if self._state_change_callback:
            self._state_change_callback(route_id, old_state, new_state)

    def _initialize_routes(self):
        """初始化所有路线"""
        for route_id in config.FEED_ROUTES.keys():
            self.routes[route_id] = RouteContext(
                route_id=route_id,
                state=RouteState.IDLE,
                assigned_hoppers=self.ROUTE_HOPPERS.get(route_id, []),
                assigned_cart=self.ROUTE_CARTS.get(route_id),
                feed_point=self.ROUTE_FEED_POINTS.get(route_id),
            )

    def get_route_state(self, route_id: str) -> RouteState:
        """获取路线状态"""
        if route_id in self.routes:
            return self.routes[route_id].state
        return RouteState.IDLE

    def _transition(self, ctx: RouteContext, new_state: RouteState):
        """内部状态转换，自动发出回调"""
        old_state = ctx.state
        if old_state == new_state:
            return
        ctx.state = new_state
        self._notify_state_change(ctx.route_id, old_state, new_state)

    def set_route_state(self, route_id: str, state: RouteState):
        """设置路线状态（外部接口）"""
        if route_id in self.routes:
            self._transition(self.routes[route_id], state)

    def get_route_context(self, route_id: str) -> Optional[RouteContext]:
        """获取路线上下文"""
        return self.routes.get(route_id)

    def start_route(self, route_id: str, target_bin: str) -> bool:
        """启动路线"""
        if route_id not in self.routes:
            return False

        ctx = self.routes[route_id]
        if not self._acquire_resources(route_id):
            return False

        # 计算小车目标位置
        cart_id = ctx.assigned_cart
        if cart_id and '-' in target_bin:
            try:
                ctx.cart_target_position = int(target_bin.split('-')[1])
            except ValueError:
                ctx.cart_target_position = 1
        else:
            ctx.cart_target_position = 1
        ctx.cart_moving = True

        # 进入MOVING_TO_TARGET状态，等待小车移动到目标位置
        ctx.target_bin = target_bin
        self._transition(ctx, RouteState.MOVING_TO_TARGET)
        ctx.final_weights.clear()
        ctx.material_on_belt.clear()
        ctx.cleared_sensors.clear()
        ctx.feeding_start_time = 0.0
        return True

    def stop_route(self, route_id: str) -> bool:
        """停止路线（需先完成余料清空）"""
        if route_id not in self.routes:
            return False

        ctx = self.routes[route_id]
        if ctx.state == RouteState.WAITING:
            self._transition(ctx, RouteState.IDLE)
            self._release_resources(route_id)
            return True
        elif ctx.state == RouteState.FEEDING:
            self._transition(ctx, RouteState.IDLE)
            self._release_resources(route_id)
            return True
        # MOVING_TO_TARGET / CLEARING / IDLE 等：强制结束路线
        self._transition(ctx, RouteState.IDLE)
        ctx.cart_moving = False
        self._release_resources(route_id)
        return True

    def trigger_clearing(self, route_id: str) -> bool:
        """触发清空余料（料位达到阈值）"""
        if route_id not in self.routes:
            return False
        ctx = self.routes[route_id]
        if ctx.state != RouteState.FEEDING:
            return False
        ctx.previous_state = ctx.state.value
        self._transition(ctx, RouteState.CLEARING)
        # 保存FEEDING阶段结束时的称重值作为CLEARING的初始值
        # 只清空final_weights和cleared_sensors
        # 保留current_weights（FEEDING阶段的累加值）和pending_release_weights
        ctx.final_weights.clear()
        ctx.material_on_belt.clear()
        ctx.cleared_sensors.clear()
        # 如果current_weights为空，用pending_release_weights初始化
        if not ctx.current_weights and ctx.pending_release_weights:
            ctx.current_weights = ctx.pending_release_weights.copy()
        return True

    def complete_clearing(self, route_id: str):
        """完成清空，转到WAITING状态"""
        if route_id not in self.routes:
            return
        ctx = self.routes[route_id]
        if ctx.state == RouteState.CLEARING:
            self._release_resources(route_id)
            self._transition(ctx, RouteState.WAITING)
            ctx.previous_state = 'clearing'
            for hopper_id, weight in ctx.current_weights.items():
                if weight > 0:
                    ctx.pending_release_weights[hopper_id] = weight
            for hopper_id, weight in ctx.current_weights.items():
                ctx.final_weights[hopper_id] = weight

    def recover_feeding(self, route_id: str) -> bool:
        """恢复供料（从WAITING转到FEEDING）"""
        if route_id not in self.routes:
            return False
        ctx = self.routes[route_id]
        if ctx.state != RouteState.WAITING:
            return False
        ctx.previous_state = 'clearing'
        self._transition(ctx, RouteState.FEEDING)
        ctx.material_on_belt.clear()
        ctx.cleared_sensors.clear()
        ctx.feeding_start_time = 0.0
        print(f"[RECOVER_FEEDING] route={route_id} previous_state=clearing pending_release={dict(ctx.pending_release_weights)} final_weights={dict(ctx.final_weights)}")
        return True

    def update_sensor_cleared(self, route_id: str, sensor_id: str):
        """更新传感器已清空"""
        if route_id in self.routes:
            self.routes[route_id].cleared_sensors.add(sensor_id)

    def is_route_cleared(self, route_id: str) -> bool:
        """检查路线是否已清空"""
        if route_id not in self.routes:
            return True
        ctx = self.routes[route_id]
        route_sensors = self.ROUTE_PROXIMITY_SENSORS.get(route_id, [])
        return len(ctx.cleared_sensors) >= len(route_sensors)

    def update_material_on_belt(self, route_id: str, belt_id: str, weight: float):
        """更新皮带上余料量"""
        if route_id in self.routes:
            self.routes[route_id].material_on_belt[belt_id] = weight

    def update_hopper_weight(self, route_id: str, hopper_id: str, weight: float):
        """更新单个中转斗的最终称重值"""
        if route_id in self.routes:
            self.routes[route_id].final_weights[hopper_id] = weight

    def get_residual_material_total(self, route_id: str) -> float:
        """获取路线上余料总量"""
        if route_id not in self.routes:
            return 0.0
        return sum(self.routes[route_id].material_on_belt.values())

    def _acquire_resources(self, route_id: str) -> bool:
        """获取路线所需资源"""
        if route_id not in self.routes:
            return False
        ctx = self.routes[route_id]
        for hopper_id in ctx.assigned_hoppers:
            if self._resource_locks.get(hopper_id) is not None:
                return False
        # 注意：小车（Cart）不被独占锁定，允许不同路线共用同一小车
        for hopper_id in ctx.assigned_hoppers:
            self._resource_locks[hopper_id] = route_id
        return True

    def _release_resources(self, route_id: str):
        """释放路线资源"""
        if route_id not in self.routes:
            return
        ctx = self.routes[route_id]
        for hopper_id in ctx.assigned_hoppers:
            if self._resource_locks.get(hopper_id) == route_id:
                self._resource_locks[hopper_id] = None

    def is_resource_available(self, resource_id: str) -> bool:
        """检查资源是否可用"""
        return self._resource_locks.get(resource_id) is None

    def is_cart_busy(self, cart_id: str, exclude_route: str = None) -> bool:
        """检查小车是否繁忙（被其他路线占用且处于移动/补料状态）"""
        BUSY_STATES = {RouteState.MOVING_TO_TARGET, RouteState.FEEDING, RouteState.CLEARING}
        for route_id, ctx in self.routes.items():
            if route_id == exclude_route:
                continue
            if ctx.assigned_cart != cart_id:
                continue
            if ctx.state in BUSY_STATES or ctx.cart_moving:
                return True
        return False

    def get_cart_busy_route(self, cart_id: str, exclude_route: str = None) -> Optional[str]:
        """获取占用小车的路线ID"""
        BUSY_STATES = {RouteState.MOVING_TO_TARGET, RouteState.FEEDING, RouteState.CLEARING}
        for route_id, ctx in self.routes.items():
            if route_id == exclude_route:
                continue
            if ctx.assigned_cart != cart_id:
                continue
            if ctx.state in BUSY_STATES or ctx.cart_moving:
                return route_id
        return None

    def get_resource_lock(self, resource_id: str) -> Optional[str]:
        """获取资源占用者"""
        return self._resource_locks.get(resource_id)

    def get_all_route_states(self) -> Dict[str, str]:
        """获取所有路线状态"""
        return {route_id: ctx.state.value for route_id, ctx in self.routes.items()}

    def update_cart_position(self, route_id: str, new_position: int):
        """更新路线的小车位置"""
        if route_id in self.routes:
            self.routes[route_id].cart_target_position = new_position

    def check_cart_arrival(self, route_id: str, current_position: int) -> bool:
        """检查小车是否到达目标位置"""
        if route_id not in self.routes:
            return False
        ctx = self.routes[route_id]
        return ctx.cart_moving and ctx.cart_target_position == current_position

    def set_cart_arrived(self, route_id: str):
        """标记小车已到达"""
        if route_id in self.routes:
            self.routes[route_id].cart_moving = False

    def reset(self):
        """重置所有路线状态"""
        for route_id in list(self.routes.keys()):
            self._release_resources(route_id)
            ctx = self.routes[route_id]
            self._transition(ctx, RouteState.IDLE)
            ctx.target_bin = None
            ctx.final_weights.clear()
            ctx.material_on_belt.clear()
            ctx.cleared_sensors.clear()


_route_state_manager: Optional[RouteStateManager] = None


def get_route_state_manager() -> RouteStateManager:
    """获取路线状态管理器单例"""
    global _route_state_manager
    if _route_state_manager is None:
        _route_state_manager = RouteStateManager()
    return _route_state_manager


def reset_route_state_manager():
    """重置路线状态管理器"""
    global _route_state_manager
    if _route_state_manager:
        _route_state_manager.reset()
    _route_state_manager = None
