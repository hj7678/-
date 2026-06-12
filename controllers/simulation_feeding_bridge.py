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

    def tick(self):
        """每帧: 推送料位→Stock, 推送传感器→FeedingMaster"""
        if not self._enabled:
            return

        ctrl = self._ctrl

        # 推送料位到 Stock Management
        levels = {}
        for bid, sb in ctrl.small_bins.items():
            levels[bid] = sb.current_level
        if levels:
            self._stock.set_levels_batch(levels)

        # 推送传感器状态到 FeedingMaster
        sensor_data = {
            "proximity": {sid: s.is_active for sid, s in ctrl.sensors.items()},
            "hopper_states": {hid: h.is_open for hid, h in ctrl.hoppers.items()},
            "hopper_weights": {hid: h.get_display_weight() for hid, h in ctrl.hoppers.items()},
            "cart_positions": dict(ctrl.cart_positions),
            "cart_divert": {cid: list(div) for cid, div in ctrl.cart_divert.items()},
            "belt_states": {cid: conv.is_running for cid, conv in ctrl.conveyors.items()},
            "belt_speeds": {cid: conv.current_speed for cid, conv in ctrl.conveyors.items()},
            "active_routes": list(ctrl.active_routes),
            "route_states": ctrl.route_state_manager.get_all_route_states(),
        }
        self._fm.send_sensor_states(sensor_data)

    def _on_commands(self, commands: List[dict]):
        self.command_received.emit(commands)

    def apply_commands(self, commands: List[dict]):
        ctrl = self._ctrl
        for cmd in commands:
            device = cmd.get("device", "")
            dev_id = cmd.get("id", "")
            action = cmd.get("action", "")

            if device == "belt":
                conv = ctrl.conveyors.get(dev_id)
                if conv:
                    if action == "start":
                        conv.start(ctrl.speed)
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
                    if target is not None and dev_id in ctrl.cart_positions:
                        ctrl.cart_positions[dev_id] = target
