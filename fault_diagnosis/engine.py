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

from fault_diagnosis.types import (
    RouteState,
    SystemSnapshot,
    DiagnosisResult,
)

REPORT_COOLDOWN = 30.0
CONVEYOR_FAULT_DURATION = 10.0
HOPPER_SWITCH_STUCK_OPEN_DURATION = 3.0

# 阶段特定常量
FEEDING_UPSTREAM_LIT_TIMEOUT_S = 30.0     # feeding: 上游点亮超时判卡低（末尾传感器）
FEEDING_MIDDLE_STUCK_LOW_DURATION = 30.0  # feeding: 中间传感器卡低需持续时长
CLEARING_PROXIMITY_MAX_LIT_S = 50.0         # clearing: 接近开关最大点亮时长

WAITING_WEIGHT_VOLATILITY_THRESHOLD = 3  # waiting: 称重波动阈值(t)


class DiagnosisEngine:
    """独立诊断引擎——零仿真依赖"""

    def __init__(self):
        self._proximity_history: Dict[str, deque] = {}   # sensor_id → deque of (ts, state), maxlen=120
        self._weight_history: Dict[str, deque] = {}       # hopper_id → deque of (ts, weight), maxlen=120
        self._speed_history: Dict[str, deque] = {}        # conveyor_id → deque of (ts, speed), maxlen=120
        self._report_tracker: Dict[str, float] = {}       # key → last_reported_ts
        self._conveyor_fault_start: Dict[str, float] = {}  # "cid:fault_type" → first_observed_ts
        self._hopper_switch_fault_start: Dict[str, float] = {}  # "hid:fault_type" → first_observed_ts
        self._proximity_fault_start: Dict[str, float] = {}  # "sid:fault_type" → first_observed_ts
        self._route_state: Dict[str, RouteState] = {}
        self._route_state_since: Dict[str, float] = {}

    def diagnose(self, snapshot: SystemSnapshot) -> List[DiagnosisResult]:
        self._record_snapshot(snapshot)
        results: List[DiagnosisResult] = []
        results.extend(self._diagnose_proximity(snapshot))
        results.extend(self._diagnose_hopper_switch(snapshot))
        results.extend(self._diagnose_carts(snapshot))
        results.extend(self._diagnose_conveyors(snapshot))
        results.extend(self._diagnose_cross_sensor(snapshot))
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
        filtered = []
        for r in results:
            key = f"{r.sensor_id}:{r.fault_type}"
            last = self._report_tracker.get(key, -999.0)
            if now - last < REPORT_COOLDOWN:
                continue
            self._report_tracker[key] = now
            filtered.append(r)
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
        for route_id in snapshot.active_route_ids:
            route = snapshot.routes.get(route_id)
            if not route:
                continue
            prev_state = self._route_state.get(route_id)
            if prev_state != route.state:
                self._route_state_since[route_id] = snapshot.timestamp
                self._route_state[route_id] = route.state
            if route.state == RouteState.MOVING_TO_TARGET:
                results.extend(self._check_moving_stage(route, snapshot))
            elif route.state == RouteState.FEEDING:
                results.extend(self._check_feeding_stage(route, snapshot))
            elif route.state == RouteState.CLEARING:
                results.extend(self._check_clearing_stage(route, snapshot))
            elif route.state == RouteState.WAITING:
                results.extend(self._check_waiting_stage(route, snapshot))
        return results

    # ------------------------------------------------------------------
    # 阶段1：小车移动
    # ------------------------------------------------------------------

    def _check_moving_stage(self, route, snapshot: SystemSnapshot) -> List[DiagnosisResult]:
        """小车移动阶段：所有接近开关为false，所有中转斗开关为false，非终点皮带运行，终点皮带停止"""
        results = []

        for sid in route.proximity_sensor_ids:
            sensor = snapshot.proximity_sensors.get(sid)
            if sensor and sensor.state:
                results.append(DiagnosisResult(
                    sensor_id=sid,
                    fault_type="stuck_high",
                    confidence=0.85,
                    description=f"接近开关{sid}故障(卡高): 小车移动阶段本应false但为true",
                    category="proximity",
                ))
        for hid in route.hopper_ids:
            hopper = snapshot.hoppers.get(hid)
            if not hopper:
                continue
            if hopper.switch_open:
                key = f"{hid}:switch_stuck_open_moving"
                start = self._hopper_switch_fault_start.get(key, snapshot.timestamp)
                self._hopper_switch_fault_start[key] = start
                if snapshot.timestamp - start >= HOPPER_SWITCH_STUCK_OPEN_DURATION:
                    results.append(DiagnosisResult(
                        sensor_id=hid,
                        fault_type="hopper_switch_stuck_open",
                        confidence=0.85,
                        description=f"{hid}开关故障(卡开): 小车移动阶段开关为true持续{snapshot.timestamp-start:.0f}s",
                        category="hopper_switch",
                    ))
            else:
                self._hopper_switch_fault_start.pop(f"{hid}:switch_stuck_open_moving", None)

        if route.conveyor_ids:
            end_cid = route.conveyor_ids[-1]
            for cid in route.conveyor_ids:
                conv = snapshot.conveyors.get(cid)
                if not conv:
                    continue
                if cid == end_cid:
                    if conv.is_running:
                        results.append(DiagnosisResult(
                            sensor_id=f"{cid}_state",
                            fault_type="conveyor_should_stop",
                            confidence=0.85,
                            description=f"皮带{cid}异常: 小车移动阶段终点皮带应停止但为运行",
                            category="conveyor",
                        ))
                else:
                    if not conv.is_running:
                        results.append(DiagnosisResult(
                            sensor_id=f"{cid}_state",
                            fault_type="conveyor_should_run",
                            confidence=0.85,
                            description=f"皮带{cid}异常: 小车移动阶段非终点皮带应运行但为停止",
                            category="conveyor",
                        ))

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
                results.append(DiagnosisResult(
                    sensor_id=f"{cid}_state",
                    fault_type="conveyor_should_run",
                    confidence=0.85,
                    description=f"皮带{cid}异常: feeding阶段应运行但为停止",
                    category="conveyor",
                ))

        for hid in route.hopper_ids:
            hopper = snapshot.hoppers.get(hid)
            if not hopper:
                continue
            if not hopper.switch_open:
                results.append(DiagnosisResult(
                    sensor_id=hid,
                    fault_type="hopper_switch_stuck_closed",
                    confidence=0.80,
                    description=f"{hid}开关故障(卡关): feeding阶段开关未打开",
                    category="hopper_switch",
                ))

        for sid in route.proximity_sensor_ids:
            sensor = snapshot.proximity_sensors.get(sid)
            if not sensor:
                continue

            upstream = self._get_upstream_sensors(route, sid, snapshot)
            downstream = self._get_downstream_sensors(route, sid, snapshot)
            is_last = self._is_last_sensor(route, sid)

            # 卡低：上游和下游都true，本传感器false
            if not sensor.state:
                up_ok = len(upstream) > 0 and all(s.state for s in upstream)
                down_ok = len(downstream) > 0 and all(s.state for s in downstream)
                if up_ok and down_ok:
                    key = f"{sid}:stuck_low_mid_feeding"
                    start = self._proximity_fault_start.get(key, ts)
                    self._proximity_fault_start[key] = start
                    if ts - start >= FEEDING_MIDDLE_STUCK_LOW_DURATION:
                        results.append(DiagnosisResult(
                            sensor_id=sid,
                            fault_type="stuck_low",
                            confidence=0.90,
                            description=f"接近开关{sid}故障(卡低): 上/下游均点亮但本传感器未点亮持续{ts-start:.0f}s",
                            category="proximity",
                        ))
                elif not is_last:
                    self._proximity_fault_start.pop(f"{sid}:stuck_low_mid_feeding", None)
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
                self._proximity_fault_start.pop(f"{sid}:stuck_low_mid_feeding", None)
                up_off = len(upstream) > 0 and all(not s.state for s in upstream)
                down_off = len(downstream) > 0 and all(not s.state for s in downstream)
                if up_off and down_off:
                    results.append(DiagnosisResult(
                        sensor_id=sid,
                        fault_type="stuck_high",
                        confidence=0.90,
                        description=f"接近开关{sid}故障(卡高): 上/下游均未点亮但本传感器点亮",
                        category="proximity",
                    ))
                elif is_last:
                    upstream_false_count = sum(1 for s in upstream if not s.state)
                    if upstream_false_count >= 2:
                        key = f"{sid}:stuck_high_tail_feeding"
                        start = self._proximity_fault_start.get(key, ts)
                        self._proximity_fault_start[key] = start
                        if ts - start >= FEEDING_UPSTREAM_LIT_TIMEOUT_S:
                            results.append(DiagnosisResult(
                                sensor_id=sid,
                                fault_type="stuck_high",
                                confidence=0.85,
                                description=f"接近开关{sid}故障(卡高): 末尾传感器，{upstream_false_count}个上游未点亮但本传感器已点亮持续{ts-start:.0f}s",
                                category="proximity",
                            ))
                    else:
                        self._proximity_fault_start.pop(f"{sid}:stuck_high_tail_feeding", None)

        return results

    # ------------------------------------------------------------------
    # 阶段3：清空余料
    # ------------------------------------------------------------------

    def _check_clearing_stage(self, route, snapshot: SystemSnapshot) -> List[DiagnosisResult]:
        """清空余料阶段：开关全false，接近开关点亮不超5s，皮带全部运行"""
        results = []
        ts = snapshot.timestamp

        for cid in route.conveyor_ids:
            conv = snapshot.conveyors.get(cid)
            if conv and not conv.is_running:
                results.append(DiagnosisResult(
                    sensor_id=f"{cid}_state",
                    fault_type="conveyor_should_run",
                    confidence=0.85,
                    description=f"皮带{cid}异常: clearing阶段应运行但为停止",
                    category="conveyor",
                ))

        for hid in route.hopper_ids:
            hopper = snapshot.hoppers.get(hid)
            if not hopper:
                continue
            if hopper.switch_open:
                results.append(DiagnosisResult(
                    sensor_id=hid,
                    fault_type="hopper_switch_stuck_open",
                    confidence=0.85,
                    description=f"{hid}开关故障(卡开): 清空阶段开关应为false",
                    category="hopper_switch",
                ))

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
        """上料完成阶段：接近开关全false，开关全false，称重稳定，非终点皮带运行/终点皮带停止"""
        results = []

        if route.conveyor_ids:
            end_cid = route.conveyor_ids[-1]
            for cid in route.conveyor_ids:
                conv = snapshot.conveyors.get(cid)
                if not conv:
                    continue
                if cid == end_cid:
                    if conv.is_running:
                        results.append(DiagnosisResult(
                            sensor_id=f"{cid}_state",
                            fault_type="conveyor_should_stop",
                            confidence=0.85,
                            description=f"皮带{cid}异常: waiting阶段终点皮带应停止但为运行",
                            category="conveyor",
                        ))
                else:
                    if not conv.is_running:
                        results.append(DiagnosisResult(
                            sensor_id=f"{cid}_state",
                            fault_type="conveyor_should_run",
                            confidence=0.85,
                            description=f"皮带{cid}异常: waiting阶段非终点皮带应运行但为停止",
                            category="conveyor",
                        ))

        for sid in route.proximity_sensor_ids:
            sensor = snapshot.proximity_sensors.get(sid)
            if sensor and sensor.state:
                results.append(DiagnosisResult(
                    sensor_id=sid,
                    fault_type="stuck_high",
                    confidence=0.85,
                    description=f"接近开关{sid}故障(卡高): 上料完成阶段本应为false",
                    category="proximity",
                ))

        for hid in route.hopper_ids:
            hopper = snapshot.hoppers.get(hid)
            if not hopper:
                continue
            if hopper.switch_open:
                results.append(DiagnosisResult(
                    sensor_id=hid,
                    fault_type="hopper_switch_stuck_open",
                    confidence=0.85,
                    description=f"{hid}开关故障(卡开): 上料完成阶段应为false",
                    category="hopper_switch",
                ))
            vol = self._weight_volatility(hid, 3.0)
            if vol > WAITING_WEIGHT_VOLATILITY_THRESHOLD:
                results.append(DiagnosisResult(
                    sensor_id=hid,
                    fault_type="weight_volatile",
                    confidence=0.75,
                    description=f"{hid}称重故障: 上料完成阶段称重波动{vol:.3f}t",
                    category="hopper_weight",
                ))

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

            # 规则3：无任务时分料激活
            has_active = bool(snapshot.active_route_ids)
            if not has_active and (cart.left_divert or cart.right_divert):
                results.append(DiagnosisResult(
                    sensor_id=f"{cart_id}_divert",
                    fault_type="divert_no_task",
                    confidence=0.50,
                    description=f"{cart_id}分料异常: 无活跃路线但分料传感器激活",
                    category="cart",
                ))

        return results

    # ========================================================================
    # E. 皮带转速诊断
    # ========================================================================

    def _diagnose_conveyors(self, snapshot: SystemSnapshot) -> List[DiagnosisResult]:
        results = []
        ts = snapshot.timestamp

        for cid, conveyor in snapshot.conveyors.items():
            # 规则1：皮带运行但转速为0，需持续10秒
            key_zero = f"{cid}:speed_zero"
            if conveyor.is_running and conveyor.speed == 0:
                start = self._conveyor_fault_start.get(key_zero, ts)
                self._conveyor_fault_start[key_zero] = start
                if ts - start >= CONVEYOR_FAULT_DURATION:
                    results.append(DiagnosisResult(
                        sensor_id=f"{cid}_speed",
                        fault_type="speed_zero_while_running",
                        confidence=0.90,
                        description=f"转速传感器{cid}故障: 皮带运行但转速为0",
                        category="conveyor",
                    ))
            else:
                self._conveyor_fault_start.pop(key_zero, None)

            # 规则2：皮带停止但转速非0，需持续10秒
            key_nonzero = f"{cid}:speed_nonzero"
            if not conveyor.is_running and conveyor.speed != 0:
                start = self._conveyor_fault_start.get(key_nonzero, ts)
                self._conveyor_fault_start[key_nonzero] = start
                if ts - start >= CONVEYOR_FAULT_DURATION:
                    results.append(DiagnosisResult(
                        sensor_id=f"{cid}_speed",
                        fault_type="speed_nonzero_while_stopped",
                        confidence=0.90,
                        description=f"转速传感器{cid}异常: 皮带停止但转速={conveyor.speed}",
                        category="conveyor",
                    ))
            else:
                self._conveyor_fault_start.pop(key_nonzero, None)

            # 规则3：匀速运行阶段波动 > 30%，需持续10秒
            key_volatile = f"{cid}:speed_volatile"
            mean_speed = self._speed_mean(cid, 2.0)
            is_volatile = (conveyor.is_running and mean_speed > 0
                           and conveyor.speed != 0
                           and abs(conveyor.speed - mean_speed) / mean_speed > 0.30)
            if is_volatile:
                start = self._conveyor_fault_start.get(key_volatile, ts)
                self._conveyor_fault_start[key_volatile] = start
                if ts - start >= CONVEYOR_FAULT_DURATION:
                    deviation = abs(conveyor.speed - mean_speed) / mean_speed
                    results.append(DiagnosisResult(
                        sensor_id=f"{cid}_speed",
                        fault_type="speed_volatile",
                        confidence=0.50,
                        description=f"转速传感器{cid}波动异常: 偏离均值{deviation*100:.0f}%",
                        category="conveyor",
                    ))
            else:
                self._conveyor_fault_start.pop(key_volatile, None)

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

            # 规则1：活跃路线 FEEDING 但所有接近开关均为 false 超过 2s
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
                    results.append(DiagnosisResult(
                        sensor_id=route_id,
                        fault_type="route_all_sensors_false",
                        confidence=0.55,
                        description=f"{route_id}异常: FEEDING状态但所有接近开关为false",
                        category="cross_sensor",
                        related_sensors=list(route.proximity_sensor_ids),
                    ))

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
    # 公共：清空历史
    # ========================================================================

    def clear_history(self):
        self._proximity_history.clear()
        self._weight_history.clear()
        self._speed_history.clear()
        self._report_tracker.clear()
        self._conveyor_fault_start.clear()
        self._hopper_switch_fault_start.clear()
        self._proximity_fault_start.clear()
        self._route_state.clear()
        self._route_state_since.clear()
