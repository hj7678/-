"""
故障诊断引擎 —— 基于多传感器交叉一致性的故障检测

六类诊断规则：
  A. 接近开关诊断  B. 中转斗开关诊断  C. 中转斗称重诊断
  D. 小车传感器诊断  E. 皮带转速诊断  F. 跨传感器一致性诊断

诊断按路线状态分4个阶段：
  1. moving_to_target (小车移动)  2. feeding (正常上料)
  3. clearing (清空余料)          4. waiting (上料完成)
"""

from collections import deque
from typing import Dict, List

import logging
logger = logging.getLogger(__name__)

from tcp_diagnosis.diagnosis_types import (
    RouteState,
    SystemSnapshot,
    DiagnosisResult,
)

REPORT_COOLDOWN = 1.0  # 实时推送, 不做冷却
FAULT_CONFIRMATION_DURATION = 3.0  # 故障确认时长: 故障需持续该时间后才上报UI/下位机
CONVEYOR_FAULT_DURATION = 10.0
HOPPER_SWITCH_STUCK_OPEN_DURATION = 30
CLEARING_FAULT_DURATION = 60.0    # clearing阶段故障需持续60s才判定
STANDBY_FAULT_DURATION = 3.0     # standby阶段故障需持续3s才判定
MOVING_FAULT_DURATION = 3.0       # moving阶段无规定时间的故障需持续3s才判定
DEFAULT_FAULT_DURATION = 3.0      # 所有未指定持续时间的故障统一3s判定

# 阶段特定常量
FEEDING_UPSTREAM_LIT_TIMEOUT_S = 50.0     # feeding: 上游点亮超时判卡低（末尾传感器）
FEEDING_MIDDLE_STUCK_LOW_DURATION = 40.0  # feeding: 传感器卡低需持续时长
STUCK_HIGH_DURATION = 50.0                # 统一卡高阈值: 50s
CLEARING_PROXIMITY_MAX_LIT_S = 50.0         # clearing: 接近开关最大点亮时长

WAITING_WEIGHT_VOLATILITY_THRESHOLD = 3  # waiting: 称重波动阈值(t)

# 上料异常诊断常量
FEEDING_BLOCKAGE_DURATION = 3.0          # 上料点堵料判定时间(s)
HOPPER_BLOCKAGE_DURATION = 3.0           # 中转斗堵料判定时间(s)
CART_MOVE_GRID_TIME = 18.0               # 小车每格移动时间(s)
CART_MOVE_TOLERANCE = 0.2                # 小车移动容错比例(20%)


class DiagnosisEngine:
    """独立诊断引擎——零仿真依赖"""

    def __init__(self):
        self._proximity_history: Dict[str, deque] = {}   # sensor_id → deque of (ts, state), maxlen=120
        self._weight_history: Dict[str, deque] = {}       # hopper_id → deque of (ts, weight), maxlen=120
        self._speed_history: Dict[str, deque] = {}        # conveyor_id → deque of (ts, speed), maxlen=120
        self._report_tracker: Dict[str, float] = {}       # key → last_reported_ts
        self._fault_first_seen: Dict[str, float] = {}   # key → first_seen_ts (用于确认延迟)
        self._conveyor_fault_start: Dict[str, float] = {}  # "cid:fault_type" → first_observed_ts
        self._hopper_switch_fault_start: Dict[str, float] = {}  # "hid:fault_type" → first_observed_ts
        self._proximity_fault_start: Dict[str, float] = {}  # "sid:fault_type" → first_observed_ts
        self._route_state: Dict[str, RouteState] = {}
        self._route_state_since: Dict[str, float] = {}
        self._route_configs: Dict[str, dict] = {}  # route_id → {conveyor_ids, hopper_ids, proximity_sensor_ids}
        # 上料异常诊断追踪
        self._feeding_blockage_start: Dict[str, float] = {}  # "route_id:feed_point" → first_observed_ts
        self._hopper_blockage_start: Dict[str, float] = {}   # "route_id:hopper_id" → first_observed_ts
        self._cart_move_start: Dict[str, float] = {}         # route_id → move_start_ts
        self._cart_move_initial_pos: Dict[str, int] = {}     # route_id → move_start_position

    def diagnose(self, snapshot: SystemSnapshot) -> List[DiagnosisResult]:
        self._record_snapshot(snapshot)
        results: List[DiagnosisResult] = []
        results.extend(self._diagnose_proximity(snapshot))
        results.extend(self._diagnose_hopper_switch(snapshot))
        results.extend(self._diagnose_carts(snapshot))
        results.extend(self._diagnose_conveyors(snapshot))
        results.extend(self._diagnose_cross_sensor(snapshot))
        # 上料异常诊断
        results.extend(self._diagnose_feeding_blockage(snapshot))
        results.extend(self._diagnose_hopper_blockage(snapshot))
        results.extend(self._diagnose_cart_movement(snapshot))
        return self._dedup_and_sort(results, snapshot.timestamp)

    # ========================================================================
    # 内部：历史记录
    # ========================================================================

    def _record_snapshot(self, snapshot: SystemSnapshot):
        ts = snapshot.timestamp
        for sid, s in snapshot.proximity_sensors.items():
            if sid not in self._proximity_history:
                self._proximity_history[sid] = deque(maxlen=120)
            self._proximity_history[sid].append((ts, s.state))
        for hid, h in snapshot.hoppers.items():
            if hid not in self._weight_history:
                self._weight_history[hid] = deque(maxlen=120)
            self._weight_history[hid].append((ts, h.weight))
        for cid, c in snapshot.conveyors.items():
            if cid not in self._speed_history:
                self._speed_history[cid] = deque(maxlen=120)
            self._speed_history[cid].append((ts, c.speed))

    def _dedup_and_sort(self, results: List[DiagnosisResult], now: float) -> List[DiagnosisResult]:
        """去重排序，增加故障确认延迟: 故障需持续 CONFIRMATION_DURATION 秒后才上报"""
        active_keys = set()
        filtered = []
        for r in results:
            key = f"{r.sensor_id}:{r.fault_type}"
            active_keys.add(key)

            # 记录首次检测时间
            if key not in self._fault_first_seen:
                self._fault_first_seen[key] = now

            first_seen = self._fault_first_seen[key]

            # 故障确认延迟: 必须持续存在超过 CONFIRMATION_DURATION 才上报
            if now - first_seen < FAULT_CONFIRMATION_DURATION:
                continue

            # 冷却去重
            last = self._report_tracker.get(key, -999.0)
            if now - last < REPORT_COOLDOWN:
                continue
            self._report_tracker[key] = now
            filtered.append(r)

        # 清理已消失的故障
        for key in list(self._fault_first_seen.keys()):
            if key not in active_keys:
                self._fault_first_seen.pop(key, None)

        filtered.sort(key=lambda r: -r.confidence)
        return filtered

    def _consecutive_false_duration_ms(self, sensor_id: str, now: float) -> float:
        """计算传感器连续为 false 的时长（ms），只看最近的连续段"""
        history = self._proximity_history.get(sensor_id)
        if not history:
            return 0.0
        duration = 0.0
        prev_ts = now
        for ts, state in reversed(history):
            if state:
                break
            duration += (prev_ts - ts) * 1000
            prev_ts = ts
        return duration

    def _consecutive_true_duration_ms(self, sensor_id: str, now: float) -> float:
        """计算传感器连续为 true 的时长（ms）"""
        history = self._proximity_history.get(sensor_id)
        if not history:
            return 0.0
        duration = 0.0
        prev_ts = now
        for ts, state in reversed(history):
            if not state:
                break
            duration += (prev_ts - ts) * 1000
            prev_ts = ts
        return duration

    def _min_neighbor_true_duration_ms(self, neighbor_ids: List[str], now: float) -> float:
        """所有邻居传感器连续为 true 的最短时长（ms），用于判断邻居是否已稳定"""
        if not neighbor_ids:
            return float('inf')
        min_dur = float('inf')
        for nid in neighbor_ids:
            dur = self._consecutive_true_duration_ms(nid, now)
            if dur < min_dur:
                min_dur = dur
        return min_dur

    def _min_neighbor_false_duration_ms(self, neighbor_ids: List[str], now: float) -> float:
        """所有邻居传感器连续为 false 的最短时长（ms）"""
        if not neighbor_ids:
            return float('inf')
        min_dur = float('inf')
        for nid in neighbor_ids:
            dur = self._consecutive_false_duration_ms(nid, now)
            if dur < min_dur:
                min_dur = dur
        return min_dur

    def _true_duration_since(self, sensor_id: str, since_ts: float, now: float) -> float:
        """传感器在 since_ts 之后连续为 true 的时长（ms），不追溯 since_ts 之前"""
        history = self._proximity_history.get(sensor_id)
        if not history:
            return 0.0
        duration = 0.0
        prev_ts = now
        for ts, state in reversed(history):
            if ts < since_ts:
                if state:
                    duration += (prev_ts - since_ts) * 1000
                break
            if not state:
                break
            duration += (prev_ts - ts) * 1000
            prev_ts = ts
        return duration

    # ========================================================================
    # 辅助：从历史数据计算趋势
    # ========================================================================

    def _weight_trend(self, hopper_id: str, lookback_s: float) -> float:
        """计算最近 lookback_s 秒内称重的变化率（t/s），正=递增"""
        history = self._weight_history.get(hopper_id)
        if not history or len(history) < 2:
            return 0.0
        cutoff = history[-1][0] - lookback_s
        values = [(ts, w) for ts, w in history if ts >= cutoff]
        if len(values) < 2:
            return 0.0
        first_ts, first_w = values[0]
        last_ts, last_w = values[-1]
        dt = last_ts - first_ts
        if dt < 0.1:
            return 0.0
        return (last_w - first_w) / dt

    def _weight_volatility(self, hopper_id: str, lookback_s: float) -> float:
        """计算称重波动幅度（最近值的 max-min）"""
        history = self._weight_history.get(hopper_id)
        if not history:
            return 0.0
        cutoff = history[-1][0] - lookback_s
        values = [w for ts, w in history if ts >= cutoff]
        if len(values) < 3:
            return 0.0
        return max(values) - min(values)


    def _speed_mean(self, conveyor_id: str, lookback_s: float) -> float:
        history = self._speed_history.get(conveyor_id)
        if not history:
            return 0.0
        cutoff = history[-1][0] - lookback_s
        values = [s for ts, s in history if ts >= cutoff]
        if not values:
            return 0.0
        return sum(values) / len(values)

    # ========================================================================
    # A. 接近开关诊断 —— 按路线状态分4阶段
    # ========================================================================

    def _diagnose_proximity(self, snapshot: SystemSnapshot) -> List[DiagnosisResult]:
        results = []

        # 清理不再活跃的路线状态追踪，避免跨会话状态残留导致计时错误
        active_set = set(snapshot.active_route_ids)
        for route_id in list(self._route_state.keys()):
            if route_id not in active_set:
                # 清除故障追踪状态，防止残留的计时在下一次会话中导致误报
                cfg = self._route_configs.pop(route_id, {})
                for cid in cfg.get('conveyor_ids', []):
                    for suffix in ('stopped_in_clearing', 'speed_zero', 'speed_nonzero', 'speed_volatile', 'should_stop_in_standby', 'should_stop_in_moving', 'should_run_in_moving'):
                        self._conveyor_fault_start.pop(f"{cid}:{suffix}", None)
                for hid in cfg.get('hopper_ids', []):
                    self._hopper_switch_fault_start.pop(f"{hid}:switch_open_in_clearing", None)
                    self._hopper_switch_fault_start.pop(f"{hid}:switch_stuck_open", None)
                    pass  # 不再追踪
                    self._hopper_switch_fault_start.pop(f"{hid}:switch_open_in_standby", None)
                for sid in cfg.get('proximity_sensor_ids', []):
                    self._proximity_fault_start.pop(f"{sid}:stuck_low_mid_feeding", None)
                    self._proximity_fault_start.pop(f"{sid}:stuck_high_tail_feeding", None)
                    self._proximity_fault_start.pop(f"{sid}:stuck_high_in_standby", None)
                    self._proximity_fault_start.pop(f"{sid}:stuck_high_moving", None)
                # 清理上料异常追踪
                for key in list(self._feeding_blockage_start.keys()):
                    if key.startswith(route_id):
                        self._feeding_blockage_start.pop(key, None)
                for key in list(self._hopper_blockage_start.keys()):
                    if key.startswith(route_id):
                        self._hopper_blockage_start.pop(key, None)
                self._cart_move_start.pop(route_id, None)
                self._cart_move_initial_pos.pop(route_id, None)
                del self._route_state[route_id]
                self._route_state_since.pop(route_id, None)

        for route_id in snapshot.active_route_ids:
            route = snapshot.routes.get(route_id)
            if not route:
                continue
            # 缓存路线配置，用于路线不再活跃时清理故障追踪状态
            if route_id not in self._route_configs:
                self._route_configs[route_id] = {
                    'conveyor_ids': list(route.conveyor_ids),
                    'hopper_ids': list(route.hopper_ids),
                    'proximity_sensor_ids': list(route.proximity_sensor_ids),
                }
            prev_state = self._route_state.get(route_id)
            if prev_state != route.state:
                self._route_state_since[route_id] = snapshot.timestamp
                self._route_state[route_id] = route.state
                # 离开MOVING_TO_TARGET阶段时，清理该路线相关的moving故障追踪key
                if prev_state == RouteState.MOVING_TO_TARGET:
                    for sid in route.proximity_sensor_ids:
                        self._proximity_fault_start.pop(f"{sid}:stuck_high_moving", None)
                    for cid in route.conveyor_ids:
                        self._conveyor_fault_start.pop(f"{cid}:should_stop_in_moving", None)
                        self._conveyor_fault_start.pop(f"{cid}:should_run_in_moving", None)
                    for hid in route.hopper_ids:
                        pass  # 不再追踪移动阶段的斗开关
                # 离开CLEARING阶段时，清理该路线相关的clearing故障追踪key
                if prev_state == RouteState.CLEARING:
                    for cid in route.conveyor_ids:
                        self._conveyor_fault_start.pop(f"{cid}:stopped_in_clearing", None)
                    for hid in route.hopper_ids:
                        self._hopper_switch_fault_start.pop(f"{hid}:switch_open_in_clearing", None)
                # 离开STANDBY阶段时，清理该路线相关的standby故障追踪key
                if prev_state == RouteState.STANDBY:
                    for cid in route.conveyor_ids:
                        self._conveyor_fault_start.pop(f"{cid}:should_stop_in_standby", None)
                    for hid in route.hopper_ids:
                        self._hopper_switch_fault_start.pop(f"{hid}:switch_open_in_standby", None)
                    for sid in route.proximity_sensor_ids:
                        self._proximity_fault_start.pop(f"{sid}:stuck_high_in_standby", None)
            if route.state == RouteState.MOVING_TO_TARGET:
                results.extend(self._check_moving_stage(route, snapshot))
            elif route.state == RouteState.FEEDING:
                results.extend(self._check_feeding_stage(route, snapshot))
            elif route.state == RouteState.CLEARING:
                results.extend(self._check_clearing_stage(route, snapshot))
            elif route.state == RouteState.WAITING:
                results.extend(self._check_waiting_stage(route, snapshot))
            elif route.state == RouteState.STANDBY:
                results.extend(self._check_standby_stage(route, snapshot))
        return results

    # ------------------------------------------------------------------
    # 阶段1：小车移动
    # ------------------------------------------------------------------

    def _check_moving_stage(self, route, snapshot: SystemSnapshot) -> List[DiagnosisResult]:
        """小车移动阶段：所有接近开关为false，所有中转斗开关为false，非终点皮带运行，终点皮带停止"""
        results = []
        ts = snapshot.timestamp

        # for sid in route.proximity_sensor_ids:
        #     sensor = snapshot.proximity_sensors.get(sid)
        #     if sensor and sensor.state:
        #         key = f"{sid}:stuck_high_moving"
        #         start = self._proximity_fault_start.get(key, snapshot.timestamp)
        #         self._proximity_fault_start[key] = start
        #         if snapshot.timestamp - start >= 3.0:
        #             results.append(DiagnosisResult(
        #                 sensor_id=sid,
        #                 fault_type="stuck_high",
        #                 confidence=0.85,
        #                 description=f"接近开关{sid}故障(卡高): 小车移动阶段本应false但为true持续{snapshot.timestamp-start:.0f}s",
        #                 category="proximity",
        #             ))
        #     else:
        #         self._proximity_fault_start.pop(f"{sid}:stuck_high_moving", None)
        # 小车移动阶段: 中转斗可开可关, 不检查

        if route.conveyor_ids:
            end_cid = route.conveyor_ids[-1]
            for cid in route.conveyor_ids:
                conv = snapshot.conveyors.get(cid)
                if not conv:
                    continue
                if cid == end_cid:
                    if conv.is_running:
                        key = f"{cid}:should_stop_in_moving"
                        start = self._conveyor_fault_start.get(key, ts)
                        self._conveyor_fault_start[key] = start
                        if ts - start >= MOVING_FAULT_DURATION:
                            results.append(DiagnosisResult(
                                sensor_id=f"{cid}_state",
                                fault_type="conveyor_should_stop",
                                confidence=0.85,
                                description=f"皮带{cid}异常: 小车移动阶段终点皮带应停止但为运行(持续{ts-start:.0f}s)",
                                category="conveyor",
                            ))
                    else:
                        self._conveyor_fault_start.pop(f"{cid}:should_stop_in_moving", None)
                else:
                    if not conv.is_running:
                        key = f"{cid}:should_run_in_moving"
                        start = self._conveyor_fault_start.get(key, ts)
                        self._conveyor_fault_start[key] = start
                        if ts - start >= MOVING_FAULT_DURATION:
                            results.append(DiagnosisResult(
                                sensor_id=f"{cid}_state",
                                fault_type="conveyor_should_run",
                                confidence=0.85,
                                description=f"皮带{cid}异常: 小车移动阶段非终点皮带应运行但为停止(持续{ts-start:.0f}s)",
                                category="conveyor",
                            ))
                    else:
                        self._conveyor_fault_start.pop(f"{cid}:should_run_in_moving", None)

        return results

    # ------------------------------------------------------------------
    # 阶段2：正常上料
    # ------------------------------------------------------------------

    def _check_feeding_stage(self, route, snapshot: SystemSnapshot) -> List[DiagnosisResult]:
        """正常上料阶段：开关必须true；接近开关按上下游判断；皮带全部运行"""
        results = []
        ts = snapshot.timestamp

        for cid in route.conveyor_ids:
            conv = snapshot.conveyors.get(cid)
            if conv and not conv.is_running:
                key = f"{cid}:feeding_should_run"
                start = self._conveyor_fault_start.get(key, ts)
                self._conveyor_fault_start[key] = start
                if ts - start >= DEFAULT_FAULT_DURATION:
                    results.append(DiagnosisResult(
                        sensor_id=f"{cid}_state",
                        fault_type="conveyor_should_run",
                        confidence=0.85,
                        description=f"皮带{cid}异常: feeding阶段应运行但为停止(持续{ts-start:.0f}s)",
                        category="conveyor",
                    ))
            else:
                self._conveyor_fault_start.pop(f"{cid}:feeding_should_run", None)

        for hid in route.hopper_ids:
            hopper = snapshot.hoppers.get(hid)
            if not hopper:
                continue
            if not hopper.switch_open:
                key = f"{hid}:feeding_closed"
                start = self._hopper_switch_fault_start.get(key, ts)
                self._hopper_switch_fault_start[key] = start
                if ts - start >= DEFAULT_FAULT_DURATION:
                    results.append(DiagnosisResult(
                        sensor_id=hid,
                        fault_type="hopper_switch_stuck_closed",
                        confidence=0.80,
                        description=f"{hid}开关故障(卡关): feeding阶段开关未打开(持续{ts-start:.0f}s)",
                        category="hopper_switch",
                    ))
            else:
                self._hopper_switch_fault_start.pop(f"{hid}:feeding_closed", None)

        for sid in route.proximity_sensor_ids:
            sensor = snapshot.proximity_sensors.get(sid)
            if not sensor:
                continue

            upstream = self._get_upstream_sensors(route, sid, snapshot)
            downstream = self._get_downstream_sensors(route, sid, snapshot)
            is_last = self._is_last_sensor(route, sid)
            key = f"{sid}:stuck_low_mid_feeding"

            # 卡低：上游和/或下游都true，本传感器false
            if not sensor.state:
                up_ok = len(upstream) > 0 and all(s.state for s in upstream)
                down_ok = len(downstream) > 0 and all(s.state for s in downstream)
                # 首/尾传感器: 只看紧邻的下游/上游
                first_ok = (not upstream and len(downstream) > 0 and downstream[0].state)
                last_ok = (not downstream and len(upstream) > 0 and upstream[-1].state)
                # 中间传感器: 上游&&下游都true
                middle_ok = (up_ok and down_ok)
                if middle_ok or first_ok or last_ok:
                    was = self._proximity_fault_start.get(key, 0)
                    if was == 0:
                        self._proximity_fault_start[key] = ts
                    elif ts - was >= FEEDING_MIDDLE_STUCK_LOW_DURATION:
                        results.append(DiagnosisResult(
                            sensor_id=sid,
                            fault_type="stuck_low",
                            confidence=0.90,
                            description=f"接近开关{sid}故障(卡低): 上/下游均点亮但本传感器未点亮持续{ts-was:.0f}s",
                            category="proximity",
                        ))
                elif not is_last and not (not upstream and len(downstream) > 0):
                    self._proximity_fault_start.pop(key, None)
                elif is_last and up_ok:
                    feeding_start = self._route_state_since.get(route.route_id, ts)
                    upstream_lit_dur = min(
                        self._true_duration_since(s.sensor_id, feeding_start, ts)
                        for s in upstream
                    )
                    if upstream_lit_dur >= FEEDING_UPSTREAM_LIT_TIMEOUT_S * 1000:
                        results.append(DiagnosisResult(
                            sensor_id=sid,
                            fault_type="stuck_low",
                            confidence=0.85,
                            description=f"接近开关{sid}故障(卡低): 末尾传感器，上游点亮{upstream_lit_dur/1000:.0f}s但本传感器未点亮",
                            category="proximity",
                        ))

            # 卡高：上游和下游都false，本传感器true
            if sensor.state:
                self._proximity_fault_start.pop(key, None)
                up_off = len(upstream) > 0 and all(not s.state for s in upstream)
                down_off = len(downstream) > 0 and all(not s.state for s in downstream)
                if up_off and down_off:
                    key_high = f"{sid}:stuck_high_feeding"
                    start = self._proximity_fault_start.get(key_high, ts)
                    self._proximity_fault_start[key_high] = start
                    if ts - start >= STUCK_HIGH_DURATION:
                        results.append(DiagnosisResult(
                            sensor_id=sid,
                            fault_type="stuck_high",
                            confidence=0.90,
                            description=f"接近开关{sid} 卡高(持续{ts-start:.0f}s)",
                            category="proximity",
                        ))
                else:
                    self._proximity_fault_start.pop(f"{sid}:stuck_high_feeding", None)
                if is_last:
                    upstream_false_count = sum(1 for s in upstream if not s.state)
                    if upstream_false_count >= 2:
                        key = f"{sid}:stuck_high_tail_feeding"
                        start = self._proximity_fault_start.get(key, ts)
                        self._proximity_fault_start[key] = start
                        if ts - start >= STUCK_HIGH_DURATION:
                            results.append(DiagnosisResult(
                                sensor_id=sid,
                                fault_type="stuck_high",
                                confidence=0.85,
                                description=f"接近开关{sid} 卡高(持续{ts-start:.0f}s)",
                                category="proximity",
                            ))
                    else:
                        self._proximity_fault_start.pop(f"{sid}:stuck_high_tail_feeding", None)

        return results

    # ------------------------------------------------------------------
    # 阶段3：清空余料
    # ------------------------------------------------------------------

    def _check_clearing_stage(self, route, snapshot: SystemSnapshot) -> List[DiagnosisResult]:
        """清空余料阶段诊断（持续60s才判定故障，顺序策略终点皮带除外，换列策略中转斗除外）
        
        顺序清空共享状态（early_moved_from_clearing=True）：
        - 清空余料 + 小车移动同步进行，状态取两者并集条件
        - 中转斗开关：MOVING_TO_TARGET不检查 → 共享状态也不检查（并集：只要一方允许即OK）
        - 接近开关：MOVING_TO_TARGET不检查 → 共享状态也不检查（并集：只要一方允许即OK）
        - 皮带：两状态规则一致（非终点运行、终点停止），保持不变
        """
        results = []
        ts = snapshot.timestamp
        strategy = getattr(route, 'clearing_strategy', 'reverse')
        end_cid = route.conveyor_ids[-1] if route.conveyor_ids else None
        in_shared = (strategy == 'sequential' and
                     getattr(route, 'early_moved_from_clearing', False))

        # 皮带检查：两状态规则一致，无论是否共享状态都执行
        for cid in route.conveyor_ids:
            conv = snapshot.conveyors.get(cid)
            # 顺序策略：终点皮带被故意停止，跳过检查
            if strategy == 'sequential' and cid == end_cid:
                self._conveyor_fault_start.pop(f"{cid}:stopped_in_clearing", None)
                continue
            if conv and not conv.is_running:
                key = f"{cid}:stopped_in_clearing"
                start = self._conveyor_fault_start.get(key, ts)
                self._conveyor_fault_start[key] = start
                if ts - start >= CLEARING_FAULT_DURATION:
                    results.append(DiagnosisResult(
                        sensor_id=f"{cid}_state",
                        fault_type="conveyor_should_run",
                        confidence=0.85,
                        description=f"皮带{cid}异常: clearing阶段应运行但为停止(持续{ts-start:.0f}s)",
                        category="conveyor",
                    ))
            else:
                self._conveyor_fault_start.pop(f"{cid}:stopped_in_clearing", None)

        # 共享状态：中转斗开关取并集 → MOVING_TO_TARGET不检查，共享状态也不检查
        if in_shared:
            for hid in route.hopper_ids:
                self._hopper_switch_fault_start.pop(f"{hid}:switch_open_in_clearing", None)
        elif strategy == 'column_switch':
            # 换列策略：中转斗故意保持开启，跳过检查
            for hid in route.hopper_ids:
                self._hopper_switch_fault_start.pop(f"{hid}:switch_open_in_clearing", None)
        else:
            for hid in route.hopper_ids:
                hopper = snapshot.hoppers.get(hid)
                if not hopper:
                    continue
                if hopper.switch_open:
                    key = f"{hid}:switch_open_in_clearing"
                    start = self._hopper_switch_fault_start.get(key, ts)
                    self._hopper_switch_fault_start[key] = start
                    if ts - start >= CLEARING_FAULT_DURATION:
                        results.append(DiagnosisResult(
                            sensor_id=hid,
                            fault_type="hopper_switch_stuck_open",
                            confidence=0.85,
                            description=f"{hid}开关故障(卡开): 清空阶段开关为true持续{ts-start:.0f}s",
                            category="hopper_switch",
                        ))
                else:
                    self._hopper_switch_fault_start.pop(f"{hid}:switch_open_in_clearing", None)

        # 共享状态：接近开关取并集 → MOVING_TO_TARGET不检查，共享状态也不检查
        if in_shared:
            for sid in route.proximity_sensor_ids:
                self._proximity_fault_start.pop(f"{sid}:stuck_high_moving", None)
        else:
            for sid in route.proximity_sensor_ids:
                sensor = snapshot.proximity_sensors.get(sid)
                if sensor and sensor.state:
                    clearing_start = self._route_state_since.get(route.route_id, ts)
                    lit_dur = self._true_duration_since(sid, clearing_start, ts) / 1000.0
                    if lit_dur > CLEARING_PROXIMITY_MAX_LIT_S:
                        results.append(DiagnosisResult(
                            sensor_id=sid,
                            fault_type="stuck_high",
                            confidence=0.85,
                            description=f"接近开关{sid}故障(卡高): 清空阶段点亮{lit_dur:.1f}s超过{CLEARING_PROXIMITY_MAX_LIT_S}s",
                            category="proximity",
                        ))

        return results

    # ------------------------------------------------------------------
    # 阶段4：上料完成
    # ------------------------------------------------------------------

    def _check_waiting_stage(self, route, snapshot: SystemSnapshot) -> List[DiagnosisResult]:
        results = []
        ts = snapshot.timestamp

        if route.conveyor_ids:
            end_cid = route.conveyor_ids[-1]
            for cid in route.conveyor_ids:
                conv = snapshot.conveyors.get(cid)
                if not conv: continue
                if cid == end_cid:
                    if conv.is_running:
                        key = f"{cid}:waiting_stop"
                        if key not in self._conveyor_fault_start: self._conveyor_fault_start[key] = ts
                        if ts - self._conveyor_fault_start[key] >= DEFAULT_FAULT_DURATION:
                            results.append(DiagnosisResult(sensor_id=f"{cid}_state", fault_type="conveyor_should_stop", confidence=0.85, description=f"皮带{cid} 终点应停止但运行", category="conveyor"))
                    else: self._conveyor_fault_start.pop(f"{cid}:waiting_stop", None)
                else:
                    if not conv.is_running:
                        key = f"{cid}:waiting_run"
                        if key not in self._conveyor_fault_start: self._conveyor_fault_start[key] = ts
                        if ts - self._conveyor_fault_start[key] >= DEFAULT_FAULT_DURATION:
                            results.append(DiagnosisResult(sensor_id=f"{cid}_state", fault_type="conveyor_should_run", confidence=0.85, description=f"皮带{cid} 非终点应运行但停止", category="conveyor"))
                    else: self._conveyor_fault_start.pop(f"{cid}:waiting_run", None)

        for hid in route.hopper_ids:
            hopper = snapshot.hoppers.get(hid)
            if not hopper: continue
            if hopper.switch_open:
                key = f"{hid}:waiting_open"
                if key not in self._hopper_switch_fault_start: self._hopper_switch_fault_start[key] = ts
                if ts - self._hopper_switch_fault_start[key] >= DEFAULT_FAULT_DURATION:
                    results.append(DiagnosisResult(sensor_id=hid, fault_type="hopper_switch_stuck_open", confidence=0.85, description=f"{hid} 卡开", category="hopper_switch"))
            else: self._hopper_switch_fault_start.pop(f"{hid}:waiting_open", None)
            vol = self._weight_volatility(hid, 3.0)
            if vol > WAITING_WEIGHT_VOLATILITY_THRESHOLD:
                results.append(DiagnosisResult(sensor_id=hid, fault_type="weight_volatile", confidence=0.75, description=f"{hid} 称重波动{vol:.3f}t", category="hopper_weight"))

        return results

    # 阶段5：节能待机
    # ------------------------------------------------------------------

    def _check_standby_stage(self, route, snapshot: SystemSnapshot) -> List[DiagnosisResult]:
        """节能待机阶段：全部皮带停止，中转斗关闭，接近开关全false（持续3s以上才判定）"""
        results = []
        ts = snapshot.timestamp

        for cid in route.conveyor_ids:
            conv = snapshot.conveyors.get(cid)
            if conv and conv.is_running:
                key = f"{cid}:should_stop_in_standby"
                start = self._conveyor_fault_start.get(key, ts)
                self._conveyor_fault_start[key] = start
                if ts - start >= STANDBY_FAULT_DURATION:
                    results.append(DiagnosisResult(
                        sensor_id=f"{cid}_state",
                        fault_type="conveyor_should_stop",
                        confidence=0.85,
                        description=f"皮带{cid}异常: 待机阶段应停止但为运行(持续{ts-start:.0f}s)",
                        category="conveyor",
                    ))
            else:
                self._conveyor_fault_start.pop(f"{cid}:should_stop_in_standby", None)

        for hid in route.hopper_ids:
            hopper = snapshot.hoppers.get(hid)
            if hopper and hopper.switch_open:
                key = f"{hid}:switch_open_in_standby"
                start = self._hopper_switch_fault_start.get(key, ts)
                self._hopper_switch_fault_start[key] = start
                if ts - start >= STANDBY_FAULT_DURATION:
                    results.append(DiagnosisResult(
                        sensor_id=hid,
                        fault_type="hopper_switch_stuck_open",
                        confidence=0.85,
                        description=f"{hid}开关故障(卡开): 待机阶段应为false(持续{ts-start:.0f}s)",
                        category="hopper_switch",
                    ))
            else:
                self._hopper_switch_fault_start.pop(f"{hid}:switch_open_in_standby", None)

        for sid in route.proximity_sensor_ids:
            sensor = snapshot.proximity_sensors.get(sid)
            if sensor and sensor.state:
                key = f"{sid}:stuck_high_in_standby"
                start = self._proximity_fault_start.get(key, ts)
                self._proximity_fault_start[key] = start
                if ts - start >= STUCK_HIGH_DURATION:
                    results.append(DiagnosisResult(
                        sensor_id=sid,
                        fault_type="stuck_high",
                        confidence=0.85,
                        description=f"接近开关{sid} 卡高(持续{ts-start:.0f}s)",
                        category="proximity",
                    ))
            else:
                self._proximity_fault_start.pop(f"{sid}:stuck_high_in_standby", None)

        return results

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _get_upstream_sensors(self, route, sensor_id: str, snapshot: SystemSnapshot) -> List:
        """获取路线上当前传感器之前的所有传感器对象"""
        try:
            idx = route.proximity_sensor_ids.index(sensor_id)
        except ValueError:
            return []
        upstream = []
        for prev_id in route.proximity_sensor_ids[:idx]:
            s = snapshot.proximity_sensors.get(prev_id)
            if s:
                upstream.append(s)
        return upstream

    def _get_downstream_sensors(self, route, sensor_id: str, snapshot: SystemSnapshot) -> List:
        """获取路线上当前传感器之后的所有传感器对象"""
        try:
            idx = route.proximity_sensor_ids.index(sensor_id)
        except ValueError:
            return []
        downstream = []
        for next_id in route.proximity_sensor_ids[idx + 1:]:
            s = snapshot.proximity_sensors.get(next_id)
            if s:
                downstream.append(s)
        return downstream

    def _is_last_sensor(self, route, sensor_id: str) -> bool:
        try:
            return route.proximity_sensor_ids.index(sensor_id) == len(route.proximity_sensor_ids) - 1
        except ValueError:
            return False


    # ========================================================================
    # B. 中转斗开关诊断
    # ========================================================================

    def _diagnose_hopper_switch(self, snapshot: SystemSnapshot) -> List[DiagnosisResult]:
        results = []
        ts = snapshot.timestamp
        for hopper_id, hopper in snapshot.hoppers.items():
            # 找该中转斗所属的路线和状态
            route_state = self._hopper_route_state(hopper_id, snapshot)

            # 规则1：开关开但称重持续增加 + 下游传感器不触发 → 卡关
            if hopper.switch_open:
                trend = self._weight_trend(hopper_id, 3.0)
                if trend > 0.5:  # 持续增加 > 0.05 t/s
                    route = self._hopper_route(hopper_id, snapshot)
                    downstream_active = self._check_downstream_sensors(route, hopper_id, snapshot)
                    if not downstream_active:
                        results.append(DiagnosisResult(
                            sensor_id=hopper_id,
                            fault_type="hopper_switch_stuck_closed",
                            confidence=0.85,
                            description=f"{hopper_id}开关故障(卡关): 开关显示开但称重递增({trend:.2f}t/s)且下游无物料",
                            category="hopper_switch",
                        ))

            # 规则2：开关关 + 输入皮带运行 + 下游有物料 + 称重≈0 → 卡开，需持续3秒以上
            if not hopper.switch_open:
                key_stuck_open = f"{hopper_id}:switch_stuck_open"
                is_stuck_open = (hopper.weight < 0.1
                                 and self._input_conveyors_running(hopper, snapshot))
                if is_stuck_open:
                    route = self._hopper_route(hopper_id, snapshot)
                    if route and self._check_downstream_sensors(route, hopper_id, snapshot):
                        start = self._hopper_switch_fault_start.get(key_stuck_open, ts)
                        self._hopper_switch_fault_start[key_stuck_open] = start
                        if ts - start >= HOPPER_SWITCH_STUCK_OPEN_DURATION:
                            results.append(DiagnosisResult(
                                sensor_id=hopper_id,
                                fault_type="hopper_switch_stuck_open",
                                confidence=0.85,
                                description=f"{hopper_id}开关故障(卡开): 开关显示关但下游有物料且称重≈0，持续{ts-start:.0f}s",
                                category="hopper_switch",
                            ))
                    else:
                        self._hopper_switch_fault_start.pop(key_stuck_open, None)
                else:
                    self._hopper_switch_fault_start.pop(key_stuck_open, None)

            # 规则3：FEEDING 时开关为关
            if route_state == RouteState.FEEDING and not hopper.switch_open:
                results.append(DiagnosisResult(
                    sensor_id=hopper_id,
                    fault_type="hopper_switch_unexpected",
                    confidence=0.50,
                    description=f"{hopper_id}开关异常: FEEDING状态下开关为关",
                    category="hopper_switch",
                ))

        return results

    def _hopper_route_state(self, hopper_id: str, snapshot: SystemSnapshot):
        for route_id in snapshot.active_route_ids:
            route = snapshot.routes.get(route_id)
            if route and hopper_id in route.hopper_ids:
                return route.state
        return None

    def _hopper_route(self, hopper_id: str, snapshot: SystemSnapshot):
        for route_id in snapshot.active_route_ids:
            route = snapshot.routes.get(route_id)
            if route and hopper_id in route.hopper_ids:
                return route
        return None

    def _input_conveyors_running(self, hopper, snapshot: SystemSnapshot) -> bool:
        for cid in hopper.input_conveyor_ids:
            conv = snapshot.conveyors.get(cid)
            if conv and conv.is_running:
                return True
        return False

    def _check_downstream_sensors(self, route, hopper_id: str, snapshot: SystemSnapshot) -> bool:
        """检查中转斗下游的接近开关是否有触发"""
        if not route:
            return False
        try:
            idx = route.hopper_ids.index(hopper_id)
        except ValueError:
            return False
        downstream_sids = route.proximity_sensor_ids[idx + 1:]
        for sid in downstream_sids:
            sensor = snapshot.proximity_sensors.get(sid)
            if sensor and sensor.state:
                return True
        return False

    # ========================================================================
    # D. 小车传感器诊断
    # ========================================================================

    def _diagnose_carts(self, snapshot: SystemSnapshot) -> List[DiagnosisResult]:
        results = []
        for cart_id, cart in snapshot.carts.items():
            # 规则1：左右极限互斥
            if cart.left_limit and cart.right_limit:
                results.append(DiagnosisResult(
                    sensor_id=f"{cart_id}_limit",
                    fault_type="limit_mutual_exclusion",
                    confidence=0.95,
                    description=f"{cart_id}极限传感器故障: 左右极限同时为true",
                    category="cart",
                ))

            # 规则2：左右分料互斥
            if cart.left_divert and cart.right_divert:
                results.append(DiagnosisResult(
                    sensor_id=f"{cart_id}_divert",
                    fault_type="divert_mutual_exclusion",
                    confidence=0.95,
                    description=f"{cart_id}分料传感器故障: 左右分料同时为true",
                    category="cart",
                ))

            # 规则3: 分料互斥检查(必须一true一false, 不能同时true)
            if cart.left_divert and cart.right_divert:
                results.append(DiagnosisResult(
                    sensor_id=f"{cart_id}_divert",
                    fault_type="divert_mutual_exclusion",
                    confidence=0.95,
                    description=f"{cart_id}分料异常: 左右分料同时为true",
                    category="cart",
                ))

        return results

    # ========================================================================
    # E. 皮带转速诊断
    # ========================================================================

    def _diagnose_conveyors(self, snapshot: SystemSnapshot) -> List[DiagnosisResult]:
        results = []
        ts = snapshot.timestamp
        active_states = (RouteState.MOVING_TO_TARGET, RouteState.FEEDING,
                         RouteState.CLEARING, RouteState.WAITING)
        belt_routes = {}
        belt_endpoints = {}
        for rid, route in snapshot.routes.items():
            convs = route.conveyor_ids
            if not convs: continue
            for cid in convs:
                belt_routes.setdefault(cid, set()).add(rid)
            belt_endpoints.setdefault(convs[-1], set()).add(rid)
        for cid, conv in snapshot.conveyors.items():
            using = belt_routes.get(cid, set())
            any_active = False
            any_fc = False
            for rid in using:
                r = snapshot.routes.get(rid)
                if r and r.state in active_states:
                    any_active = True
                    if r.state in (RouteState.FEEDING, RouteState.CLEARING):
                        any_fc = True
            is_endpoint = cid in belt_endpoints and any(
                snapshot.routes.get(rid) and snapshot.routes[rid].state in active_states
                for rid in belt_endpoints.get(cid, set()))
            # 小车移动: 终点皮带故意停止, 不检查
            is_endpoint_moving = is_endpoint and any(
                snapshot.routes.get(rid) and snapshot.routes[rid].state == RouteState.MOVING_TO_TARGET
                for rid in belt_endpoints.get(cid, set()))
            # 顺序策略终点: CLEARING期间终点皮带故意停止, 跳过检查
            sequential_endpoint = False
            if is_endpoint:
                strategies = getattr(snapshot, 'clearing_strategies', {})
                for rid in belt_endpoints.get(cid, set()):
                    r = snapshot.routes.get(rid)
                    if r and r.state == RouteState.CLEARING and strategies.get(rid) == 'sequential':
                        sequential_endpoint = True
                        logger.info(f"顺序终点跳过 {cid} route={rid} strat={strategies.get(rid)}")
                        break
            if any_active and not is_endpoint:
                if not conv.is_running:
                    key = f"{cid}:should_run"
                    if key not in self._conveyor_fault_start: self._conveyor_fault_start[key] = ts
                    if ts - self._conveyor_fault_start[key] >= DEFAULT_FAULT_DURATION:
                        results.append(DiagnosisResult(sensor_id=f"{cid}_state",
                            fault_type="conveyor_should_run", confidence=0.85,
                            description=f"皮带{cid} 应运行但停止", category="conveyor"))
                else: self._conveyor_fault_start.pop(f"{cid}:should_run", None)
            elif any_active and is_endpoint:
                if is_endpoint_moving or sequential_endpoint:
                    # 顺序策略: 终点皮带清空期被故意停止, 不检查
                    self._conveyor_fault_start.pop(f"{cid}:endpoint_run", None)
                    self._conveyor_fault_start.pop(f"{cid}:endpoint_stop", None)
                elif any_fc:
                    if not conv.is_running:
                        key = f"{cid}:endpoint_run"
                        if key not in self._conveyor_fault_start: self._conveyor_fault_start[key] = ts
                        if ts - self._conveyor_fault_start[key] >= DEFAULT_FAULT_DURATION:
                            results.append(DiagnosisResult(sensor_id=f"{cid}_state",
                                fault_type="conveyor_should_run", confidence=0.85,
                                description=f"皮带{cid} 终点应运行但停止", category="conveyor"))
                    else: self._conveyor_fault_start.pop(f"{cid}:endpoint_run", None)
                else:
                    if conv.is_running:
                        key = f"{cid}:endpoint_stop"
                        if key not in self._conveyor_fault_start: self._conveyor_fault_start[key] = ts
                        if ts - self._conveyor_fault_start[key] >= DEFAULT_FAULT_DURATION:
                            results.append(DiagnosisResult(sensor_id=f"{cid}_state",
                                fault_type="conveyor_should_stop", confidence=0.85,
                                description=f"皮带{cid} 终点应停止但运行", category="conveyor"))
                    else: self._conveyor_fault_start.pop(f"{cid}:endpoint_stop", None)
            else:
                if conv.is_running:
                    key = f"{cid}:idle_stop"
                    if key not in self._conveyor_fault_start: self._conveyor_fault_start[key] = ts
                    if ts - self._conveyor_fault_start[key] >= DEFAULT_FAULT_DURATION:
                        results.append(DiagnosisResult(sensor_id=f"{cid}_state",
                            fault_type="conveyor_should_stop", confidence=0.85,
                            description=f"皮带{cid} 应停止但运行", category="conveyor"))
                else: self._conveyor_fault_start.pop(f"{cid}:idle_stop", None)
        return results

    # ========================================================================
    # F. 跨传感器一致性诊断
    # ========================================================================

    def _diagnose_cross_sensor(self, snapshot: SystemSnapshot) -> List[DiagnosisResult]:
        results = []
        ts = snapshot.timestamp

        for route_id in snapshot.active_route_ids:
            route = snapshot.routes.get(route_id)
            if not route or route.state != RouteState.FEEDING:
                continue

            # 规则1：FEEDING路线所有传感器false + 皮带运行 → 异常
            if route.state != RouteState.FEEDING:
                continue
            all_false = True
            for sid in route.proximity_sensor_ids:
                sensor = snapshot.proximity_sensors.get(sid)
                if sensor and sensor.state:
                    all_false = False
                    break
            if all_false and route.proximity_sensor_ids:
                running = any(
                    snapshot.conveyors.get(cid) and snapshot.conveyors[cid].is_running
                    for cid in route.conveyor_ids
                )
                if running:
                    key = f"{route_id}:all_sensors_false"
                    if key not in self._conveyor_fault_start:
                        self._conveyor_fault_start[key] = ts
                    if ts - self._conveyor_fault_start[key] >= DEFAULT_FAULT_DURATION:
                        results.append(DiagnosisResult(
                            sensor_id=route_id,
                            fault_type="route_all_sensors_false",
                            confidence=0.55,
                            description=f"{route_id}异常: FEEDING但所有传感器为false(持续{ts-self._conveyor_fault_start[key]:.0f}s)",
                            category="cross_sensor",
                            related_sensors=list(route.proximity_sensor_ids),
                        ))
                else:
                    self._conveyor_fault_start.pop(f"{route_id}:all_sensors_false", None)

            # 规则2：开关开 + 称重持续增加
            for hopper_id in route.hopper_ids:
                hopper = snapshot.hoppers.get(hopper_id)
                if not hopper:
                    continue
                if hopper.switch_open:
                    trend = self._weight_trend(hopper_id, 3.0)
                    if trend > 0.5:
                        results.append(DiagnosisResult(
                            sensor_id=hopper_id,
                            fault_type="switch_weight_conflict",
                            confidence=0.75,
                            description=f"{hopper_id}开关-称重矛盾: 开关显示开但称重持续增加({trend:.2f}t/s)",
                            category="cross_sensor",
                        ))

        return results

    # ========================================================================
    # G. 上料点出料口堵料诊断
    # ========================================================================

    def _diagnose_feeding_blockage(self, snapshot: SystemSnapshot) -> List[DiagnosisResult]:
        """上料点出料口堵料：FEEDING状态下，路线起始皮带上的接近开关不点亮超过3S"""
        results = []
        ts = snapshot.timestamp

        for route_id in snapshot.active_route_ids:
            route = snapshot.routes.get(route_id)
            if not route or route.state != RouteState.FEEDING:
                continue
            if not route.proximity_sensor_ids:
                continue

            # 起始传感器 = 路线上第一个接近开关（对应起始皮带）
            first_sid = route.proximity_sensor_ids[0]
            sensor = snapshot.proximity_sensors.get(first_sid)
            if not sensor:
                continue

            feed_point = route.feed_point or route_id
            key = f"{route_id}:{feed_point}"

            if sensor.state:
                # 传感器点亮，堵料解除
                self._feeding_blockage_start.pop(key, None)
                continue

            # 传感器未点亮，开始计时
            start = self._feeding_blockage_start.get(key, ts)
            self._feeding_blockage_start[key] = start
            if ts - start >= FEEDING_BLOCKAGE_DURATION:
                results.append(DiagnosisResult(
                    sensor_id=first_sid,
                    fault_type="feeding_outlet_blocked",
                    confidence=0.88,
                    description=f"上料点{feed_point}出料口堵料: 路线{route_id}处于FEEDING但起始皮带{route.conveyor_ids[0] if route.conveyor_ids else '?'}传感器{first_sid}未点亮(持续{ts-start:.0f}s)",
                    category="feeding_anomaly",
                    related_sensors=[first_sid],
                ))

        # 清理不在活跃路线中的追踪记录
        active_set = set(snapshot.active_route_ids)
        for key in list(self._feeding_blockage_start.keys()):
            rid = key.split(':')[0]
            if rid not in active_set:
                self._feeding_blockage_start.pop(key, None)

        return results

    # ========================================================================
    # H. 中转斗堵料诊断
    # ========================================================================

    def _diagnose_hopper_blockage(self, snapshot: SystemSnapshot) -> List[DiagnosisResult]:
        """中转斗堵料：FEEDING状态下，中转斗开关为开但称重值持续增大超过3S"""
        results = []
        ts = snapshot.timestamp

        for route_id in snapshot.active_route_ids:
            route = snapshot.routes.get(route_id)
            if not route or route.state != RouteState.FEEDING:
                continue

            for hid in route.hopper_ids:
                hopper = snapshot.hoppers.get(hid)
                if not hopper:
                    continue

                key = f"{route_id}:{hid}"

                # 只有开关为开时才检查堵料
                if not hopper.switch_open:
                    self._hopper_blockage_start.pop(key, None)
                    continue

                trend = self._weight_trend(hid, 3.0)
                if trend <= 0:
                    # 称重不再增加，堵料解除
                    self._hopper_blockage_start.pop(key, None)
                    continue

                # 开关开 + 称重持续增加 → 开始计时
                start = self._hopper_blockage_start.get(key, ts)
                self._hopper_blockage_start[key] = start
                if ts - start >= HOPPER_BLOCKAGE_DURATION:
                    results.append(DiagnosisResult(
                        sensor_id=hid,
                        fault_type="hopper_blocked",
                        confidence=0.85,
                        description=f"{hid}堵料: 路线{route_id}处于FEEDING但开关开且称重持续增加({trend:.2f}t/s)超过{ts-start:.0f}s",
                        category="feeding_anomaly",
                    ))

        # 清理不在活跃路线中的追踪记录
        active_set = set(snapshot.active_route_ids)
        for key in list(self._hopper_blockage_start.keys()):
            rid = key.split(':')[0]
            if rid not in active_set:
                self._hopper_blockage_start.pop(key, None)

        return results

    # ========================================================================
    # I. 小车移动故障诊断
    # ========================================================================

    def _diagnose_cart_movement(self, snapshot: SystemSnapshot) -> List[DiagnosisResult]:
        """小车移动故障：MOVING_TO_TARGET阶段，小车在规定时间内未到达目标位置"""
        results = []
        ts = snapshot.timestamp

        # 路线→小车映射
        cart_map = {
            'route1': 'Cart1', 'route2': 'Cart1', 'route3': 'Cart1',
            'route4': 'Cart3', 'route5': 'Cart4',
            'route6': 'Cart2', 'route7': 'Cart3', 'route8': 'Cart2',
        }

        for route_id in snapshot.active_route_ids:
            route = snapshot.routes.get(route_id)
            if not route:
                continue

            if route.state == RouteState.MOVING_TO_TARGET:
                # 记录小车移动开始时刻和初始位置
                if route_id not in self._cart_move_start:
                    self._cart_move_start[route_id] = ts
                    cart_id = cart_map.get(route_id)
                    if cart_id:
                        cart = snapshot.carts.get(cart_id)
                        self._cart_move_initial_pos[route_id] = cart.position if cart else 0
                    else:
                        self._cart_move_initial_pos[route_id] = 0

                cart_id = cart_map.get(route_id)
                if not cart_id:
                    continue
                cart = snapshot.carts.get(cart_id)
                if not cart:
                    continue

                target_pos = route.cart_target_position
                if target_pos <= 0:
                    continue

                # 已经到达目标位置，解除故障追踪
                if cart.position == target_pos:
                    self._cart_move_start.pop(route_id, None)
                    self._cart_move_initial_pos.pop(route_id, None)
                    continue

                # 计算预期到达时间
                initial_pos = self._cart_move_initial_pos.get(route_id, cart.position)
                grids = abs(target_pos - initial_pos)
                if grids == 0:
                    grids = 1  # 至少移动1格
                expected_time = grids * CART_MOVE_GRID_TIME * (1 + CART_MOVE_TOLERANCE)

                move_start = self._cart_move_start[route_id]
                elapsed = ts - move_start

                if elapsed >= expected_time:
                    results.append(DiagnosisResult(
                        sensor_id=route_id,
                        fault_type="cart_move_failure",
                        confidence=0.90,
                        description=f"小车移动故障: 路线{route_id}目标格位{target_pos}，移动{grids}格，预期{expected_time:.1f}s内到达，已耗时{elapsed:.1f}s仍未到达(当前位置{cart.position})",
                        category="cart_movement",
                    ))
            else:
                # 不在MOVING_TO_TARGET阶段，清理追踪
                self._cart_move_start.pop(route_id, None)
                self._cart_move_initial_pos.pop(route_id, None)

        # 清理不在活跃路线中的追踪记录
        active_set = set(snapshot.active_route_ids)
        for rid in list(self._cart_move_start.keys()):
            if rid not in active_set:
                self._cart_move_start.pop(rid, None)
                self._cart_move_initial_pos.pop(rid, None)

        return results

    # ========================================================================
    # 公共：清空历史
    # ========================================================================

    def clear_history(self):
        self._proximity_history.clear()
        self._weight_history.clear()
        self._speed_history.clear()
        self._report_tracker.clear()
        self._fault_first_seen.clear()
        self._conveyor_fault_start.clear()
        self._hopper_switch_fault_start.clear()
        self._proximity_fault_start.clear()
        self._route_state.clear()
        self._route_state_since.clear()
        self._route_configs.clear()
        self._feeding_blockage_start.clear()
        self._hopper_blockage_start.clear()
        self._cart_move_start.clear()
        self._cart_move_initial_pos.clear()
