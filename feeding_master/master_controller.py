"""
FeedingMaster 主控制循环 — 核心大脑

50ms 周期的控制循环:
  1. 拉取料位数据
  2. 检查传感器状态
  3. 路线状态机处理
  4. 状态转换引擎判定
  5. 执行器命令生成
  6. 推送控制指令

设计原则：
  - 零 UI 依赖
  - 通过 TCP JSON 与所有外部模块通信
  - 内部使用 plc_runtime 的纯逻辑模块
"""
import sys
import threading
import time
from typing import Dict, List, Optional, Set

from shared.plc_runtime.models import Conveyor, Sensor, TransferHopper
from shared.plc_runtime.actuator import (
    ActuatorAction,
    compute_route_belt_commands,
    compute_hopper_commands,
    compute_cart_target_position,
    compute_cart4_target_position,
    should_move_cart,
    compute_emergency_stop_commands,
)
from shared.route_state_manager import (
    RouteState, RouteStateManager, get_route_state_manager,
)
from shared.state_transition_engine import StateTransitionEngine
from feeding_master.tcp_server import FeedingMasterServer
from feeding_master.stock_client import StockClient
from feeding_master.schedule_manager import ScheduleManager, CART_TO_BELT, BELT_TO_CART
from feeding_master.clearing_config import (
    get_clearing_threshold, SEQUENTIAL_EARLY_MOVE_DELAY, MIN_FEEDING_TIME,
)

import config


class FeedingMasterController:
    """上料主控 — 控制大脑"""

    # 清空超时常量 (与仿真保持一致)
    _ENDPOINT_BASE = {'D7': 22.1, 'D8': 17.4, 'D9': 12.1}
    _LINE_SPACING = 5.4
    _HOPPER_BELT_TIMEOUTS = {
        ('route1', 'S-E1'): 8.4, ('route1', 'S-E4'): 34.4,
        ('route2', 'S-E2'): 9.6, ('route2', 'S-E4'): 34.4,
        ('route3', 'S-E5'): 12.3,
        ('route1', 'S-E8'): 24.7, ('route2', 'S-E8'): 24.7, ('route3', 'S-E8'): 24.7,
        ('route1', 'S-E10'): 15.3, ('route2', 'S-E10'): 15.3, ('route3', 'S-E10'): 15.3,
        ('route4', 'S-E6'): 10.6, ('route4', 'S-E7'): 23.3, ('route4', 'S-E9'): 20.2,
        ('route5', 'S-E6'): 10.6, ('route5', 'S-E7'): 23.3, ('route5', 'S-E9'): 20.2,
        ('route5', 'S-D5'): 12.3,
        ('route6', 'S-D13'): 8.0, ('route6', 'S-D2'): 27.0, ('route6', 'S-D4'): 9.6,
        ('route7', 'S-D1'): 27.0, ('route7', 'S-D3'): 15.9,
        ('route8', 'S-D4'): 9.6, ('route8', 'S-D2-2'): 7.3,
    }
    _ENDPOINT_SENSORS = {'D7': 'S-D7', 'D8': 'S-D8', 'D9': 'S-D9', 'D6': 'S-D6'}
    # 上料点切换清空判定传感器：从有料→无料时判定旧路线非共用皮带清空
    _SWITCH_CLEAR_SENSOR = {'D7': 'S-E8', 'D8': 'S-D2-2', 'D9': 'S-D9'}

    def __init__(self, tcp_server: FeedingMasterServer):
        self.server = tcp_server
        self.stock = StockClient()

        # 故障诊断客户端
        self._diag_client = None
        self._diag_thread: Optional[threading.Thread] = None
        self._diag_results: list = []

        # 路线管理
        self.route_manager = get_route_state_manager()
        self.state_engine = StateTransitionEngine()

        # 设备注册表
        self.conveyors: Dict[str, Conveyor] = {}
        self.hoppers: Dict[str, TransferHopper] = {}
        self._active_routes: Set[str] = set()

        # 传感器状态缓存
        self._sensor_states: dict = {}
        self._cart_positions: Dict[str, int] = {}
        self._cart_divert: Dict[str, tuple] = {}

        # 内部状态
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._tick_ms = 50
        self._total_runtime = 0.0

        # 调度管理器
        self.scheduler = ScheduleManager(self.stock, self.route_manager)
        self.scheduler.on_sequence_ready(self._on_schedule_sequence)

        # 状态引擎路由配置
        self._configure_state_engine()

        # 注册回调
        self.server.on_sensor_states(self._on_sensor_states)
        self.server.on_manual_start(self._on_manual_start)
        self.server.on_manual_stop(self._on_manual_stop)
        self.server.on_emergency_stop(self._on_emergency_stop)
        self.server.on_belt_active(self._on_belt_active)

    def _configure_state_engine(self):
        for rid, r in config.FEED_ROUTES.items():
            cart = self.route_manager.ROUTE_CARTS.get(rid, '')
            self.state_engine.configure_route(
                rid,
                belts=r['conveyors'],
                hoppers=[h for h in r['hoppers'] if h],
                cart=cart,
                endpoint=r['conveyors'][-1] if r['conveyors'] else '',
            )

    # ── 传感器状态接收 ──

    def _on_sensor_states(self, data: dict):
        """接收 Upper Computer 转发的传感器状态"""
        self._sensor_states = data
        self._cart_positions = data.get('cart_positions', {})
        self._cart_moving = data.get('cart_moving', {})
        self._cart_divert = {
            k: tuple(v) for k, v in data.get('cart_divert', {}).items()
        }
        self._cart_limits = data.get('cart_limits', {})
        self.scheduler.update_cart_state(self._cart_positions, self._cart_divert)
        self.scheduler._laser_states = data.get('laser_sensor_states', {})
        self.scheduler._maintenance_bins = set(data.get('maintenance_bins', []))
        self._d7_feed_override = data.get('d7_feed_override', '')
        self._d9_feed_override = data.get('d9_feed_override', '')
        # 上料点原料状态（来自 feed_material_service 响应）
        feed_material = data.get('feed_material_states', {})
        if feed_material:
            self._feed_material_states = feed_material
        # 同步调度开关: UI点击"调度服务"后FM才开始请求调度
        self.scheduler.set_active(data.get('scheduling_active', False))

        # 同步活跃路线: 仿真激活了哪些路线，FeedingMaster 就追踪哪些
        sim_active = set(data.get('active_routes', []))
        sim_states = data.get('route_states', {})

        # FM判断cart到达
        for route_id in sim_active & self._active_routes:
            ctx = self.route_manager.get_route_context(route_id)
            if not ctx:
                continue
            cart_id = ctx.assigned_cart
            if cart_id:
                ctx.cart_moving = self._cart_moving.get(cart_id, False)
                if ctx.state == RouteState.MOVING_TO_TARGET:
                    cur = self._cart_positions.get(cart_id, 1)
                    moving = self._cart_moving.get(cart_id, False)
                    if not moving and cur == ctx.cart_target_position:
                        # 检查分料状态是否匹配目标列
                        divert_ok = True
                        div = self._cart_divert.get(cart_id, (True, False))
                        target_bin = ctx.target_bin or ''
                        if cart_id == 'Cart4' and target_bin.startswith('S'):
                            try:
                                n = int(target_bin[1:])
                                expected = (True, False) if 1 <= n <= 6 else (False, True)
                                if tuple(div) != expected:
                                    divert_ok = False
                            except ValueError:
                                pass
                        elif cart_id in ('Cart1', 'Cart2', 'Cart3'):
                            target_col = target_bin.split('-')[0] if target_bin else ''
                            col_map = {'P1': (True, False), 'P2': (True, False), 'P3': (False, True), 'P4': (False, True)}
                            expected = col_map.get(target_col)
                            if expected and tuple(div) != expected:
                                divert_ok = False
                        if divert_ok:
                            self.route_manager.set_route_state(route_id, RouteState.FEEDING)
                            ctx.feeding_start_time = self._total_runtime
                            ctx.early_moved_from_clearing = False
                            ctx.clearing_strategy = 'reverse'
                            print(f"[FM] {route_id} cart到达→FEEDING pos={cur}", flush=True)

        # FM自主管理路线生命周期, 不从仿真同步添加/移除

    # ── 主循环 ──

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._start_diag_client()
        print("[FeedingMaster] 控制循环已启动 (50ms)", flush=True)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def _run(self):
        last_tick = time.time()
        last_level_report = 0.0
        while self._running:
            now = time.time()
            delta = now - last_tick
            last_tick = now
            self._total_runtime += delta

            try:
                self._tick(delta)
            except Exception as e:
                print(f"[FeedingMaster] tick 异常: {e}", file=sys.stderr)

            # 每5s发送料位报告
            if self._total_runtime - last_level_report >= 5.0:
                last_level_report = self._total_runtime
                try:
                    levels = self.stock.get_all_levels()
                    if levels:
                        # 只发送 bin_id + level_pct + capacity
                        slim = [{'bin_id': b['bin_id'], 'level_pct': b.get('level_pct', 0), 'capacity': b.get('capacity', 0)} for b in levels]
                        self.server.send_levels(slim)
                except Exception as e:
                    print(f"[FeedingMaster] 料位发送异常: {e}", file=sys.stderr)

            elapsed = time.time() - now
            sleep_time = max(0, self._tick_ms / 1000.0 - elapsed)
            time.sleep(sleep_time)

    def _tick(self, delta_seconds: float):
        """一个控制周期"""
        # 1. 拉取料位
        levels = self.stock.get_all_levels()
        level_map = {b['bin_id']: b for b in levels} if levels else {}

        # 上料点无料自动切换检测
        self._check_feed_point_switch()

        # 追踪指令变化: new_cmds继承prev_cmds, 未被本帧更新的保持原状态
        prev_cmds = getattr(self, '_last_commands', {})

        commands = []
        new_cmds = dict(prev_cmds)  # 继承上帧: 打开的斗仍然是打开
        # 小车归位（旧路线关闭时触发）
        cart_return = getattr(self, '_pending_cart_return', None)
        if cart_return:
            self._pending_cart_return = None
            commands.append({'device': 'cart', 'id': cart_return[0], 'action': 'move',
                           'target': cart_return[1], 'route_id': '', 'left_divert': True, 'right_divert': False})
            print(f"[FM] 小车归位: {cart_return[0]}→{cart_return[1]}", flush=True)
        # 上料点切换: 停止旧上料点
        pending_stop = getattr(self, '_pending_feed_stop', None)
        if pending_stop:
            commands.append({'device': 'feed_point', 'id': pending_stop, 'action': 'stop'})
            self._pending_feed_stop = None
        pending_start = getattr(self, '_pending_feed_start', None)
        if pending_start:
            commands.append({'device': 'feed_point', 'id': pending_start, 'action': 'start'})
            self._pending_feed_start = None
        # 非共用皮带清空：判定传感器从有料→无料时完成
        pending_clear = getattr(self, '_pending_belt_clear', {})
        if pending_clear:
            proximity = self._sensor_states.get('proximity', {})
            for sensor_id in list(pending_clear.keys()):
                non_shared, was_active = pending_clear[sensor_id]
                is_active = proximity.get(sensor_id, False)
                if is_active:
                    # 传感器有料 → 记录状态
                    pending_clear[sensor_id] = (non_shared, True)
                elif was_active:
                    # 传感器从有料→无料 → 清空完成
                    del pending_clear[sensor_id]
                    for cid in non_shared:
                        commands.append({'device': 'belt', 'id': cid, 'action': 'stop'})
                    print(f"[FM] 判定传感器 {sensor_id} 熄灭 → 停止非共用皮带 {non_shared}", flush=True)
                    self._try_activate_pending_route()
        for route_id in list(self._active_routes):
            ctx = self.route_manager.get_route_context(route_id)
            if not ctx:
                continue

            cart_id = ctx.assigned_cart or ''
            cart_target = ctx.cart_target_position
            cart_pos = self._cart_positions.get(cart_id, 1) if cart_id else 1
            if cart_id:
                ctx.cart_moving = self._cart_moving.get(cart_id, False)
            # 调试：MOVING_TO_TARGET 时仅位置变化时输出一次
            if ctx.state == RouteState.MOVING_TO_TARGET and cart_id:
                last_key = f"_{route_id}_move_debug"
                cur_val = (cart_pos, ctx.cart_moving)
                if cur_val != getattr(ctx, last_key, None):
                    setattr(ctx, last_key, cur_val)
                    print(f"[FM-debug] {route_id} MOVING: {cart_id} pos={cart_pos}→{cart_target} moving={ctx.cart_moving}", flush=True)
            target_bin = ctx.target_bin or ''

            level = 0.0
            b = level_map.get(target_bin, {})
            if b:
                level = b.get('level_pct', 0)

            strategy = getattr(ctx, 'clearing_strategy', 'reverse')
            if ctx.state == RouteState.FEEDING and strategy == 'reverse':
                strategy = self._resolve_clearing_strategy(route_id)
                ctx.clearing_strategy = strategy

            # 最小feeding时间: 刚进入FEEDING或刚自动续料, 3s内不触发清空
            if ctx.state == RouteState.FEEDING:
                feeding_elapsed = self._total_runtime - getattr(ctx, 'feeding_start_time', 0)
                if feeding_elapsed < MIN_FEEDING_TIME and strategy == 'reverse':
                    strategy = 'reverse'  # 保持, 但跳过清空判定

            # 清空计时器 (所有策略都追踪传感器)
            sensor_clear_timers = {}
            sensor_clear_timeouts = {}
            if ctx.state == RouteState.CLEARING:
                sensor_clear_timers, sensor_clear_timeouts = self._build_clearing_data(ctx, route_id, strategy)

            # 顺序策略: 进入 MOVING_TO_TARGET 时立即设置目标+关闭斗+终点皮带
            if (ctx.state == RouteState.MOVING_TO_TARGET and strategy == 'sequential'
                    and cart_id in ('Cart1', 'Cart2') and not getattr(ctx, 'early_moved_from_clearing', False)):
                belt_id = CART_TO_BELT.get(cart_id, '')
                nxt = self.scheduler.get_next_bin(belt_id)
                if nxt:
                    self.scheduler.pop_next_bin(belt_id)
                    try:
                        next_pos = int(nxt.split('-')[1])
                        ctx.cart_target_position = next_pos
                        ctx.target_bin = nxt
                        ctx.cart_moving = True
                        ctx.early_moved_from_clearing = True
                        ctx.clearing_strategy = 'reverse'
                        self.scheduler.mark_executing(belt_id, route_id, nxt)
                        print(f"[FM] {route_id} 顺序清空: 立即移小车 {cart_id}→{next_pos} ({nxt})", flush=True)
                    except (ValueError, IndexError):
                        pass

            # 状态引擎判定
            belt_id_for_engine = CART_TO_BELT.get(cart_id, '')
            self.state_engine._override_threshold = get_clearing_threshold(belt_id_for_engine or '', strategy)
            has_next = bool(self.scheduler.get_next_bin(belt_id_for_engine)) if belt_id_for_engine else False
            has_seq = self.scheduler.has_sequence(belt_id_for_engine) if belt_id_for_engine else False
            next_state, actions = self.state_engine.evaluate(
                route_id, ctx.state,
                level_sensors={'__target__': level},
                cart_sensor={cart_id: cart_pos} if cart_id else {},
                cart_target=cart_target,
                cart_moving=ctx.cart_moving,
                cart=cart_id,
                clearing_strategy=strategy,
                schedule_has_next=has_next,
                schedule_next_round_empty=(not has_seq and not has_next),
                current_time=self._total_runtime,
                sensor_clear_timers=sensor_clear_timers or None,
                sensor_clear_timeouts=sensor_clear_timeouts or None,
            )

            # 状态变更 → 详细日志
            if next_state != ctx.state:
                old = ctx.state
                self.route_manager.set_route_state(route_id, next_state)
                parts = [f"[FM] {route_id}: {old.value} → {next_state.value}"]

                if next_state.value == 'feeding':
                    parts.append(f"→ {target_bin} (料位{level:.0f}%)")
                    convs = config.FEED_ROUTES.get(route_id, {}).get('conveyors', [])
                    parts.append(f"皮带: {','.join(convs)}")
                    if ctx.assigned_hoppers:
                        parts.append(f"斗开: {','.join(ctx.assigned_hoppers)}")
                    if strategy != 'reverse':
                        parts.append(f"策略: {strategy}")
                    # 重置顺序清空标记，确保下一轮能正常触发 early move
                    ctx.early_moved_from_clearing = False
                    ctx.clearing_strategy = 'reverse'
                    # 启动上料点（silo_out 由 silo_gate 替代）
                    fp = ctx.feed_point or config.FEED_ROUTES.get(route_id, {}).get('feed_point', '')
                    if fp and fp != 'silo_out':
                        commands.append({'device': 'feed_point', 'id': fp, 'action': 'start'})
                        new_cmds[f"feed_point:{fp}"] = 'start'
                        print(f"[FM] {route_id} feed_point start: {fp}", flush=True)
                    # 高位储料仓上料 → 打开对应卸料门
                    if fp == 'silo_out' and target_bin.startswith('S'):
                        gate_id = f"silo_gate_{target_bin}"
                        commands.append({'device': 'silo_gate', 'id': gate_id, 'action': 'open'})
                        new_cmds[f"silo_gate:{target_bin}"] = 'open'
                        print(f"[FM] {route_id} silo_gate open: {gate_id}", flush=True)
                elif old.value == 'feeding':
                    # 离开 FEEDING → 停止上料点（silo_out 由 silo_gate 替代）
                    fp = ctx.feed_point or config.FEED_ROUTES.get(route_id, {}).get('feed_point', '')
                    if fp and fp != 'silo_out':
                        commands.append({'device': 'feed_point', 'id': fp, 'action': 'stop'})
                        new_cmds[f"feed_point:{fp}"] = 'stop'
                        print(f"[FM] {route_id} feed_point stop: {fp}", flush=True)
                    # 高位储料仓上料 → 关闭对应卸料门
                    if fp == 'silo_out' and target_bin and target_bin.startswith('S'):
                        gate_id = f"silo_gate_{target_bin}"
                        commands.append({'device': 'silo_gate', 'id': gate_id, 'action': 'close'})
                        new_cmds[f"silo_gate:{target_bin}"] = 'close'
                        print(f"[FM] {route_id} silo_gate close: {gate_id}", flush=True)
                elif next_state.value == 'clearing':
                    threshold = get_clearing_threshold(belt_id_for_engine or '', strategy)
                    parts.append(f"料位{level:.0f}%≥{threshold}% 策略={strategy}")
                elif next_state.value == 'moving_to_target':
                    parts.append(f"小车 {cart_id}→{cart_target}")
                elif next_state.value == 'waiting':
                    parts.append("清空完成")
                    # 反序: 只停终点皮带, 非终点皮带继续运行
                    convs = config.FEED_ROUTES.get(route_id, {}).get('conveyors', [])
                    if convs:
                        final = convs[-1]
                        commands.append({'device': 'belt', 'id': final, 'action': 'stop'})
                        new_cmds[f"belt:{final}"] = 'stop'
                        parts.append(f"停终点:{final}")

                ctx.clearing_start_time = self._total_runtime if next_state.value == 'clearing' else getattr(ctx, 'clearing_start_time', 0)
                print(' | '.join(parts), flush=True)

                # 路线完成 → 释放资源 + 自动续料/节能待机
                if next_state.value in ('waiting', 'standby'):
                    self.route_manager._release_resources(route_id)
                    belt_id = CART_TO_BELT.get(cart_id, '')
                    completed_bin = ctx.target_bin
                    self.scheduler.mark_completed(belt_id)
                    # 对齐序列：如果序列首项是刚完成的料仓，跳过它
                    nxt = self.scheduler.get_next_bin(belt_id)
                    if nxt and nxt == completed_bin:
                        self.scheduler.pop_next_bin(belt_id)
                        nxt = self.scheduler.get_next_bin(belt_id)
                    if nxt:
                        self.scheduler.pop_next_bin(belt_id)
                        self._pending_auto_continue = (belt_id, nxt)
                    else:
                        # 无下一仓: 进入节能待机, 停止所有皮带
                        self.route_manager.set_route_state(route_id, RouteState.STANDBY)
                        route_convs = config.FEED_ROUTES.get(route_id, {}).get('conveyors', [])
                        for cid in route_convs:
                            commands.append({'device': 'belt', 'id': cid, 'action': 'stop'})
                            new_cmds[f"belt:{cid}"] = 'stop'
                        for hid in ctx.assigned_hoppers:
                            commands.append({'device': 'hopper', 'id': hid, 'action': 'close'})
                            new_cmds[f"hopper:{hid}"] = 'close'
                        self._active_routes.discard(route_id)
                        if not hasattr(self, '_deactivated_routes'):
                            self._deactivated_routes = set()
                        self._deactivated_routes.add(route_id)
                        print(f"[FM] {route_id}: waiting → standby | 节能待机", flush=True)
                        ctx.clearing_start_time = 0

            # 执行器命令
            route_conveyors = config.FEED_ROUTES.get(route_id, {}).get('conveyors', [])
            final_conv = route_conveyors[-1] if route_conveyors else ''
            cart_at_target = not should_move_cart(cart_pos, cart_target)

            if ctx.state in (RouteState.FEEDING, RouteState.CLEARING, RouteState.MOVING_TO_TARGET):
                # MOVING_TO_TARGET: 强制cart_at_target=False, 非终点运行终点停
                _cat = cart_at_target if ctx.state != RouteState.MOVING_TO_TARGET else False
                belt_cmds = compute_route_belt_commands(
                    route_conveyors, final_conv,
                    is_feeding=(ctx.state == RouteState.FEEDING),
                    is_clearing=(ctx.state == RouteState.CLEARING),
                    cart_at_target=_cat,
                    clearing_strategy=strategy,
                )
                for cid, action in belt_cmds.items():
                    cmd = {'device': 'belt', 'id': cid, 'action': action.value}
                    commands.append(cmd)
                    new_cmds[f"belt:{cid}"] = action.value

                # FEEDING: 确保上料点启动（无延迟，与皮带同帧）
                if ctx.state == RouteState.FEEDING:
                    fp = ctx.feed_point or config.FEED_ROUTES.get(route_id, {}).get('feed_point', '')
                    if fp:
                        cmd = {'device': 'feed_point', 'id': fp, 'action': 'start'}
                        commands.append(cmd)
                        new_cmds[f"feed_point:{fp}"] = 'start'

                # MOVING_TO_TARGET: 不改变斗状态 (保持上一轮的开关)
                if ctx.state != RouteState.MOVING_TO_TARGET:
                    _hs = {}
                    for hid in ctx.assigned_hoppers:
                        prev = prev_cmds.get(f"hopper:{hid}", 'close')
                        _hs[hid] = (prev == 'open')
                    hopper_cmds = compute_hopper_commands(
                        ctx.assigned_hoppers,
                        is_feeding=(ctx.state == RouteState.FEEDING),
                        cart_at_target=cart_at_target,
                        hopper_states=_hs,
                    )
                    if strategy == 'column_switch':
                        hopper_cmds = {hid: ActuatorAction.OPEN for hid in ctx.assigned_hoppers}
                    for hid, action in hopper_cmds.items():
                        key = f"hopper:{hid}"
                        cmd = {'device': 'hopper', 'id': hid, 'action': action.value}
                        commands.append(cmd)
                        new_cmds[key] = action.value

            elif ctx.state == RouteState.WAITING and route_conveyors:
                # WAITING: 非终点皮带保持运行, 仅终点皮带已在上方状态转换中停止
                for cid in route_conveyors[:-1]:
                    new_cmds[f"belt:{cid}"] = 'start'
                for hid in ctx.assigned_hoppers:
                    new_cmds[f"hopper:{hid}"] = 'close'

            if cart_id:
                if cart_id == 'Cart4':
                    target = compute_cart4_target_position(target_bin)
                else:
                    target = compute_cart_target_position(target_bin, cart_id)
                if target is not None:
                    ctx.cart_target_position = target  # 同步: FM知道真实目标
                if target is not None and should_move_cart(cart_pos, target):
                    left_div, right_div = self._compute_cart_divert(cart_id, target_bin)
                    cmd = {'device': 'cart', 'id': cart_id, 'action': 'move',
                           'target': target, 'route_id': route_id,
                           'left_divert': left_div, 'right_divert': right_div}
                    commands.append(cmd)
                    # 同步更新FM自身的分料状态缓存，避免送到调度请求时使用旧值
                    self._cart_divert[cart_id] = (left_div, right_div)
                    new_cmds[f"cart:{cart_id}"] = f"→{target}"

        # 指令变化时输出
        if new_cmds != prev_cmds:
            self._last_commands = dict(new_cmds)
            changed = {k: v for k, v in new_cmds.items() if prev_cmds.get(k) != v}
            added = {k: v for k, v in new_cmds.items() if k not in prev_cmds}
            parts = []
            if added:
                belts_start = [k.split(':')[1] for k, v in added.items()
                               if k.startswith('belt:') and v not in ('stop',)]
                belts_stop = [k.split(':')[1] for k, v in added.items()
                              if k.startswith('belt:') and v in ('stop',)]
                hoppers_open = [k.split(':')[1] for k, v in added.items()
                                if k.startswith('hopper:') and v not in ('close',)]
                hoppers_close = [k.split(':')[1] for k, v in added.items()
                                 if k.startswith('hopper:') and v in ('close',)]
                carts = [(k.split(':')[1], v) for k, v in added.items() if k.startswith('cart:')]
                if belts_start: parts.append(f"启动皮带: {','.join(belts_start)}")
                if belts_stop: parts.append(f"停止皮带: {','.join(belts_stop)}")
                if hoppers_open: parts.append(f"打开斗: {','.join(hoppers_open)}")
                if hoppers_close: parts.append(f"关闭斗: {','.join(hoppers_close)}")
                if carts: parts.append(f"小车: {', '.join(f'{c}{t}' for c,t in carts)}")
            if changed:
                belts_changed = [k.split(':')[1] for k, v in changed.items()
                                 if k.startswith('belt:') and v == 'stop']
                hoppers_changed = [k.split(':')[1] for k, v in changed.items()
                                   if k.startswith('hopper:') and v == 'close']
                if belts_changed: parts.append(f"停止皮带: {','.join(belts_changed)}")
                if hoppers_changed: parts.append(f"关闭斗: {','.join(hoppers_changed)}")
            if parts:
                print(f"[FM] 指令变化: {'; '.join(parts)}", flush=True)

        # 3. 调度引擎联动
        self.scheduler.tick(self._total_runtime)

        # 3.5 延迟自动续料: 在构建 route_info 前处理，确保 HMI 不显示已关闭的旧路线
        pending = getattr(self, '_pending_auto_continue', None)
        if pending:
            self._pending_auto_continue = None
            belt_id, nxt = pending
            route_id2 = self._pick_route_for_bin(belt_id, nxt)
            if route_id2:
                old_route = None
                for rid in list(self._active_routes):
                    ctx = self.route_manager.get_route_context(rid)
                    if ctx and CART_TO_BELT.get(ctx.assigned_cart or '', '') == belt_id and rid != route_id2:
                        if ctx.state in (RouteState.WAITING, RouteState.STANDBY):
                            old_route = rid
                            break
                if old_route:
                    old_convs = set(config.FEED_ROUTES.get(old_route, {}).get('conveyors', []))
                    new_convs = set(config.FEED_ROUTES.get(route_id2, {}).get('conveyors', []))
                    non_shared = old_convs - new_convs
                    self._do_switch(old_route, route_id2, nxt)
                    # 停止旧路线非共用皮带
                    for cid in non_shared:
                        commands.append({'device': 'belt', 'id': cid, 'action': 'stop'})
                        new_cmds[f"belt:{cid}"] = 'stop'
                    print(f"[FM] {belt_id} 自动续料 {old_route}→{route_id2} → {nxt} (停非共用: {non_shared})", flush=True)
                elif self.activate_route(route_id2, nxt):
                    print(f"[FM] {belt_id} 自动续料 → {nxt}", flush=True)

        # 4. 推送控制指令 (含路线状态+调度序列用于HMI显示)
        deactivated = getattr(self, '_deactivated_routes', set())
        # 始终构建路线状态和调度序列信息（即使无指令也推送，保证HMI实时更新）
        route_info = {}
        for rid in self._active_routes:
            ctx = self.route_manager.get_route_context(rid)
            if ctx:
                route_info[rid] = {
                    'state': ctx.state.value,
                    'target_bin': ctx.target_bin or '',
                    'cart_target': ctx.cart_target_position,
                    'cart_moving': ctx.cart_moving,
                    'clearing_strategy': getattr(ctx, 'clearing_strategy', 'reverse'),
                    'early_moved': getattr(ctx, 'early_moved_from_clearing', False),
                    'assigned_cart': ctx.assigned_cart or '',
                    'assigned_hoppers': list(ctx.assigned_hoppers) if ctx.assigned_hoppers else [],
                    'feeding_start_time': getattr(ctx, 'feeding_start_time', 0.0),
                    'clearing_start_time': getattr(ctx, 'clearing_start_time', 0.0),
                }
        for rid in deactivated:
            ctx = self.route_manager.get_route_context(rid)
            if ctx:
                route_info[rid] = {
                    'state': ctx.state.value,
                    'target_bin': ctx.target_bin or '',
                    'cart_target': ctx.cart_target_position,
                    'cart_moving': ctx.cart_moving,
                    'clearing_strategy': getattr(ctx, 'clearing_strategy', 'reverse'),
                    'early_moved': getattr(ctx, 'early_moved_from_clearing', False),
                    'assigned_cart': ctx.assigned_cart or '',
                    'assigned_hoppers': list(ctx.assigned_hoppers) if ctx.assigned_hoppers else [],
                    'feeding_start_time': getattr(ctx, 'feeding_start_time', 0.0),
                    'clearing_start_time': getattr(ctx, 'clearing_start_time', 0.0),
                }
            else:
                route_info[rid] = {'state': 'standby', 'target_bin': '', 'cart_target': 0, 'cart_moving': False}
        sched_info = {
            'executing_bin': dict(self.scheduler._executing_bin),
            'sequences': {k: list(v) for k, v in self.scheduler._sequences.items()},
        }
        # 从活跃路线补充 executing_bin（覆盖调度器可能遗漏的更新，如提前移动跳过WAITING）
        for rid in self._active_routes:
            ctx = self.route_manager.get_route_context(rid)
            if ctx and ctx.target_bin and ctx.state in (RouteState.FEEDING, RouteState.CLEARING, RouteState.MOVING_TO_TARGET):
                belt_id = CART_TO_BELT.get(ctx.assigned_cart, '')
                if belt_id:
                    sched_info['executing_bin'][belt_id] = ctx.target_bin
        if commands or deactivated:
            if self._diag_results:
                # 过滤: 排除正在清空的非共用皮带的 conveyor_should_run 误报
                clearing_belts = set(getattr(self, '_pending_belt_clear', {}).keys())
                filtered = []
                for r in self._diag_results:
                    fid = r.get('sensor_id', '') if isinstance(r, dict) else getattr(r, 'sensor_id', '')
                    ftype = r.get('fault_type', '') if isinstance(r, dict) else getattr(r, 'fault_type', '')
                    # 皮带ID格式: E1_state, D7_state 等
                    belt_id = fid.replace('_state', '') if fid.endswith('_state') else ''
                    if belt_id in clearing_belts and ftype == 'conveyor_should_run':
                        continue  # 跳过正在清空的皮带误报
                    filtered.append(r)
                self._last_diag = filtered
                self._last_diag_time = self._total_runtime
                self._diag_results.clear()
            else:
                # 无新结果, 3s后清除HMI(让遗留故障尽快消失)
                if hasattr(self, '_last_diag') and hasattr(self, '_last_diag_time'):
                    if self._total_runtime - self._last_diag_time > 3.0:
                        self._last_diag = None
        diag = getattr(self, '_last_diag', None)
        # 上料点切换阶段1: 停止旧路线（在 send_commands 之前，确保本帧推送 IDLE 状态）
        pending_switch = getattr(self, '_pending_route_switch', None)
        if pending_switch:
            self._pending_route_switch = None
            old_rid, new_rid, tgt_bin = pending_switch
            self._switch_route_phase1(old_rid, new_rid, tgt_bin)
        # 指令变化时推送，避免每帧(50ms)高频发送相同指令
        last_cmds = getattr(self, '_last_sent_commands', [])
        last_sched = getattr(self, '_last_sent_sched', {})
        cmds_changed = (commands != last_cmds)
        sched_changed = (sched_info != last_sched)
        if cmds_changed or sched_changed or diag:
            self._last_sent_commands = list(commands)
            self._last_sent_sched = dict(sched_info) if sched_info else {}
            self.server.send_commands(commands, route_info, sched_info, diag)
        if hasattr(self, '_deactivated_routes'):
            self._deactivated_routes.clear()

        # 6. 延迟上料点切换阶段2: 非共用皮带清空后激活新路线
        # (由 _try_activate_pending_route 在每帧检查 _pending_belt_clear 时触发)

    # ── 外部接口 ──

    def activate_route(self, route_id: str, target_bin: str):
        """激活一条路线, 若cart已在目标位则直接FEEDING跳过MOVE"""
        ok = self.route_manager.start_route(route_id, target_bin)
        if ok:
            # start_route不处理S格式(Cart4), 补设正确目标
            ctx = self.route_manager.get_route_context(route_id)
            if ctx and ctx.assigned_cart == 'Cart4' and target_bin.startswith('S'):
                t = compute_cart4_target_position(target_bin)
                if t is not None:
                    ctx.cart_target_position = t
            ctx = self.route_manager.get_route_context(route_id)
            if ctx:
                ctx.clearing_strategy = 'reverse'
                ctx.early_moved_from_clearing = False
            if ctx and ctx.assigned_cart:
                cart_id = ctx.assigned_cart
                cur = self._cart_positions.get(cart_id, 1)
                # Cart4: 用compute_cart4_target_position算真实目标(start_route不处理S格式)
                tgt = (compute_cart4_target_position(target_bin) 
                       if cart_id == 'Cart4' and target_bin.startswith('S')
                       else ctx.cart_target_position)
                if cur == tgt:
                    ctx.cart_target_position = tgt  # 修正
                    self.route_manager.set_route_state(route_id, RouteState.FEEDING)
                    ctx.feeding_start_time = self._total_runtime
                    print(f"[FeedingMaster] 路线 {route_id} → {target_bin} cart已在位→FEEDING", flush=True)
                else:
                    print(f"[FeedingMaster] 路线 {route_id} → {target_bin} 已激活", flush=True)
            self._active_routes.add(route_id)
            belt_id = CART_TO_BELT.get(
                self.route_manager.ROUTE_CARTS.get(route_id, ''), '')
            self.scheduler.mark_executing(belt_id, route_id, target_bin)
        else:
            print(f"[FeedingMaster] 路线 {route_id} 激活失败 (资源占用?)", flush=True)
        return ok

    def _on_schedule_sequence(self, belt_id: str, sequence: list):
        """收到调度序列 → 若皮带空闲则自动启动"""
        # 兼职调度回切: 执行中但新序列是主列且当前路线是跨列→强制停止
        if self.scheduler.is_executing(belt_id):
            first_bin = sequence[0] if sequence else ''
            from scheduling.bin_config import BELT_TO_COL_PREFIX, CROSS_COL_PREFIX
            default_prefix = BELT_TO_COL_PREFIX.get(belt_id, '')
            cross_prefix = CROSS_COL_PREFIX.get(belt_id, '')
            if cross_prefix and first_bin.startswith(default_prefix):
                current_bin = self.scheduler._executing_bin.get(belt_id, '')
                if current_bin.startswith(cross_prefix):
                    # 跨列→主列回切
                    for rid in self._active_routes:
                        ctx = self.route_manager.get_route_context(rid)
                        if ctx and CART_TO_BELT.get(ctx.assigned_cart or '', '') == belt_id \
                           and ctx.target_bin and ctx.target_bin.startswith(cross_prefix):
                            print(f"[FM] {belt_id} 兼职回切: {ctx.target_bin}→{first_bin}", flush=True)
                            self._stop_route_for_switch(rid)
                            return
            print(f"[FM] {belt_id} 已在执行中, 序列缓存", flush=True)
            return
        # 双保险: 检查 _active_routes 中是否有同皮带活跃路线
        for rid in self._active_routes:
            ctx = self.route_manager.get_route_context(rid)
            if ctx and CART_TO_BELT.get(ctx.assigned_cart or '', '') == belt_id:
                print(f"[FM] {belt_id} 已有活跃路线 {rid}, 序列缓存", flush=True)
                return

        first_bin = sequence[0] if sequence else None
        if not first_bin:
            return

        route_id = self._pick_route_for_bin(belt_id, first_bin)
        print(f"[FM] {belt_id} pick {first_bin} → {route_id}", flush=True)
        if not route_id:
            # D6: 上料点物料不可用，跳过该仓继续下一个
            if belt_id == 'D6':
                self.scheduler.pop_next_bin(belt_id)
                print(f"[FM] D6 跳过 {first_bin} (上料点物料不可用)，尝试下一仓", flush=True)
            return

        self.scheduler.pop_next_bin(belt_id)
        ok = self.activate_route(route_id, first_bin)
        print(f"[FM] {belt_id} activate {route_id} → {first_bin}: {'OK' if ok else 'FAIL'}", flush=True)

    def _has_feed_material(self, feed_point: str, bin_prefix: str) -> bool:
        """通过 TCP 查询上料点原料服务端"""
        try:
            import json, socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(('127.0.0.1', 9010))
            s.sendall(json.dumps({'type': 'has_material', 'feed_point': feed_point, 'bin_prefix': bin_prefix}).encode('utf-8'))
            data = s.recv(4096).decode('utf-8')
            s.close()
            return json.loads(data).get('result', True)
        except Exception:
            return True  # 服务端不可用时默认有料

    def _pick_route_for_bin(self, belt_id: str, bin_id: str) -> Optional[str]:
        """根据料仓ID选择路线（复用仿真侧的 BIN_TO_AVAILABLE_ROUTES）"""
        if belt_id == 'D6':
            return 'route5'

        available = config.BIN_TO_AVAILABLE_ROUTES.get(bin_id, [])
        if not available:
            return None

        # 根据上料点激光传感器过滤有料的路线
        laser = getattr(self.scheduler, '_laser_states', {})
        prefix = bin_id.split('-')[0]
        priority_map = config.FEED_POINT_PRIORITY.get(prefix, {})

        candidates = []
        for feed_point, route_id in available:
            # 过滤: 路线必须匹配当前皮带（跨列调度关键）
            route_cart = self.route_manager.ROUTE_CARTS.get(route_id, '')
            route_belt = CART_TO_BELT.get(route_cart, '')
            if route_belt and route_belt != belt_id:
                continue
            # feed3 优先级供 P2/P3，P4 不使用 feed3
            if feed_point == 'feed3' and prefix not in ('P2', 'P3'):
                continue
            # D7: 用户选择了指定上料点, 只选该上料点的路线
            d7_override = getattr(self, '_d7_feed_override', '')
            if belt_id == 'D7' and d7_override and feed_point != d7_override:
                continue
            # D9: 用户选择了指定上料点, 只选该上料点的路线
            d9_override = getattr(self, '_d9_feed_override', '')
            if belt_id == 'D9' and d9_override and feed_point != d9_override:
                continue
            # D8: feed3 有料→选 feed3, 无料→选 silo_out
            if belt_id == 'D8' and feed_point == 'silo_out' and self._has_feed_material('feed3', prefix):
                continue  # feed3 有料，跳过 silo_out
            # silo_out 无需激光检测（默认有料）
            has_material = (feed_point == 'silo_out' or self._has_feed_material(feed_point, prefix))
            if not has_material:
                continue
            priority = priority_map.get(feed_point, 99)
            candidates.append((priority, feed_point, route_id))

        if not candidates:
            # D7: 用户选择的上料点无料，回退到默认 feed1_1
            if belt_id == 'D7' and d7_override:
                print(f"[FM] D7 上料点 {d7_override} 无料，回退默认 feed1_1", flush=True)
                for feed_point, route_id in available:
                    if feed_point == 'feed1_1':
                        if laser.get('feed1_1', True):
                            return route_id
                return None
            return None
        candidates.sort()
        return candidates[0][2]

    def _check_feed_point_switch(self):
        """上料点无料/高优先级恢复时自动切换路线（D7/D8/D9）— 延迟到 tick 末尾执行"""
        laser = getattr(self.scheduler, '_laser_states', {})
        d7_override = getattr(self, '_d7_feed_override', '')

        for route_id in list(self._active_routes):
            ctx = self.route_manager.get_route_context(route_id)
            if not ctx or ctx.state.value not in ('feeding',):
                continue

            cart_id = ctx.assigned_cart or ''
            belt_id = CART_TO_BELT.get(cart_id, '')
            if belt_id not in ('D7', 'D8', 'D9', 'D6'):
                continue

            fp = ctx.feed_point or config.FEED_ROUTES.get(route_id, {}).get('feed_point', '')
            if not fp:
                continue

            target_bin = ctx.target_bin or ''
            if not target_bin:
                continue

            # D6: 仅一个上料点 feed2_2，无料时进入清空余料，有料时恢复
            if belt_id == 'D6':
                prefix = target_bin.split('-')[0]
                if not self._has_feed_material('feed2_2', prefix):
                    if ctx.state != RouteState.CLEARING:
                        self._pending_feed_stop = fp
                        ctx.state = RouteState.CLEARING
                        print(f"[FM] D6 上料点 {fp} 无料({prefix}) → 进入清空余料", flush=True)
                elif ctx.state == RouteState.CLEARING:
                    # 物料恢复，恢复上料
                    self._pending_feed_start = fp
                    ctx.state = RouteState.FEEDING
                    print(f"[FM] D6 上料点 {fp} 有料({prefix}) → 恢复上料", flush=True)
                continue

            # D8: feed3 当前物料无料 → 切换 silo_out
            if belt_id == 'D8' and fp == 'feed3':
                prefix = target_bin.split('-')[0]
                if not self._has_feed_material('feed3', prefix):
                    available = config.BIN_TO_AVAILABLE_ROUTES.get(target_bin, [])
                    for fp_candidate, rid in available:
                        if fp_candidate == 'silo_out' and rid != route_id:
                            self._pending_route_switch = (route_id, rid, target_bin)
                            print(f"[FM] D8 上料点 feed3 无料({prefix}) → 切换 {rid}", flush=True)
                            return
                continue

            # D9: feed2_2 当前物料无料 → 切换 silo_out
            if belt_id == 'D9' and fp == 'feed2_2':
                prefix = target_bin.split('-')[0]
                if not self._has_feed_material('feed2_2', prefix):
                    available = config.BIN_TO_AVAILABLE_ROUTES.get(target_bin, [])
                    for fp_candidate, rid in available:
                        if fp_candidate == 'silo_out' and rid != route_id:
                            self._pending_route_switch = (route_id, rid, target_bin)
                            print(f"[FM] D9 上料点 feed2_2 无料({prefix}) → 切换 {rid}", flush=True)
                            return
                continue

            # silo_out 默认有料，无需切换
            if fp == 'silo_out':
                continue
                continue

            prefix = target_bin.split('-')[0]
            priority_map = config.FEED_POINT_PRIORITY.get(prefix, {})
            available = config.BIN_TO_AVAILABLE_ROUTES.get(target_bin, [])
            current_priority = priority_map.get(fp, 99)

            # 1. 当前上料点无料 → 寻找替代路线
            if not laser.get(fp, True):
                new_route = self._find_switch_target(route_id, fp, target_bin, belt_id, available, laser, priority_map, d7_override, current_priority)
                if new_route:
                    self._pending_route_switch = (route_id, new_route, target_bin)
                    print(f"[FM] {route_id} 上料点 {fp} 无料，延迟切换 → {new_route}", flush=True)
                    return  # 一帧只处理一次切换

            # 2. 反向切换: 更高优先级上料点恢复有料
            for fp_candidate, new_route_id in available:
                if new_route_id == route_id:
                    continue
                if fp_candidate == 'silo_out':
                    continue
                candidate_priority = priority_map.get(fp_candidate, 99)
                if candidate_priority < current_priority and laser.get(fp_candidate, True):
                    if belt_id == 'D7' and d7_override:
                        if fp_candidate != d7_override and fp != d7_override:
                            continue
                    self._pending_route_switch = (route_id, new_route_id, target_bin)
                    print(f"[FM] {route_id} 上料点 {fp_candidate} 恢复有料，延迟切换 → {new_route_id}", flush=True)
                    return

    def _find_switch_target(self, route_id, fp, target_bin, belt_id, available, laser, priority_map, d7_override, current_priority):
        """找到切换目标路线"""
        if belt_id == 'D7':
            fallback_order = ['feed2_1', 'feed1_1', 'feed1_2']
            if d7_override:
                fallback_order = [d7_override] + [f for f in fallback_order if f != d7_override]
            for f in fallback_order:
                if laser.get(f, True):
                    for fp_candidate, rid in available:
                        if fp_candidate == f and rid != route_id:
                            return rid
        else:
            sorted_fps = sorted(available, key=lambda x: priority_map.get(x[0], 99))
            for fp_candidate, rid in sorted_fps:
                if rid == route_id:
                    continue
                if fp_candidate == 'silo_out' or laser.get(fp_candidate, True):
                    return rid
        return None

    def _switch_route_phase1(self, old_route_id: str, new_route_id: str, target_bin: str):
        """阶段1: 停止旧上料点，旧路线设IDLE，等待判定传感器清空"""
        old_ctx = self.route_manager.get_route_context(old_route_id)
        if not old_ctx:
            return
        old_fp = old_ctx.feed_point or config.FEED_ROUTES.get(old_route_id, {}).get('feed_point', '')
        old_ctx.state = RouteState.IDLE
        old_ctx.target_bin = ''           # 清除目标仓，确保桥接收到IDLE时移除route_to_bin
        old_ctx.cart_target_position = 0  # 清除小车目标
        old_ctx.cart_moving = False
        if not hasattr(self, '_deactivated_routes'):
            self._deactivated_routes = set()
        self._deactivated_routes.add(old_route_id)  # 加入deactivated，route_info会包含
        if old_fp:
            self._pending_feed_stop = old_fp
        old_convs = set(config.FEED_ROUTES.get(old_route_id, {}).get('conveyors', []))
        new_convs = set(config.FEED_ROUTES.get(new_route_id, {}).get('conveyors', []))
        non_shared = old_convs - new_convs
        if non_shared:
            belt_id = CART_TO_BELT.get(old_ctx.assigned_cart or '', '')
            clear_sensor = self._SWITCH_CLEAR_SENSOR.get(belt_id, '')
            if not hasattr(self, '_pending_belt_clear'):
                self._pending_belt_clear = {}
            # 存储: {sensor_id: (non_shared_belts, was_active)}
            self._pending_belt_clear[clear_sensor] = (non_shared, True)
            if not hasattr(self, '_pending_route_activate'):
                self._pending_route_activate = {}
            switch_key = f"{old_route_id}→{new_route_id}"
            self._pending_route_activate[switch_key] = (old_route_id, new_route_id, target_bin, clear_sensor)
            print(f"[FM] {old_route_id}→{new_route_id} 阶段1: 停止旧上料点 {old_fp}, 等待 {clear_sensor} 熄灭", flush=True)
        else:
            self._do_switch(old_route_id, new_route_id, target_bin)
            print(f"[FM] {old_route_id}→{new_route_id} 切换完成 (无共用皮带)", flush=True)

    def _do_switch(self, old_route_id: str, new_route_id: str, target_bin: str):
        """同时停旧路线+激活新路线"""
        old_ctx = self.route_manager.get_route_context(old_route_id)
        belt_id = CART_TO_BELT.get(old_ctx.assigned_cart or '', '') if old_ctx else ''
        if old_ctx:
            print(f"[FM] {old_route_id}: {old_ctx.state.value} → idle (彻底关闭)", flush=True)
            old_ctx.state = RouteState.IDLE
            old_ctx.target_bin = ''
            old_ctx.cart_target_position = 0
            old_ctx.cart_moving = False
            self._active_routes.discard(old_route_id)
            if not hasattr(self, '_deactivated_routes'):
                self._deactivated_routes = set()
            self._deactivated_routes.add(old_route_id)
            self.route_manager._release_resources(old_route_id)
        if self.activate_route(new_route_id, target_bin):
            self.scheduler.mark_executing(belt_id, new_route_id, target_bin)
        else:
            # 激活失败，回退旧路线
            if old_ctx:
                old_ctx.state = RouteState.WAITING
                self._active_routes.add(old_route_id)
                self._deactivated_routes.discard(old_route_id)
            print(f"[FM] _do_switch {old_route_id}→{new_route_id} 激活失败", flush=True)

    def _switch_route(self, old_route_id: str, new_route_id: str, target_bin: str):
        """两阶段切换（兼容旧调用）"""
        self._switch_route_phase1(old_route_id, new_route_id, target_bin)

    def _try_activate_pending_route(self):
        """检查所有非共用皮带是否已清空，若清空则激活新路线（阶段2）"""
        pending_activate = getattr(self, '_pending_route_activate', {})
        if not pending_activate:
            return
        pending_clear = getattr(self, '_pending_belt_clear', {})
        for switch_key in list(pending_activate.keys()):
            old_route_id, new_route_id, target_bin, clear_sensor = pending_activate[switch_key]
            # 判定传感器已熄灭（已从 pending_clear 移除）→ 可激活新路线
            if clear_sensor in pending_clear:
                continue
            del pending_activate[switch_key]
            self._do_switch(old_route_id, new_route_id, target_bin)
            print(f"[FM] {switch_key} 阶段2: 判定传感器 {clear_sensor} 熄灭，激活新路线", flush=True)

    # ── 清空检测 ──

    def _calc_endpoint_timeout(self, belt_id: str, target_bin: str) -> float:
        if belt_id not in self._ENDPOINT_BASE:
            return 30.0
        try:
            row = int(target_bin.split('-')[1])
        except (ValueError, IndexError):
            row = 7
        base = self._ENDPOINT_BASE[belt_id]
        distance = base + self._LINE_SPACING * (8 - row)
        return distance / 2.5 + 2.0

    def _build_clearing_data(self, ctx, route_id: str, strategy: str = 'reverse') -> tuple:
        """构建清空检测数据。
        反序清空时有下一仓 → 只需终点传感器清空，非终点皮带余料由下一仓消耗。
        """
        timers = getattr(ctx, 'sensor_clear_timers', {}) or {}
        timeouts = {}
        proximity = self._sensor_states.get('proximity', {})
        route_sensors = self.route_manager.ROUTE_PROXIMITY_SENSORS.get(route_id, [])

        route_cfg = config.FEED_ROUTES.get(route_id, {})
        conveyors = route_cfg.get('conveyors', [])
        final_conveyor = conveyors[-1] if conveyors else ''
        endpoint_sensor = self._ENDPOINT_SENSORS.get(final_conveyor, '')

        # 反序清空 + 有下一仓 → 仅追踪终点传感器
        belt_id = CART_TO_BELT.get(ctx.assigned_cart or '', '')
        has_next = bool(self.scheduler.get_next_bin(belt_id)) if belt_id else False
        only_endpoint = (strategy == 'reverse' and has_next)

        for sid in route_sensors:
            is_active = proximity.get(sid, False)
            if only_endpoint and sid != endpoint_sensor:
                # 非终点传感器：有下一仓时跳过，直接清空计时器
                if sid in timers:
                    del timers[sid]
                continue
            if sid == endpoint_sensor:
                timeouts[sid] = self._calc_endpoint_timeout(final_conveyor, ctx.target_bin or '')
            else:
                timeouts[sid] = self._HOPPER_BELT_TIMEOUTS.get((route_id, sid), 30.0)

            if is_active:
                if sid in timers:
                    del timers[sid]
            else:
                if sid not in timers:
                    timers[sid] = self._total_runtime

        ctx.sensor_clear_timers = timers
        return timers, timeouts

    def _on_manual_start(self, bin_id: str, route_id: str):
        """手动上料: 上位机点击料仓触发"""
        if self.scheduler.is_executing(CART_TO_BELT.get(
                self.route_manager.ROUTE_CARTS.get(route_id, ''), '')):
            print(f"[FM] 手动上料拒绝: {route_id} 皮带已在执行中", flush=True)
            return
        if route_id not in config.FEED_ROUTES:
            print(f"[FM] 手动上料失败: 未知路线 {route_id}", flush=True)
            return
        if not self.activate_route(route_id, bin_id):
            return
        # 手动模式不走调度序列, 直接标记执行中
        belt_id = CART_TO_BELT.get(self.route_manager.ROUTE_CARTS.get(route_id, ''), '')
        self.scheduler.mark_executing(belt_id, route_id, bin_id)
        print(f"[FM] 手动上料: {route_id} → {bin_id}", flush=True)

    def _on_emergency_stop(self):
        """急停: 立即停止所有路线 + 关全部设备"""
        for route_id in list(self._active_routes):
            ctx = self.route_manager.get_route_context(route_id)
            if ctx:
                self.route_manager._release_resources(route_id)
                belt_id = CART_TO_BELT.get(self.route_manager.ROUTE_CARTS.get(route_id, ''), '')
                self.scheduler.mark_completed(belt_id)
        deactivated = list(self._active_routes)
        self._active_routes.clear()
        if not hasattr(self, '_deactivated_routes'):
            self._deactivated_routes = set()
        self._deactivated_routes.update(deactivated)
        # 急停指令通过commands下发
        cmds = []
        from shared.plc_runtime.actuator import compute_emergency_stop_commands
        estop = compute_emergency_stop_commands(
            list(self.conveyors.keys()) if not hasattr(self, 'conveyors') or not self.conveyors
            else self.conveyors,
            list(self.hoppers.keys())
        )
        # 简单处理: 直接发送全停指令
        for cid in config.CONVEYORS:
            cmds.append({'device': 'belt', 'id': cid, 'action': 'stop'})
        for hid in config.TRANSFER_HOPPERS:
            cmds.append({'device': 'hopper', 'id': hid, 'action': 'close'})
        self.server.send_commands(cmds)
        print("[FM] 急停! 全部设备已停止", flush=True)

    def _on_manual_stop(self, route_id: str):
        """手动停止"""
        if route_id not in self._active_routes:
            return
        ctx = self.route_manager.get_route_context(route_id)
        if not ctx:
            return
        cart_id = ctx.assigned_cart or ''
        belt_id = CART_TO_BELT.get(cart_id, '')
        # 清除序列+待执行(防止auto-continue覆盖)
        self.scheduler._sequences.pop(belt_id, None)
        if getattr(self, '_pending_auto_continue', (None, None))[0] == belt_id:
            self._pending_auto_continue = None
        # 清除scheduler状态(防止idle检测重新触发)
        self.scheduler.mark_completed(belt_id)
        self.scheduler._last_request[belt_id] = self._total_runtime  # 重置冷却

        if ctx.state == RouteState.FEEDING:
            self.route_manager.set_route_state(route_id, RouteState.CLEARING)
            ctx.clearing_start_time = self._total_runtime
            print(f"[FM] 手动停止: {route_id} FEEDING→CLEARING→STANDBY", flush=True)
        elif ctx.state in (RouteState.CLEARING, RouteState.WAITING, RouteState.MOVING_TO_TARGET):
            self.route_manager._release_resources(route_id)
            self.route_manager.set_route_state(route_id, RouteState.STANDBY)
            self._active_routes.discard(route_id)
            if not hasattr(self, '_deactivated_routes'):
                self._deactivated_routes = set()
            self._deactivated_routes.add(route_id)
            print(f"[FM] 手动停止: {route_id} {ctx.state.value}→STANDBY", flush=True)
            self.route_manager._release_resources(route_id)
            self.scheduler.mark_completed(belt_id)
            self.route_manager.set_route_state(route_id, RouteState.STANDBY)
            self._active_routes.discard(route_id)
            if not hasattr(self, '_deactivated_routes'):
                self._deactivated_routes = set()
            self._deactivated_routes.add(route_id)
            print(f"[FM] 手动停止: {route_id} WAITING→STANDBY", flush=True)
        else:
            # MOVING_TO_TARGET等 → 直接停
            self.route_manager._release_resources(route_id)
            self.scheduler.mark_completed(belt_id)
            self.route_manager.set_route_state(route_id, RouteState.STANDBY)
            self._active_routes.discard(route_id)
            if not hasattr(self, '_deactivated_routes'):
                self._deactivated_routes = set()
            self._deactivated_routes.add(route_id)
            print(f"[FM] 手动停止: {route_id} {ctx.state.value}→STANDBY", flush=True)

    def _stop_route_for_switch(self, route_id: str):
        """兼职调度回切：停止当前跨列路线，让主列路线接管"""
        ctx = self.route_manager.get_route_context(route_id)
        if not ctx:
            return
        cart_id = ctx.assigned_cart or ''
        belt_id = CART_TO_BELT.get(cart_id, '')
        # 清除旧序列
        self.scheduler._sequences.pop(belt_id, None)
        if getattr(self, '_pending_auto_continue', (None, None))[0] == belt_id:
            self._pending_auto_continue = None
        self.scheduler.mark_completed(belt_id)
        self.scheduler._last_request[belt_id] = self._total_runtime

        if ctx.state == RouteState.FEEDING:
            self.route_manager.set_route_state(route_id, RouteState.CLEARING)
            ctx.clearing_start_time = self._total_runtime
            print(f"[FM] 兼职回切: {route_id} {ctx.target_bin}→CLEARING", flush=True)
        else:
            self.route_manager._release_resources(route_id)
            self.route_manager.set_route_state(route_id, RouteState.STANDBY)
            self._active_routes.discard(route_id)
            if not hasattr(self, '_deactivated_routes'):
                self._deactivated_routes = set()
            self._deactivated_routes.add(route_id)
            print(f"[FM] 兼职回切: {route_id} {ctx.state.value}→STANDBY", flush=True)

    def _on_belt_active(self, belt_id: str, active: bool):
        """UI点击皮带按钮 → 激活该皮带 + 强制启动调度"""
        if active and belt_id in ('D6', 'D7', 'D8', 'D9'):
            self.scheduler._belt_activated[belt_id] = True
            print(f"[FM-Sched] {belt_id} 启动调度", flush=True)
            self.scheduler.request_schedule_now(belt_id)

    def _resolve_clearing_strategy(self, route_id: str) -> str:
        """根据缓存序列中紧挨的下一个料仓判断清空策略(与纯仿真一致)"""
        ctx = self.route_manager.get_route_context(route_id)
        if not ctx or not ctx.target_bin:
            return 'reverse'
        if ctx.assigned_cart == 'Cart4':
            return 'column_switch'
        belt_id = CART_TO_BELT.get(ctx.assigned_cart, '')
        if not belt_id:
            return 'reverse'
        nxt = self.scheduler.get_next_bin(belt_id)
        if not nxt:
            return 'column_switch' if not self.scheduler.has_sequence(belt_id) else 'reverse'
        # 对齐：若序列首项与当前正在执行的料仓相同，跳过取下一个
        if nxt == ctx.target_bin:
            self.scheduler.pop_next_bin(belt_id)
            nxt = self.scheduler.get_next_bin(belt_id)
            if not nxt:
                return 'column_switch' if not self.scheduler.has_sequence(belt_id) else 'reverse'
        cur_col = ctx.target_bin.split('-')[0]
        next_col = nxt.split('-')[0]
        if cur_col != next_col:
            return 'column_switch'
        cur_row = int(ctx.target_bin.split('-')[1])
        next_row = int(nxt.split('-')[1])
        if next_row < cur_row:
            if ctx.assigned_hoppers:
                # 产线1/2（row 1-2）作为下一目标，且当前料仓产线位置≤3时，用反序代替顺序清空
                if next_row <= 2 and cur_row <= 3:
                    return 'reverse'
                return 'sequential'
            return 'reverse'
        return 'reverse'

    def _start_diag_client(self):
        """启动故障诊断客户端 (后台线程)"""
        if self._diag_thread:
            return
        import socket as _sk
        self._diag_thread = threading.Thread(target=self._diag_loop, daemon=True)
        self._diag_thread.start()

    def _diag_loop(self):
        import socket as _sk, json as _json
        sock = None
        while self._running:
            try:
                if sock is None:
                    sock = _sk.socket(_sk.AF_INET, _sk.SOCK_STREAM)
                    sock.settimeout(3)
                    sock.connect(('127.0.0.1', 8890))
                    sock.settimeout(None)
                # 发送状态快照
                snap = self._build_diag_snapshot()
                sock.sendall((_json.dumps(snap, ensure_ascii=False) + "\n").encode("utf-8"))
                # 接收诊断结果
                buf = b""
                sock.settimeout(2)
                while b"\n" not in buf:
                    chunk = sock.recv(4096)
                    if not chunk: break
                    buf += chunk
                if buf:
                    resp = _json.loads(buf.decode("utf-8").strip())
                    results = resp.get("diagnosis_results", [])
                    if results:
                        self._diag_results = results
            except Exception:
                if sock:
                    try: sock.close()
                    except: pass
                    sock = None
            time.sleep(0.5)

    def _build_diag_snapshot(self) -> dict:
        """构建诊断快照 (匹配 TcpDataAdapter 格式)"""
        # 传感器: {"S-E1": bool, ...}
        sensors = dict(self._sensor_states.get('proximity', {}))
        # 斗: {"hopper1": {"switch": bool, "weight": float}, ...}
        hoppers = {}
        for hid, h in self.hoppers.items():
            hoppers[hid] = {"switch": h.is_open, "weight": h.get_display_weight()}
        # 皮带转速传感器: {"S-CV-E1": int, ...}
        speed_map = {
            'E1': 'S-CV-E1','E2': 'S-CV-E2','E4': 'S-CV-E4','E5': 'S-CV-E5',
            'E6': 'S-CV-E6','E7': 'S-CV-E7','E8': 'S-CV-E8','E9': 'S-CV-E9','E10': 'S-CV-E10',
            'D1': 'S-CV-D1','D2': 'S-CV-D2','D3': 'S-CV-D3','D4': 'S-CV-D4','D5': 'S-CV-D5',
            'D6': 'S-CV-D6','D7': 'S-CV-D7','D8': 'S-CV-D8','D9': 'S-CV-D9','D13': 'S-CV-D13',
        }
        # 从桥接的belt_states构造转速(非零=运行中)
        belt_states = self._sensor_states.get('belt_states', {})
        conv_sensors = {}
        for cid, sid in speed_map.items():
            if belt_states.get(cid, False):
                conv_sensors[sid] = 100  # 运行中
            else:
                conv_sensors[sid] = 0
        # 小车: {"Cart1": {"position": int, "left_limit": bool, ...}, ...}
        carts = {}
        for cart_id in ['Cart1', 'Cart2', 'Cart3']:
            pos = self._cart_positions.get(cart_id, 1)
            default_div = self._cart_divert.get(cart_id, (True, False))
            carts[cart_id] = {
                "position": pos, "left_limit": pos==1, "right_limit": pos==7,
                "left_divert": default_div[0],
                "right_divert": default_div[1],
            }
        pos4 = self._cart_positions.get('Cart4', 1)
        default_div = self._cart_divert.get('Cart4', (True, False))
        carts['Cart4'] = {
            "position": pos4, "left_limit": pos4==1, "right_limit": pos4==6,
            "left_divert": default_div[0],
            "right_divert": default_div[1],
        }
        # 路线状态
        route_states = {}
        for rid in ['route1','route2','route3','route4','route5','route6','route7','route8']:
            ctx = self.route_manager.get_route_context(rid)
            route_states[rid] = ctx.state.value if ctx else 'idle'
        # 清空策略传给诊断 (用于顺序策略终点皮带例外)
        clearing_strategies = {}
        for rid in ['route1','route2','route3','route4','route5','route6','route7','route8']:
            ctx = self.route_manager.get_route_context(rid)
            if ctx and hasattr(ctx, 'clearing_strategy'):
                clearing_strategies[rid] = ctx.clearing_strategy
        return {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sensors": sensors,
            "hoppers": hoppers,
            "conveyor_sensors": conv_sensors,
            "cart_sensors": carts,
            "route_states": route_states,
            "clearing_strategies": clearing_strategies,
            "feed_signals": {},  # FM模式无此数据
        }

    def deactivate_route(self, route_id: str):
        """停用路线"""
        self.route_manager.stop_route(route_id)
        self._active_routes.discard(route_id)

    def get_active_routes(self) -> Set[str]:
        return set(self._active_routes)

    @staticmethod
    def _compute_cart_divert(cart_id: str, target_bin: str) -> tuple:
        """根据小车ID和目标料仓计算分料方向"""
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
        elif cart_id == 'Cart4':
            if target_bin.startswith('S'):
                try:
                    num = int(target_bin[1:])
                    return (True, False) if 1 <= num <= 6 else (False, True)
                except ValueError:
                    pass
            return (True, False)
        return (False, False)
