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
                except Exception as e:
                    # Stock 暂时不可用，静默等待下次重试
                    time.sleep(5.0)  # 连接失败时延长等待避免频繁重试
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

        # 自动重连 (每3秒尝试一次, 避免阻塞tick)
        now = time.time()
        if not self._fm.is_connected():
            if now - getattr(self, '_last_reconnect_attempt', 0) > 3.0:
                self._last_reconnect_attempt = now
                self._fm.ensure_connected()

        ctrl = self._ctrl

        # 限频: FM 接管时 100ms
        now = time.time()
        interval = 0.1
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
        # 故障覆盖(最高优先级): 故障模拟注入的传感器值
        fault_overrides = {}
        if hasattr(ctrl, 'control_strategy_generator'):
            fault_overrides = getattr(ctrl.control_strategy_generator, 'fault_overrides', {})

        sensor_data = {
            "proximity": {sid: fault_overrides.get(sid, s.is_active) for sid, s in ctrl.sensors.items()},
            "hopper_states": {hid: h.is_open for hid, h in ctrl.hoppers.items()},
            "hopper_weights": {hid: h.get_display_weight() for hid, h in ctrl.hoppers.items()},
            "cart_positions": {
                'Cart1': ctrl.cart_positions.get('Cart1', 1),
                'Cart2': ctrl.cart_positions.get('Cart2', 1),
                'Cart3': ctrl.cart_positions.get('Cart3', 1),
                'Cart4': ctrl.cart4_position,
            },
            "cart_divert": {
                'Cart1': list(ctrl.cart_divert.get('Cart1', (True, False))),
                'Cart2': list(ctrl.cart_divert.get('Cart2', (True, False))),
                'Cart3': list(ctrl.cart_divert.get('Cart3', (False, True))),
                'Cart4': _cart4_divert(ctrl),
            },
            "cart_limits": {
                'Cart1': [ctrl.cart_sensor_positions.get('Cart1', 1) == 1,
                          ctrl.cart_sensor_positions.get('Cart1', 1) == 7],
                'Cart2': [ctrl.cart_sensor_positions.get('Cart2', 1) == 1,
                          ctrl.cart_sensor_positions.get('Cart2', 1) == 7],
                'Cart3': [ctrl.cart_sensor_positions.get('Cart3', 1) == 1,
                          ctrl.cart_sensor_positions.get('Cart3', 1) == 7],
                'Cart4': [ctrl.cart4_position == 1,
                          ctrl.cart4_position == 6],
            },
            "cart_moving": {
                'Cart1': getattr(ctrl, '_cart1_is_moving', False),
                'Cart2': getattr(ctrl, '_cart2_is_moving', False),
                'Cart3': getattr(ctrl, '_cart3_is_moving', False),
                'Cart4': ctrl.cart4_is_moving,
            },
            "belt_states": {cid: conv.is_running for cid, conv in ctrl.conveyors.items()},
            "belt_speeds": {cid: conv.current_speed for cid, conv in ctrl.conveyors.items()},
            "active_routes": list(ctrl.active_routes),
            "route_states": ctrl.route_state_manager.get_all_route_states(),
            "scheduling_active": ctrl._auto_feeding_active,
            "route_targets": dict(ctrl.route_to_bin),
            "d7_feed_override": getattr(ctrl, '_d7_feed_override', ''),
            "laser_sensor_states": dict(ctrl.laser_sensor_states) if hasattr(ctrl, 'laser_sensor_states') else {},
            "maintenance_bins": list(ctrl.get_maintenance_bins()) if hasattr(ctrl, 'get_maintenance_bins') else [],
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
            # 消息序列号检测丢包
            seq = msg.get('seq')
            if seq is not None:
                last_seq = getattr(self, '_last_seq', 0)
                if last_seq > 0 and seq > last_seq + 1:
                    print(f"[桥接] ⚠ 检测到丢包: seq {last_seq}→{seq} (跳过 {seq - last_seq - 1} 条)", flush=True)
                self._last_seq = seq
        # 路线状态同步推迟到主线程 apply_commands 中处理
        self._pending_route_states = route_states
        # 调度序列同步到仿真 (HMI显示用)
        if schedule:
            sd = schedule
            if hasattr(self._ctrl, '_executing_bin'):
                self._ctrl._executing_bin.clear()
                self._ctrl._executing_bin.update(sd.get('executing_bin', {}))
            if hasattr(self._ctrl, '_scheduled_sequence'):
                self._ctrl._scheduled_sequence.clear()
                self._ctrl._scheduled_sequence.update(sd.get('sequences', {}))
        # 故障诊断结果转发到仿真
        diag = msg.get('diagnosis', None)
        if hasattr(self._ctrl, 'set_diagnosis_results'):
            self._ctrl.set_diagnosis_results(diag if diag else [])
        self.command_received.emit(commands)

    def apply_commands(self, commands: List[dict]):
        ctrl = self._ctrl
        # FM状态同步到仿真 (FM是权威，直接更新RouteContext字段)
        rs = getattr(self, '_pending_route_states', {})
        if rs:
            self._pending_route_states = {}
            from controllers.route_state_manager import RouteState
            for rid, info in rs.items():
                ctx = ctrl.route_state_manager.get_route_context(rid)
                if not ctx: continue
                try:
                    if isinstance(info, dict):
                        # 直接用 FM 数据更新 RouteContext，不再通过状态机
                        new_s = RouteState(info.get('state', '')) if info.get('state') else None
                        if new_s is not None:
                            ctx.state = new_s
                        if info.get('target_bin'):
                            ctx.target_bin = info['target_bin']
                            ctrl.route_to_bin[rid] = info['target_bin']
                        if info.get('cart_target') is not None:
                            ctx.cart_target_position = info['cart_target']
                        ctx.cart_moving = info.get('cart_moving', False)
                        if info.get('clearing_strategy'):
                            ctx.clearing_strategy = info['clearing_strategy']
                        ctx.early_moved_from_clearing = info.get('early_moved', False)
                        if info.get('assigned_cart'):
                            ctx.assigned_cart = info['assigned_cart']
                        if info.get('assigned_hoppers'):
                            ctx.assigned_hoppers = info['assigned_hoppers']
                        if info.get('feeding_start_time'):
                            ctx.feeding_start_time = info['feeding_start_time']
                        if info.get('clearing_start_time'):
                            ctx.clearing_start_time = info['clearing_start_time']
                        # 活跃路线管理
                        if new_s and new_s not in (RouteState.IDLE, RouteState.STANDBY):
                            ctrl.active_routes.add(rid)
                        elif new_s:
                            ctrl.active_routes.discard(rid)
                except Exception as e:
                    print(f"[桥接-状态] {rid} 同步失败: {e}", flush=True)
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

            elif device == "feed_point":
                if action in ("start", "on"):
                    ctrl.set_feed_point_active(cmd["id"], True)
                elif action in ("stop", "off"):
                    ctrl.set_feed_point_active(cmd["id"], False)

            elif device == "cart":
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
                            if dev_id == 'Cart1': ctrl._cart1_is_moving = (ctrl.cart_positions.get('Cart1', 1) != target)
                            if dev_id == 'Cart2': ctrl._cart2_is_moving = (ctrl.cart_positions.get('Cart2', 1) != target)
                            if dev_id == 'Cart3': ctrl._cart3_is_moving = (ctrl.cart_positions.get('Cart3', 1) != target)
                        route_id = cmd.get("route_id")
                        if route_id:
                            ctx = ctrl.route_state_manager.get_route_context(route_id)
                            if ctx:
                                ctx.cart_moving = True
                                ctx.cart_target_position = target
                    # 同步分料方向：FM命令中携带的分料状态
                    left_div = cmd.get("left_divert")
                    right_div = cmd.get("right_divert")
                    if left_div is not None and right_div is not None:
                        ctrl.cart_divert[dev_id] = (left_div, right_div)
                        # 同步写入传感器数据管理器，确保TCP诊断服务也能看到
                        ctrl.sensor_data_manager.write_cart_left_divert(dev_id, left_div)
                        ctrl.sensor_data_manager.write_cart_right_divert(dev_id, right_div)
        ctrl.mark_dirty()  # 通知UI刷新


def _cart4_divert(ctrl) -> list:
    """Cart4分料: 左=S1~S6, 右=S7~S12"""
    ctx = ctrl.route_state_manager.get_route_context('route5')
    if not ctx or not ctx.target_bin:
        return [True, False]  # 默认左分料
    tb = ctx.target_bin
    if tb.startswith('S') and tb[1:].isdigit():
        n = int(tb[1:])
        if 1 <= n <= 6:
            return [True, False]
        elif 7 <= n <= 12:
            return [False, True]
    return [True, False]
