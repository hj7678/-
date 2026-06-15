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
        self._cart_divert = {
            k: tuple(v) for k, v in data.get('cart_divert', {}).items()
        }
        self.scheduler.update_cart_state(self._cart_positions, self._cart_divert)

        # 同步活跃路线: 仿真激活了哪些路线，FeedingMaster 就追踪哪些
        sim_active = set(data.get('active_routes', []))
        sim_states = data.get('route_states', {})

        # 新激活的路线: 从桥接数据同步状态和目标料仓
        route_targets = data.get('route_targets', {})
        for route_id in sim_active - self._active_routes:
            ctx = self.route_manager.get_route_context(route_id)
            target = route_targets.get(route_id, '')
            state_str = sim_states.get(route_id, 'idle') if isinstance(sim_states, dict) else 'idle'

            if target and ctx:
                ctx.target_bin = target
                if state_str != 'idle':
                    # 同步仿真当前状态
                    try:
                        new_state = RouteState(state_str)
                        self.route_manager._transition(ctx, new_state)
                    except ValueError:
                        pass

            self._active_routes.add(route_id)
            print(f"[FeedingMaster] 路线 {route_id} [{state_str}]" +
                  (f" → {target}" if target else "") + " 已同步", flush=True)

        # 仿真已停用的路线
        for route_id in self._active_routes - sim_active:
            self._active_routes.discard(route_id)

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

        # 心跳日志 (每2秒)
        tick_count = getattr(self, '_tick_count', 0) + 1
        self._tick_count = tick_count
        do_heartbeat = (tick_count % 40 == 0)  # 50ms*40=2s

        # 2. 遍历活跃路线，执行状态机
        commands = []
        route_summaries = []
        for route_id in list(self._active_routes):
            ctx = self.route_manager.get_route_context(route_id)
            if not ctx:
                continue

            cart_id = ctx.assigned_cart or ''
            cart_pos = self._cart_positions.get(cart_id, 1)
            cart_target = ctx.cart_target_position
            target_bin = ctx.target_bin or ''

            # 读取料位
            level = 0.0
            b = level_map.get(target_bin, {})
            if b:
                level = b.get('level_pct', 0)

            # 进入 FEEDING 时确定清空策略
            strategy = getattr(ctx, 'clearing_strategy', 'reverse')
            if ctx.state == RouteState.FEEDING and strategy == 'reverse':
                strategy = self._resolve_clearing_strategy(route_id)
                ctx.clearing_strategy = strategy
                if strategy != 'reverse':
                    print(f"[FeedingMaster] {route_id} 清空策略={strategy}", flush=True)

            # 状态引擎判定
            next_state, actions = self.state_engine.evaluate(
                route_id, ctx.state,
                level_sensors={'__target__': level},
                cart_sensor={cart_id: cart_pos} if cart_id else {},
                cart_target=cart_target,
                cart_moving=ctx.cart_moving,
                cart=cart_id,
                clearing_strategy=strategy,
                current_time=self._total_runtime,
            )

            # 收集摘要（使用已确定的 strategy 而非 getattr）
            threshold = {'sequential': 98, 'reverse': 95, 'column_switch': 92}.get(strategy, 95)
            if cart_id == 'Cart3':
                threshold = 94
            route_summaries.append(
                f"  {route_id} {ctx.state.value}/{strategy} {target_bin}={level:.0f}% "
                f"(阈值{threshold}%) cart={cart_id}@{cart_pos}"
            )

            # 状态变更
            if next_state != ctx.state:
                old = ctx.state
                self.route_manager.set_route_state(route_id, next_state)
                reason = ""
                if old.value == 'feeding' and next_state.value == 'clearing':
                    reason = f" — 料位 {level:.0f}% ≥ {threshold}%"
                elif old.value == 'moving_to_target':
                    reason = f" — 小车到达位置 {cart_pos}"
                print(f"[FeedingMaster] {route_id}: {old.value} → {next_state.value}{reason}", flush=True)

                # 路线完成 → 执行序列下一仓
                if next_state.value in ('waiting', 'standby'):
                    belt_id = CART_TO_BELT.get(cart_id, '')
                    self.scheduler.mark_completed(belt_id)
                    nxt = self.scheduler.get_next_bin(belt_id)
                    if nxt:
                        self.scheduler.pop_next_bin(belt_id)
                        route_id2 = self._pick_route_for_bin(belt_id, nxt)
                        if route_id2:
                            if self.activate_route(route_id2, nxt):
                                print(f"[FeedingMaster] {belt_id} 自动续 → {nxt}", flush=True)

            # 执行器命令
            route_conveyors = config.FEED_ROUTES.get(route_id, {}).get('conveyors', [])
            final_conv = route_conveyors[-1] if route_conveyors else ''
            hoppers = ctx.assigned_hoppers
            cart_at_target = not should_move_cart(cart_pos, cart_target)

            if ctx.state in (RouteState.FEEDING, RouteState.CLEARING):
                belt_cmds = compute_route_belt_commands(
                    route_conveyors, final_conv,
                    is_feeding=(ctx.state == RouteState.FEEDING),
                    is_clearing=(ctx.state == RouteState.CLEARING),
                    cart_at_target=cart_at_target,
                )
                for cid, action in belt_cmds.items():
                    commands.append({
                        "device": "belt", "id": cid,
                        "action": action.value,
                    })

                hopper_cmds = compute_hopper_commands(
                    hoppers,
                    is_feeding=(ctx.state == RouteState.FEEDING),
                    cart_at_target=cart_at_target,
                    hopper_states={},
                )
                for hid, action in hopper_cmds.items():
                    commands.append({
                        "device": "hopper", "id": hid,
                        "action": action.value,
                    })

            # 小车目标位置
            if cart_id:
                if cart_id == 'Cart4':
                    target = compute_cart4_target_position(target_bin)
                else:
                    target = compute_cart_target_position(target_bin, cart_id)
                if target is not None and should_move_cart(cart_pos, target):
                    commands.append({
                        "device": "cart", "id": cart_id,
                        "action": "move", "target": target,
                    })

        # 3. 心跳日志
        if do_heartbeat and route_summaries:
            n_cmds = len(commands)
            print(f"[FeedingMaster] ── 心跳 (tick={tick_count}) ──", flush=True)
            for s in route_summaries:
                print(s, flush=True)
            if n_cmds > 0:
                actions = set(c['action'] for c in commands)
                print(f"  → 指令: {n_cmds}条 ({', '.join(sorted(actions))})", flush=True)

        # 4. 调度引擎联动
        self.scheduler.tick(self._total_runtime)

        # 5. 推送控制指令
        if commands:
            self.server.send_commands(commands)

    # ── 外部接口 ──

    def activate_route(self, route_id: str, target_bin: str):
        """激活一条路线"""
        ok = self.route_manager.start_route(route_id, target_bin)
        if ok:
            self._active_routes.add(route_id)
            belt_id = CART_TO_BELT.get(
                self.route_manager.ROUTE_CARTS.get(route_id, ''), '')
            self.scheduler.mark_executing(belt_id, route_id, target_bin)
            print(f"[FeedingMaster] 路线 {route_id} → {target_bin} 已激活", flush=True)
        return ok

    def _on_schedule_sequence(self, belt_id: str, sequence: list):
        """收到调度序列 → 若皮带空闲则自动启动"""
        if self.scheduler.is_executing(belt_id):
            return  # 正在执行中, 序列已缓存等下次使用

        # 选第一条执行
        first_bin = sequence[0] if sequence else None
        if not first_bin:
            return

        route_id = self._pick_route_for_bin(belt_id, first_bin)
        if not route_id:
            return

        self.scheduler.pop_next_bin(belt_id)
        if self.activate_route(route_id, first_bin):
            print(f"[FeedingMaster] {belt_id} → {first_bin} ({route_id})", flush=True)

    def _pick_route_for_bin(self, belt_id: str, bin_id: str) -> Optional[str]:
        """根据料仓ID选择路线（复用仿真侧的 BIN_TO_AVAILABLE_ROUTES）"""
        if belt_id == 'D6':
            return 'route5'

        available = config.BIN_TO_AVAILABLE_ROUTES.get(bin_id, [])
        if not available:
            return None

        # 优先选第一条可用路线
        prefix = bin_id.split('-')[0]
        priority_map = config.FEED_POINT_PRIORITY.get(prefix, {})

        candidates = []
        for feed_point, route_id in available:
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

    def deactivate_route(self, route_id: str):
        """停用路线"""
        self.route_manager.stop_route(route_id)
        self._active_routes.discard(route_id)

    def get_active_routes(self) -> Set[str]:
        return set(self._active_routes)
