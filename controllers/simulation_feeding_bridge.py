"""
仿真-FeedingMaster 桥接模块

将仿真系统的传感器状态发送给 FeedingMaster，接收控制指令并执行。

双模式:
  - 桥接模式 (bridge_enabled=True): 传感器状态 → FeedingMaster → 控制指令 → 仿真执行
  - 独立模式 (bridge_enabled=False): 仿真内部闭环，不使用 FeedingMaster

用法:
  bridge = SimulationFeedingBridge(controller)
  bridge.start()   # 连接到 FeedingMaster + Stock Management
  # 在 update() 中:
  bridge.tick()    # 收集状态 → 发送 → 接收指令 → 执行
"""
import threading
import time
from typing import Optional, Dict, List

from PyQt5.QtCore import QObject, pyqtSignal
from controllers.upper_computer.feedingmaster_client import FeedingMasterClient
from controllers.upper_computer.stock_client import StockClient as UpperStockClient
import config


class SimulationFeedingBridge(QObject):
    """仿真 ↔ FeedingMaster 桥接器"""

    # 信号
    command_received = pyqtSignal(list)   # 收到控制指令 [{device, id, action, ...}]
    connection_changed = pyqtSignal(bool)  # FeedingMaster 连接状态变化
    stock_updated = pyqtSignal(list)       # 料位数据更新 [{bin_id, level_tons, ...}]

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._ctrl = controller  # SimulationController 引用
        self._fm = FeedingMasterClient()
        self._stock = UpperStockClient()
        self._enabled = False
        self._stock_thread: Optional[threading.Thread] = None

        # 注册回调
        self._fm.on_commands(self._on_commands)

    @property
    def is_connected(self) -> bool:
        return self._fm._running if hasattr(self._fm, '_running') else False

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        if enabled:
            self._connect()
        else:
            self._fm.disconnect()

    def start(self):
        """启动桥接 (连接 FeedingMaster)"""
        self._enabled = True
        self._connect()
        self._start_stock_polling()

    def stop(self):
        self._enabled = False
        self._fm.disconnect()
        self._stock.disconnect()

    def _connect(self):
        self._stock.connect()
        ok = self._fm.connect()
        self.connection_changed.emit(ok)

    def _start_stock_polling(self):
        """后台线程定期拉取料位数据"""
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

    def tick(self):
        """每帧调用: 收集仿真状态 → 发送给 FeedingMaster"""
        if not self._enabled:
            return

        ctrl = self._ctrl

        # 收集传感器状态
        sensor_data = {
            "proximity": {
                sid: s.is_active
                for sid, s in ctrl.sensors.items()
            },
            "hopper_states": {
                hid: h.is_open
                for hid, h in ctrl.hoppers.items()
            },
            "hopper_weights": {
                hid: h.get_display_weight()
                for hid, h in ctrl.hoppers.items()
            },
            "cart_positions": dict(ctrl.cart_positions),
            "cart_divert": {
                cid: list(div) for cid, div in ctrl.cart_divert.items()
            },
            "belt_states": {
                cid: conv.is_running
                for cid, conv in ctrl.conveyors.items()
            },
            "belt_speeds": {
                cid: conv.current_speed
                for cid, conv in ctrl.conveyors.items()
            },
            "active_routes": list(ctrl.active_routes),
            "route_states": ctrl.route_state_manager.get_all_route_states(),
        }
        self._fm.send_sensor_states(sensor_data)

    def _on_commands(self, commands: List[dict]):
        """收到 FeedingMaster 的控制指令，转发给仿真执行"""
        self.command_received.emit(commands)

    def apply_commands(self, commands: List[dict]):
        """将控制指令应用到仿真对象"""
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
