"""
状态转换引擎 — 基于传感器状态的路线阶段判定

零依赖模块，仅根据传感器输入 + 配置参数判定路线应进入的状态。

输入: 传感器状态字典 + 路线配置 + 当前状态 + 调度信号
输出: 应进入的下一状态 (RouteState)

用途: 仿真系统和真实PLC系统共用同一判定逻辑。
"""

from enum import Enum
from typing import Dict, List, Optional, Tuple, Callable


class RouteState(Enum):
    IDLE = "idle"
    MOVING_TO_TARGET = "moving_to_target"
    FEEDING = "feeding"
    CLEARING = "clearing"
    WAITING = "waiting"
    STANDBY = "standby"


# 清空策略阈值
STRATEGY_THRESHOLDS = {'sequential': 98, 'reverse': 95, 'column_switch': 88}


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

    def evaluate(self, route_id: str, current_state: RouteState,
                 level_sensors: Dict[str, float],
                 cart_sensor: Dict[str, int],
                 cart_target: int,
                 cart_moving: bool,
                 proximity_sensors: Dict[str, bool],
                 schedule_has_next: bool = False,
                 schedule_next_round_empty: bool = False,
                 current_time: float = 0.0,
                 clearing_strategy: str = 'reverse',
                 sensor_clear_timers: Dict[str, float] = None,
                 sensor_clear_timeouts: Dict[str, float] = None,
                 ) -> Tuple[RouteState, dict]:
        """
        判定下一状态。

        Returns:
            (next_state, actions) — actions包含建议操作如 'close_hoppers', 'stop_endpoint'
        """
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
            threshold = STRATEGY_THRESHOLDS.get(clearing_strategy, 95)
            if level >= threshold:
                actions['close_hoppers'] = (clearing_strategy != 'column_switch')
                if clearing_strategy == 'sequential':
                    actions['stop_endpoint'] = True
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
