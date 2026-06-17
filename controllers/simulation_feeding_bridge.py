"""
仿真-FeedingMaster 桥接模块

数据流:
  仿真 small_bins 料位 → PUSH → Stock Management (数据中转站)
  仿真传感器状态     → PUSH → FeedingMaster  (控制大脑)
  FeedingMaster 指令 ← PULL ← 应用到仿真对象

用法:
  bridge = SimulationFeedingBridge(controller)
  bridge.start()
  # update() 中: bridge.tick()
"""
import threading
import time
from typing import Optional, Dict, List

from PyQt5.QtCore import QObject, pyqtSignal
from controllers.upper_computer.feedingmaster_client import FeedingMasterClient
from controllers.upper_computer.stock_client import StockClient as UpperStockClient
import config


class SimulationFeedingBridge(QObject):
    """仿真 ↔ 外部模块桥接器"""

    command_received = pyqtSignal(list)
    stock_updated = pyqtSignal(list)   # 从 Stock 拉回的料位数据

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._ctrl = controller
        self._fm = FeedingMasterClient()
        self._stock = UpperStockClient()
        self._enabled = False
        self._stock_thread: Optional[threading.Thread] = None
        self._last_push = 0.0  # 上次推送时间戳

        self._fm.on_commands(self._on_commands)

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        if enabled:
            self._connect()
        else:
            self._fm.disconnect()
            self._stock.disconnect()

    def start(self):
        self._enabled = True
        self._connect()
        self._start_stock_polling()

    def stop(self):
        self._enabled = False
        self._fm.disconnect()
        self._stock.disconnect()

    def _start_stock_polling(self):
        """后台线程从 Stock 拉取料位 → 更新 HMI 显示"""
        def _poll():
            while self._enabled:
                try:
                    levels = self._stock.get_all_levels()
                    if levels:
                        self.stock_updated.emit(levels)
                except Exception:
                    pass
                time.sleep(1.0)
        self._stock_thread = threading.Thread(target=_poll, daemon=True)
        self._stock_thread.start()

    def _connect(self):
        self._stock.connect()
        self._fm.connect()

    def randomize_stock_levels(self, lo_pct: float = 25.0, hi_pct: float = 90.0):
        self._stock.randomize_all(lo_pct, hi_pct)

    def send_manual_start(self, bin_id: str, route_id: str):
        """手动上料: 通知FM激活指定路线"""
        self._fm._send({"type": "manual_start", "bin_id": bin_id, "route_id": route_id})

    def send_manual_stop(self, route_id: str):
        """手动停止: 通知FM停用路线"""
        self._fm._send({"type": "manual_stop", "route_id": route_id})

    def tick(self):
        """每帧: 推送料位→Stock, 推送传感器→FeedingMaster"""
        if not self._enabled:
            return

        ctrl = self._ctrl

        # 限频: FM接管时100ms, 监控时500ms
        now = time.time()
        interval = 0.1 if self._ctrl._use_feeding_master else 0.5
        if now - self._last_push < interval:
            return
        self._last_push = now

        # 推送料位到 Stock Management (配料站 + 高位仓)
        levels = {}
        for bid, sb in ctrl.small_bins.items():
            levels[bid] = sb.current_level
        # 高位仓 S1-S12
        if hasattr(ctrl, 'view') and ctrl.view:
            for sid, silo in ctrl.view.silo_compartments.items():
                cur = silo.get('current_level', 0)
                levels[sid] = cur
        if levels:
            self._stock.set_levels_batch(levels)
        # 消耗速率每60秒同步一次 (变化不频繁)
        if now - getattr(self, '_last_rate_push', 0) > 60:
            self._last_rate_push = now
            rates = {bid: sb.consumption_rate for bid, sb in ctrl.small_bins.items()}
            self._stock.set_consumption_rates_batch(rates)

        # 推送传感器状态到 FeedingMaster
        sensor_data = {
            "proximity": {sid: s.is_active for sid, s in ctrl.sensors.items()},
            "hopper_states": {hid: h.is_open for hid, h in ctrl.hoppers.items()},
            "hopper_weights": {hid: h.get_display_weight() for hid, h in ctrl.hoppers.items()},
            "cart_positions": dict(ctrl.cart_positions),
            "cart_divert": {cid: list(div) for cid, div in ctrl.cart_divert.items()},
            "belt_states": {cid: conv.is_running for cid, conv in ctrl.conveyors.items()},
            "belt_speeds": {cid: conv.current_speed for cid, conv in ctrl.conveyors.items()},
            "cart4_position": ctrl.cart4_position,
            "cart4_is_moving": ctrl.cart4_is_moving,
            "active_routes": list(ctrl.active_routes),
            "route_states": ctrl.route_state_manager.get_all_route_states(),
            "scheduling_active": ctrl._auto_feeding_active,
            "route_targets": dict(ctrl.route_to_bin),
            "route_cart_moving": {
                rid: (ctx.cart_moving if (ctx := ctrl.route_state_manager.get_route_context(rid)) else False)
                for rid in ctrl.active_routes
            },
        }
        self._fm.send_sensor_states(sensor_data)

    def _on_commands(self, msg):
        """接收命令 (含路线状态) from FeedingMaster"""
        if isinstance(msg, list):
            commands = msg
            route_states = {}
            schedule = {}
        else:
            commands = msg.get('commands', [])
            route_states = msg.get('route_states', {})
            schedule = msg.get('schedule', {})
        # 路线状态同步推迟到主线程 apply_commands 中处理
        self._pending_route_states = route_states
        # 调度序列同步到仿真 (HMI显示用)
        if schedule:
            sd = schedule
            if hasattr(self._ctrl, '_executing_bin'):
                self._ctrl._executing_bin.update(sd.get('executing_bin', {}))
            if hasattr(self._ctrl, '_scheduled_sequence'):
                self._ctrl._scheduled_sequence.update(sd.get('sequences', {}))
        # 操作日志: 写入belt_log让HMI显示
        oplog = msg.get('operation_log', [])
        if oplog:
            from belt_logger import belt_log as _bl
            belt_map = {'route1': 'D7', 'route2': 'D7', 'route3': 'D7',
                        'route4': 'D9', 'route5': 'D6',
                        'route6': 'D8', 'route7': 'D9', 'route8': 'D8'}
            for entry in oplog:
                rid = entry.get('route_id', '')
                bid = belt_map.get(rid, '')
                if bid:
                    _bl(bid).info(entry.get('msg', ''))
        self.command_received.emit(commands)

    def apply_commands(self, commands: List[dict]):
        ctrl = self._ctrl
        # FM状态同步到仿真 (FM是权威)
        rs = getattr(self, '_pending_route_states', {})
        if rs:
            self._pending_route_states = {}
            from controllers.route_state_manager import RouteState
            for rid, info in rs.items():
                ctx = ctrl.route_state_manager.get_route_context(rid)
                if not ctx: continue
                try:
                    new_s = RouteState(info.get('state', '')) if isinstance(info, dict) else None
                    if new_s and new_s != ctx.state and new_s != RouteState.MOVING_TO_TARGET:
                        ctrl.route_state_manager._transition(ctx, new_s)
                    if new_s and new_s != RouteState.IDLE:
                        ctrl.active_routes.add(rid)
                except: pass
                if isinstance(info, dict):
                    if info.get('target_bin'): ctx.target_bin = info['target_bin']; ctrl.route_to_bin[rid] = info['target_bin']
                    if info.get('cart_target'): ctx.cart_target_position = info['cart_target']
                    ctx.cart_moving = info.get('cart_moving', False)
        for cmd in commands:
            device = cmd.get("device", "")
            dev_id = cmd.get("id", "")
            action = cmd.get("action", "")

            if device == "belt":
                conv = ctrl.conveyors.get(dev_id)
                if conv:
                    if action == "start":
                        conv.start(ctrl.speed)
                        if not ctrl.is_running:
                            ctrl.is_running = True
                            ctrl._runtime_timer.restart()
                            ctrl._last_runtime_ms = 0
                        if not ctrl.feed_timer.isActive():
                            ctrl.feed_timer.start(ctrl.feed_interval)
                    elif action == "stop":
                        conv.stop()

            elif device == "hopper":
                hopper = ctrl.hoppers.get(dev_id)
                if hopper:
                    if action == "open":
                        hopper.is_open = True
                    elif action == "close":
                        hopper.is_open = False

            elif device == "cart":
                if action == "move":
                    target = cmd.get("target")
                    if target is not None:
                        if dev_id == 'Cart4':
                            if ctrl.cart4_position != target:
                                ctrl.cart4_target_position = target
                                ctrl.cart4_is_moving = True
                            else:
                                ctrl.cart4_is_moving = False
                        else:
                            ctrl.cart_target_positions[dev_id] = target
                        route_id = cmd.get("route_id")
                        if route_id:
                            ctx = ctrl.route_state_manager.get_route_context(route_id)
                            if ctx:
                                ctx.cart_moving = True
                                ctx.cart_target_position = target
        ctrl.mark_dirty()  # 通知UI刷新
