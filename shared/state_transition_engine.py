"""
状态转换引擎 — 基于传感器状态的路线阶段判定

零依赖模块，仅根据传感器输入 + 配置参数判定路线应进入的状态。

输入: 传感器状态字典 + 路线配置 + 当前状态 + 调度信号
输出: 应进入的下一状态 (RouteState)

用途: 仿真系统和真实PLC系统共用同一判定逻辑。
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple, Callable

# RouteState 从 route_state_manager 导入（懒加载避免循环引用）
# 模块顶层不直接导入，在 _get_route_state 中延迟导入


class StateTransitionEngine:
    """基于传感器状态的路线阶段判定引擎

    用法:
        engine = StateTransitionEngine()
        engine.configure_route('route1', belts=['E1','E4','E8','E10','D7'],
                               hoppers=['hopper1','hopper3','hopper4'],
                               cart='Cart1', endpoint='D7')
        next_state = engine.evaluate(
            route_id='route1',
            current_state=RouteState.FEEDING,
            level_sensors={'P1-5': 96.0},
            cart_sensor={'Cart1': 5},
            cart_target=5,
            cart_moving=False,
            proximity_sensors={'S-E1': False, 'S-E4': False, ...},
            schedule_has_next=False,
            schedule_next_round_empty=False,
            current_time=120.5,
        )
    """

    def __init__(self):
        self._routes: Dict[str, dict] = {}
        self._on_schedule_request: Optional[Callable] = None  # 调度请求回调

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------

    def configure_route(self, route_id: str, *, belts: List[str],
                        hoppers: List[str], cart: str, endpoint: str):
        """配置路线参数"""
        self._routes[route_id] = {
            'belts': belts, 'hoppers': hoppers,
            'cart': cart, 'endpoint': endpoint,
        }

    def set_schedule_callback(self, callback: Callable):
        """设置调度请求回调（解耦：引擎不直接调用调度服务）"""
        self._on_schedule_request = callback

    # ------------------------------------------------------------------
    # 主判定
    # ------------------------------------------------------------------

    def evaluate(self, route_id: str, current_state,  # current_state: RouteState
                 level_sensors: Dict[str, float],
                 cart_sensor: Dict[str, int],
                 cart_target: int,
                 cart_moving: bool,
                 cart: str = '',
                 proximity_sensors: Dict[str, bool] = None,
                 schedule_has_next: bool = False,
                 schedule_next_round_empty: bool = False,
                 current_time: float = 0.0,
                 clearing_strategy: str = 'reverse',
                 sensor_clear_timers: Dict[str, float] = None,
                 sensor_clear_timeouts: Dict[str, float] = None,
                 ) -> tuple:  # -> Tuple[RouteState, dict]
        """
        判定下一状态。

        Returns:
            (next_state, actions) — actions包含建议操作如 'close_hoppers', 'stop_endpoint'
        """
        from shared.route_state_manager import RouteState  # 懒加载避免循环引用
        actions = {}
        route = self._routes.get(route_id)
        if not route:
            return current_state, actions

        # === IDLE → MOVING_TO_TARGET ===
        if current_state == RouteState.IDLE:
            # 外部触发（调度指令/手动启动）
            # 引擎不主动从IDLE切换，由外部调用者决定
            return current_state, actions

        # === MOVING_TO_TARGET → FEEDING ===
        if current_state == RouteState.MOVING_TO_TARGET:
            cart_pos = cart_sensor.get(route['cart'], 1)
            if not cart_moving and cart_pos == cart_target:
                return RouteState.FEEDING, {'start_endpoint': True, 'open_hoppers': True}
            return current_state, actions

        # === FEEDING → CLEARING ===
        if current_state == RouteState.FEEDING:
            level = level_sensors.get('__target__', 0)
            if '__target__' not in level_sensors:
                return current_state, actions
            threshold = getattr(self, '_override_threshold', None)
            if threshold is None:
                threshold = {'sequential': 98, 'reverse': 95, 'column_switch': 88}.get(clearing_strategy, 95)
            if cart == 'D9': threshold = 94  # D9 Cart3 backward compat
            if level >= threshold:
                actions['close_hoppers'] = (clearing_strategy != 'column_switch')
                if clearing_strategy == 'sequential':
                    # cart 已在目标位 (最后一仓/无下一仓) → 回退到反序清空
                    if cart and cart_sensor and not cart_moving and cart_sensor.get(cart, 1) == cart_target:
                        return RouteState.CLEARING, actions
                    actions['stop_endpoint'] = True
                    return RouteState.MOVING_TO_TARGET, actions
                return RouteState.CLEARING, actions
            return current_state, actions

        # === CLEARING → WAITING ===
        if current_state == RouteState.CLEARING:
            if sensor_clear_timers and sensor_clear_timeouts:
                all_done = True
                for sid, timeout in sensor_clear_timeouts.items():
                    went_false_at = sensor_clear_timers.get(sid, 0)
                    if went_false_at == 0:
                        all_done = False
                        break
                    elapsed = current_time - went_false_at
                    if elapsed < timeout:
                        all_done = False
                        break
                if all_done:
                    actions['stop_endpoint'] = True
                    actions['close_hoppers'] = True
                    return RouteState.WAITING, actions
            return current_state, actions

        # === WAITING → STANDBY or MOVING_TO_TARGET ===
        if current_state == RouteState.WAITING:
            if schedule_has_next:
                return RouteState.MOVING_TO_TARGET, {'set_cart_target': True}
            if schedule_next_round_empty:
                return RouteState.STANDBY, {'stop_all_belts': True, 'close_hoppers': True}
            # 等待调度结果中
            return current_state, actions

        # === STANDBY → MOVING_TO_TARGET ===
        if current_state == RouteState.STANDBY:
            if schedule_has_next:
                return RouteState.MOVING_TO_TARGET, {'set_cart_target': True, 'start_belts': True}
            return current_state, actions

        return current_state, actions

    # ------------------------------------------------------------------
    # 调度触发判定
    # ------------------------------------------------------------------

    def check_schedule_trigger(self, belt_id: str,
                                bin_stocks: Dict[str, float],
                                has_executing_route: bool,
                                has_cached_sequence: bool,
                                current_state=None,  # RouteState
                                level_sensor: float = 0.0,
                                is_last_in_sequence: bool = False,
                                last_request_time: float = 0.0,
                                current_time: float = 0.0,
                                cooldown: float = 120.0) -> Tuple[bool, str]:
        """判定是否需要触发调度请求"""
        from shared.route_state_manager import RouteState  # 懒加载避免循环引用
        for bin_id, stock in bin_stocks.items():
            if stock < 11.0:
                return True, f"emergency:{bin_id}={stock:.1f}t"
        if not has_executing_route and not has_cached_sequence:
            if current_time - last_request_time >= cooldown:
                idle_threshold = 399.0 if belt_id == 'D6' else 70.0  # D6: 95%, 其他: 70t
                for bin_id, stock in bin_stocks.items():
                    if stock < idle_threshold:
                        return True, f"idle:{bin_id}={stock:.1f}t"
        if (current_state == RouteState.FEEDING and
                is_last_in_sequence and level_sensor >= 80.0):
            if current_time - last_request_time >= cooldown:
                return True, "pre_emptive:level≥80%"
        return False, ""
