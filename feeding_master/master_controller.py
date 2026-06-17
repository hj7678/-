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

from controllers.plc_runtime.models import Conveyor, Sensor, TransferHopper
from controllers.plc_runtime.actuator import (
    ActuatorAction,
    compute_route_belt_commands,
    compute_hopper_commands,
    compute_cart_target_position,
    compute_cart4_target_position,
    should_move_cart,
    compute_emergency_stop_commands,
)
from controllers.route_state_manager import (
    RouteState, RouteStateManager, get_route_state_manager,
)
from state_transition_engine import StateTransitionEngine
from feeding_master.tcp_server import FeedingMasterServer
from feeding_master.stock_client import StockClient
from feeding_master.schedule_manager import ScheduleManager, CART_TO_BELT, BELT_TO_CART

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

    def __init__(self, tcp_server: FeedingMasterServer):
        self.server = tcp_server
        self.stock = StockClient()

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
                        if cart_id in ('Cart1', 'Cart2', 'Cart3'):
                            div = self._cart_divert.get(cart_id, (True, False))
                            target_col = (ctx.target_bin or '').split('-')[0] if ctx.target_bin else ''
                            col_map = {'P1': (True, False), 'P2': (True, False), 'P3': (False, True), 'P4': (False, True)}
                            expected = col_map.get(target_col)
                            if expected and tuple(div) != expected:
                                divert_ok = False
                        if divert_ok:
                            self.route_manager.set_route_state(route_id, RouteState.FEEDING)
                            ctx.feeding_start_time = self._total_runtime
                            print(f"[FM] {route_id} cart到达→FEEDING pos={cur}", flush=True)

        # FM自主管理路线生命周期, 不从仿真同步添加/移除

    # ── 主循环 ──

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print("[FeedingMaster] 控制循环已启动 (50ms)", flush=True)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def _run(self):
        last_tick = time.time()
        while self._running:
            now = time.time()
            delta = now - last_tick
            last_tick = now
            self._total_runtime += delta

            try:
                self._tick(delta)
            except Exception as e:
                print(f"[FeedingMaster] tick 异常: {e}", file=sys.stderr)

            elapsed = time.time() - now
            sleep_time = max(0, self._tick_ms / 1000.0 - elapsed)
            time.sleep(sleep_time)

    def _tick(self, delta_seconds: float):
        """一个控制周期"""
        # 1. 拉取料位
        levels = self.stock.get_all_levels()
        level_map = {b['bin_id']: b for b in levels} if levels else {}


        # 追踪指令变化: new_cmds继承prev_cmds, 未被本帧更新的保持原状态
        prev_cmds = getattr(self, '_last_commands', {})

        # 2. 遍历活跃路线，执行状态机
        commands = []
        new_cmds = dict(prev_cmds)  # 继承上帧: 打开的斗仍然是打开
        for route_id in list(self._active_routes):
            ctx = self.route_manager.get_route_context(route_id)
            if not ctx:
                continue

            cart_id = ctx.assigned_cart or ''
            cart_target = ctx.cart_target_position
            cart_pos = self._cart_positions.get(cart_id, 1) if cart_id else 1
            if cart_id:
                ctx.cart_moving = self._cart_moving.get(cart_id, False)
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
                if feeding_elapsed < 3.0 and strategy == 'reverse':
                    strategy = 'reverse'  # 保持, 但跳过清空判定

            # 清空计时器 (所有策略都追踪传感器)
            sensor_clear_timers = {}
            sensor_clear_timeouts = {}
            if ctx.state == RouteState.CLEARING:
                sensor_clear_timers, sensor_clear_timeouts = self._build_clearing_data(ctx, route_id)

            # 顺序策略: 提前移小车
            if (ctx.state == RouteState.CLEARING and strategy == 'sequential'
                    and cart_id in ('Cart1', 'Cart2') and not getattr(ctx, 'early_moved_from_clearing', False)):
                clearing_elapsed = self._total_runtime - getattr(ctx, 'clearing_start_time', 0)
                if clearing_elapsed >= 3.0:
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
                            print(f"[FM] {route_id} 顺序清空3s → 提前移小车 {cart_id}→{next_pos} ({nxt})", flush=True)
                        except (ValueError, IndexError):
                            pass

            # 顺序策略: 小车提前到达 → 直接进入FEEDING
            if (ctx.state == RouteState.CLEARING and getattr(ctx, 'early_moved_from_clearing', False)
                    and not ctx.cart_moving and cart_pos == cart_target):
                self.route_manager.set_route_state(route_id, RouteState.FEEDING)
                ctx.early_moved_from_clearing = False
                print(f"[FM] {route_id}: clearing → feeding | 小车 {cart_id} 到达 {cart_pos} (提前移动完成)", flush=True)
                # 继续使用当前 state (已是FEEDING)

            # 状态引擎判定
            belt_id_for_engine = CART_TO_BELT.get(cart_id, '')
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
                    # 列出将启动的皮带
                    convs = config.FEED_ROUTES.get(route_id, {}).get('conveyors', [])
                    parts.append(f"皮带: {','.join(convs)}")
                    if ctx.assigned_hoppers:
                        parts.append(f"斗开: {','.join(ctx.assigned_hoppers)}")
                    if strategy != 'reverse':
                        parts.append(f"策略: {strategy}")
                elif next_state.value == 'clearing':
                    threshold = {'sequential': 98, 'reverse': 95, 'column_switch': 92}.get(strategy, 95)
                    if cart_id == 'Cart3':
                        threshold = 94
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
                    self.scheduler.mark_completed(belt_id)
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
                        parts.append("节能待机")
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
                )
                for cid, action in belt_cmds.items():
                    cmd = {'device': 'belt', 'id': cid, 'action': action.value}
                    commands.append(cmd)
                    new_cmds[f"belt:{cid}"] = action.value

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
                    cmd = {'device': 'cart', 'id': cart_id, 'action': 'move', 'target': target, 'route_id': route_id}
                    commands.append(cmd)
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

        # 4. 推送控制指令 (含路线状态+调度序列用于HMI显示)
        deactivated = getattr(self, '_deactivated_routes', set())
        if commands or deactivated:
            route_info = {}
            for rid in self._active_routes:
                ctx = self.route_manager.get_route_context(rid)
                if ctx:
                    route_info[rid] = {
                        'state': ctx.state.value,
                        'target_bin': ctx.target_bin or '',
                        'cart_target': ctx.cart_target_position,
                        'cart_moving': ctx.cart_moving,
                    }
            for rid in deactivated:
                ctx = self.route_manager.get_route_context(rid)
                route_info[rid] = {'state': ctx.state.value if ctx else 'standby'}
                ctx = self.route_manager.get_route_context(rid)
                if ctx:
                    route_info[rid] = {
                        'state': ctx.state.value,
                        'target_bin': ctx.target_bin or '',
                        'cart_target': ctx.cart_target_position,
                        'cart_moving': ctx.cart_moving,
                    }
            sched_info = {
                'executing_bin': dict(self.scheduler._executing_bin),
                'sequences': {k: list(v) for k, v in self.scheduler._sequences.items()},
            }
            self.server.send_commands(commands, route_info, sched_info)
            if hasattr(self, '_deactivated_routes'):
                self._deactivated_routes.clear()

        # 5. 延迟自动续料: 等上一轮的关闭斗指令先执行, 下一tick再开新路线
        pending = getattr(self, '_pending_auto_continue', None)
        if pending:
            self._pending_auto_continue = None
            belt_id, nxt = pending
            route_id2 = self._pick_route_for_bin(belt_id, nxt)
            if route_id2:
                if self.activate_route(route_id2, nxt):
                    print(f"[FM] {belt_id} 自动续料 → {nxt}", flush=True)

    # ── 外部接口 ──

    def activate_route(self, route_id: str, target_bin: str):
        """激活一条路线, 若cart已在目标位则直接FEEDING跳过MOVE"""
        ok = self.route_manager.start_route(route_id, target_bin)
        if ok:
            ctx = self.route_manager.get_route_context(route_id)
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
        if self.scheduler.is_executing(belt_id):
            print(f"[FM] {belt_id} 已在执行中, 序列缓存", flush=True)
            return

        first_bin = sequence[0] if sequence else None
        if not first_bin:
            return

        route_id = self._pick_route_for_bin(belt_id, first_bin)
        print(f"[FM] {belt_id} pick {first_bin} → {route_id}", flush=True)
        if not route_id:
            return

        self.scheduler.pop_next_bin(belt_id)
        ok = self.activate_route(route_id, first_bin)
        print(f"[FM] {belt_id} activate {route_id} → {first_bin}: {'OK' if ok else 'FAIL'}", flush=True)

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
            # feed3 优先级供 P2/P3，P4 不使用 feed3
            if feed_point == 'feed3' and prefix not in ('P2', 'P3'):
                continue
            # silo_out 无需激光检测（默认有料）
            has_material = (feed_point == 'silo_out' or laser.get(feed_point, True))
            if not has_material:
                continue
            priority = priority_map.get(feed_point, 99)
            candidates.append((priority, feed_point, route_id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]

    def _resolve_clearing_strategy(self, route_id: str) -> str:
        """根据下一料仓与当前料仓的关系确定清空策略"""
        ctx = self.route_manager.get_route_context(route_id)
        if not ctx or not ctx.target_bin:
            return 'reverse'

        # D6: 一律换列
        if ctx.assigned_cart == 'Cart4':
            return 'column_switch'

        belt_id = CART_TO_BELT.get(ctx.assigned_cart, '')
        if not belt_id:
            return 'reverse'

        nxt = self.scheduler.get_next_bin(belt_id)
        if not nxt:
            return 'reverse'

        cur_col = ctx.target_bin.split('-')[0]
        next_col = nxt.split('-')[0]

        if cur_col != next_col:
            return 'column_switch'

        cur_row = int(ctx.target_bin.split('-')[1])
        next_row = int(nxt.split('-')[1])

        if next_row < cur_row and cur_row >= 4:
            if ctx.assigned_hoppers:
                return 'sequential'
        return 'reverse'

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

    def _build_clearing_data(self, ctx, route_id: str) -> tuple:
        """构建清空检测所需的 sensor_clear_timers 和 sensor_clear_timeouts"""
        timers = getattr(ctx, 'sensor_clear_timers', {}) or {}
        timeouts = {}
        proximity = self._sensor_states.get('proximity', {})
        route_sensors = self.route_manager.ROUTE_PROXIMITY_SENSORS.get(route_id, [])

        route_cfg = config.FEED_ROUTES.get(route_id, {})
        conveyors = route_cfg.get('conveyors', [])
        final_conveyor = conveyors[-1] if conveyors else ''
        endpoint_sensor = self._ENDPOINT_SENSORS.get(final_conveyor, '')

        for sid in route_sensors:
            is_active = proximity.get(sid, False)
            if sid == endpoint_sensor:
                timeouts[sid] = self._calc_endpoint_timeout(final_conveyor, ctx.target_bin or '')
            else:
                timeouts[sid] = self._HOPPER_BELT_TIMEOUTS.get((route_id, sid), 30.0)

            if is_active:
                timers.pop(sid, None)
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
        from controllers.plc_runtime.actuator import compute_emergency_stop_commands
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

    def _on_belt_active(self, belt_id: str, active: bool):
        """UI点击皮带按钮 → 强制启动该皮带调度"""
        if active and belt_id in ('D6', 'D7', 'D8', 'D9'):
            print(f"[FM-Sched] {belt_id} 启动调度", flush=True)
            self.scheduler.request_schedule_now(belt_id)

    def _resolve_clearing_strategy(self, route_id: str) -> str:
        """根据缓存序列中下一同列料仓确定清空策略(AI纯仿真逻辑)"""
        ctx = self.route_manager.get_route_context(route_id)
        if not ctx or not ctx.target_bin:
            return 'reverse'
        if ctx.assigned_cart == 'Cart4':
            return 'column_switch'
        cart_to_belt = {'Cart1': 'D7', 'Cart2': 'D8', 'Cart3': 'D9'}
        belt_id = cart_to_belt.get(ctx.assigned_cart, '')
        if not belt_id:
            return 'reverse'
        seq = list(self.scheduler._sequences.get(belt_id, []))
        if not seq:
            return 'reverse'
        cur_col = ctx.target_bin.split('-')[0]
        cur_row = int(ctx.target_bin.split('-')[1])
        # 找序列中第一个同列仓
        same_col_next = None
        has_other_col = False
        for bid in seq:
            if bid.startswith(cur_col + '-'):
                if same_col_next is None:
                    try:
                        same_col_next = int(bid.split('-')[1])
                    except ValueError:
                        pass
            else:
                has_other_col = True
        if same_col_next is None:
            return 'column_switch' if has_other_col else 'reverse'
        if same_col_next < cur_row and cur_row >= 4:
            if ctx.assigned_hoppers:
                return 'sequential'
        return 'reverse'

    def deactivate_route(self, route_id: str):
        """停用路线"""
        self.route_manager.stop_route(route_id)
        self._active_routes.discard(route_id)

    def get_active_routes(self) -> Set[str]:
        return set(self._active_routes)
