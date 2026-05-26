"""
主窗口 - Main Window
搅拌站上料系统仿真软件
"""

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QStatusBar, QMenuBar, QMenu, QAction, QToolBar,
                             QMessageBox, QSizePolicy, QLabel, QScrollArea)
from PyQt5.QtCore import Qt, QTimer, QElapsedTimer
from PyQt5.QtGui import QKeySequence

import config
import styles
from views import SimulationView, ControlPanel, StatusPanel
from views.feed_point_select_dialog import FeedPointSelectDialog
from views.operation_log_panel import OperationLogPanel
from views.status_data import collect_status_data
from controllers import SimulationController
from utils.logger import get_logger

ROUTE_TO_BELT = {
    'route1': 'D7', 'route2': 'D7', 'route3': 'D7',
    'route4': 'D9', 'route6': 'D9', 'route8': 'D9',
    'route5': 'D6',
    'route7': 'D8', 'route9': 'D8',
}


class MainWindow(QMainWindow):
    """主窗口类"""

    def __init__(self):
        super().__init__()

        # 标题和窗口大小
        self.setWindowTitle("搅拌站后料场上料系统仿真软件 v1.0")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 850)

        # 控制器
        self.controller = SimulationController()

        self.logger = get_logger()

        # 初始化UI
        self._init_ui()

        # 连接信号
        self._connect_signals()

        # 仿真更新计时器 - 50ms 间隔（约20FPS）
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_simulation)
        self.update_timer.start(50)

        # 使用高精度计时器计算实际经过时间
        self._elapsed_timer = QElapsedTimer()
        self._elapsed_timer.start()
        self._last_update_ms = 0  # 上一次的时间戳（毫秒）

        self.logger.info("仿真软件启动")

    def _init_ui(self):
        """初始化UI"""
        self.setPalette(styles.get_dark_palette())
        self.setStyleSheet(styles.get_scrollbar_style())

        # 菜单栏
        self._create_menu_bar()

        # 工具栏
        self._create_toolbar()

        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ========== 左侧控制面板 ==========
        left_panel = QWidget()
        left_panel.setMinimumWidth(250)
        left_panel.setMaximumWidth(280)
        left_panel.setStyleSheet(f"""
            QWidget {{
                background-color: {config.COLORS['panel']};
                border: 1px solid {config.COLORS['panel_border']};
                border-radius: 8px;
            }}
        """)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # 使用滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background-color: #21262D;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #484F58;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #6E7681;
            }
        """)

        self.control_panel = ControlPanel()
        self.control_panel._controller = self.controller  # 用于小车4控制
        scroll_area.setWidget(self.control_panel)

        left_layout.addWidget(scroll_area)

        main_layout.addWidget(left_panel)

        # ========== 中间仿真视图 + 运行日志 ==========
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(6)

        self.simulation_view = SimulationView()
        self.simulation_view.set_simulator(self.controller)
        self.simulation_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        center_layout.addWidget(self.simulation_view, 1)

        self.operation_log = OperationLogPanel()
        center_layout.addWidget(self.operation_log)

        main_layout.addWidget(center_widget, 1)

        # 设置controller的view引用（用于计算放料位置）
        self.controller.view = self.simulation_view

        # 在view设置后，重新加载料位数据
        self.controller._load_initial_levels()

        # ========== 右侧状态面板 ==========
        right_panel = QWidget()
        right_panel.setMinimumWidth(350)
        right_panel.setMaximumWidth(400)
        right_panel.setStyleSheet(f"""
            QWidget {{
                background-color: {config.COLORS['panel']};
                border: 1px solid {config.COLORS['panel_border']};
                border-radius: 8px;
            }}
        """)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)

        # 状态监控标题
        status_title = QLabel("状态监控")
        status_title.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: #2ECC71;
                padding: 5px;
                border-bottom: 2px solid #2ECC71;
            }
        """)
        right_layout.addWidget(status_title)

        # 状态监控面板
        self.status_panel = StatusPanel()
        right_layout.addWidget(self.status_panel, 1)

        main_layout.addWidget(right_panel)

        # 状态栏
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet("""
            QStatusBar {
                background-color: #161b22;
                color: #8B949E;
                border-top: 1px solid #30363d;
            }
        """)
        self.setStatusBar(self.status_bar)
        self._update_status_bar("就绪 - 请选择上料路线开始仿真")

    def _create_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        menubar.setStyleSheet(styles.get_menu_style())

        # 文件菜单
        file_menu = menubar.addMenu("文件")
        export_action = QAction("导出日志...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._on_export_log)
        file_menu.addAction(export_action)
        file_menu.addSeparator()
        exit_action = QAction("退出", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 仿真菜单（移除"启动全部路线"和"紧急停止"）
        sim_menu = menubar.addMenu("仿真")
        reset_action = QAction("系统复位", self)
        reset_action.setShortcut(QKeySequence("Ctrl+R"))
        reset_action.triggered.connect(self._on_reset_simulation)
        sim_menu.addAction(reset_action)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _create_toolbar(self):
        """创建工具栏（移除启动全部、停止全部、急停按钮）"""
        toolbar = QToolBar()
        toolbar.setStyleSheet(styles.get_toolbar_style())
        self.addToolBar(toolbar)

        reset_action = QAction("复位", self)
        reset_action.triggered.connect(self._on_reset_simulation)
        toolbar.addAction(reset_action)

    def _connect_signals(self):
        """连接信号"""
        # 控制面板信号
        self.control_panel.route_toggled.connect(self._on_route_toggled)
        self.control_panel.route_bin_selected.connect(self._on_route_bin_selected)
        self.control_panel.route_silo_bin_selected.connect(self._on_route_silo_bin_selected)
        self.control_panel.speed_changed.connect(self._on_speed_changed)
        self.control_panel.reset_requested.connect(self._on_reset_simulation)
        self.control_panel.fault_config_changed.connect(self._on_fault_config_changed)
        self.control_panel.conveyor_fault_changed.connect(self._on_conveyor_fault_changed)
        self.control_panel.laser_sensor_changed.connect(self._on_laser_sensor_changed)
        self.control_panel.bin_levels_uniform_requested.connect(self._on_bin_levels_uniform)
        self.control_panel.bin_levels_random_requested.connect(self._on_bin_levels_random)
        self.control_panel.consumption_uniform_requested.connect(self._on_consumption_uniform)
        self.control_panel.consumption_random_requested.connect(self._on_consumption_random)
        self.control_panel.consumption_toggled.connect(self._on_consumption_toggled)
        self.control_panel.tcp_communication_toggled.connect(self._on_tcp_communication_toggled)
        self.control_panel.udp_sender_toggled.connect(self._on_udp_sender_toggled)
        self.control_panel.diagnosis_mode_changed.connect(self._on_diagnosis_mode_changed)
        self.control_panel.diagnosis_tcp_toggled.connect(self._on_diagnosis_tcp_toggled)
        self.control_panel.scheduling_tcp_toggled.connect(self._on_scheduling_tcp_toggled)
        self.control_panel.auto_mode_toggled.connect(self._on_auto_mode_toggled)
        self.control_panel.maintenance_line_added.connect(self._on_maintenance_line_added)
        self.control_panel.maintenance_bin_added.connect(self._on_maintenance_bin_added)
        self.control_panel.maintenance_clear_requested.connect(self._on_maintenance_clear)

        # 状态面板信号 - 中转斗开关切换 / 数据初始化
        self.status_panel.hopper_switch_toggled.connect(self._on_hopper_switch_toggled)
        self.status_panel.data_reset_requested.connect(self._on_data_reset_requested)

        # 控制器信号
        self.controller.sensor_triggered.connect(self._on_sensor_triggered)
        self.controller.alarm_raised.connect(self._on_alarm_raised)
        self.controller.material_spawned.connect(self._on_material_spawned)
        self.controller.route_started.connect(self._on_route_started)
        self.controller.route_stopped.connect(self._on_route_stopped)

        # 仿真视图信号 - 画布点击选择上料路线
        self.simulation_view.bin_clicked.connect(self._on_bin_clicked)

        # 控制器 - 路线状态变化
        self.controller.route_state_changed.connect(self._on_route_state_changed)

        # 日志内容
        self._log_sys("仿真软件启动", "#2ECC71")

    def _update_simulation(self):
        """更新仿真 - 使用实际经过的时间，不受UI事件阻塞影响"""
        # 调度数据推送独立于仿真运行状态，确保自动模式未启动仿真也能收发调度数据
        self.controller.push_scheduling_data()

        if self.controller.is_running:
            # 使用高精度计时器计算实际经过的时间（毫秒）
            current_elapsed_ms = self._elapsed_timer.elapsed()
            delta_time_ms = current_elapsed_ms - self._last_update_ms
            self._last_update_ms = current_elapsed_ms

            # 确保delta_time_ms有效（至少1ms）
            if delta_time_ms < 1:
                delta_time_ms = 1

            # 限制最大单次更新时间，防止长时间卡顿后出现异常大的跳跃
            # 但允许正常情况下累积延迟，确保仿真以真实时间运行
            delta_time_ms = min(delta_time_ms, 500)  # 最大500ms

            # 调用控制器更新（使用实际经过的时间）
            self.controller.update(delta_time_ms)

            # 仅在脏标记为真时更新UI
            if self.controller.is_dirty():
                # 更新仿真视图（重绘）
                self.simulation_view.mark_needs_repaint()
                # 更新状态面板
                self.status_panel.update_all_status(collect_status_data(self.controller))

        self._poll_tcp_status()

    def _poll_tcp_status(self):
        """轮询 TCP 诊断/调度客户端连接状态，更新 UI"""
        if hasattr(self.controller, 'get_tcp_diagnosis_status'):
            diag_connected = self.controller.get_tcp_diagnosis_status()
            self.control_panel.set_diagnosis_tcp_status(diag_connected)
        if hasattr(self.controller, 'get_tcp_scheduling_status'):
            sched_status = self.controller.get_tcp_scheduling_status()
            self.control_panel.set_scheduling_tcp_status(sched_status)
            if self.controller._auto_feeding_active:
                active_belts = [b for b, r in self.controller._executing_route.items() if r]
                if active_belts:
                    bins = [self.controller._executing_bin.get(b, '') for b in active_belts]
                    self._update_status_bar(f"自动上料中：{', '.join(bins)}")
                elif sched_status:
                    self._update_status_bar("自动上料：等待调度结果...")
                else:
                    self._update_status_bar("自动上料：等待调度服务连接...")

    def _update_status_bar(self, message: str):
        """更新状态栏"""
        self.status_bar.showMessage(message)

    def _log_sys(self, msg, color="#C0C8D0"):
        self.operation_log.add_log(msg, color)

    def _log_belt(self, route_id, msg, color="#C0C8D0"):
        belt = ROUTE_TO_BELT.get(route_id, '')
        if belt:
            self.operation_log.add_belt_log(belt, msg, color)

    # 槽函数
    def _on_route_toggled(self, route_id: str, enable: bool):
        """路线切换"""
        route_name = config.FEED_ROUTES[route_id]['name']
        ctx = self.controller.route_state_manager.get_route_context(route_id)

        if enable:
            if self.controller.is_auto_mode():
                QMessageBox.information(
                    self, "自动模式",
                    "当前为自动模式，上料操作由调度模块接管，手动操作被拦截。\n请先切换到手动模式。"
                )
                self.control_panel.route_buttons[route_id].setChecked(False)
                return

            if not self.controller.is_route_available(route_id):
                self._update_status_bar(f"{route_name} 启动失败：上料点无原料！")
                self.control_panel.route_buttons[route_id].setChecked(False)
                self._log_belt(route_id, "启动失败：上料点无原料", "#E74C3C")
                return

            success = self.controller.start_route(route_id)
            if success:
                silo_bin = self.controller.route_silo_bin.get(route_id)
                dest_bin = self.controller.route_to_bin.get(route_id)
                fp_id = ctx.feed_point if ctx else ''
                fp_name = config.FEED_POINTS.get(fp_id, {}).get('name', fp_id)

                if silo_bin and dest_bin:
                    msg = f"已启动：{fp_name}({silo_bin}) → {dest_bin}，小车移动中"
                elif dest_bin:
                    msg = f"已启动：{fp_name} → {dest_bin}，小车移动中"
                else:
                    msg = "已启动，小车移动中"
                self._log_belt(route_id, msg, "#2ECC71")
        else:
            dest_bin = self.controller.route_to_bin.get(route_id)
            self.controller.stop_route(route_id)
            if dest_bin:
                msg = f"已停止{dest_bin}上料"
            else:
                msg = "已停止"
            self._log_belt(route_id, msg, "#8B949E")

    def _get_route_detail(self, route_id: str) -> tuple:
        """获取路线详情 (route_name, feed_name, target_bin, silo_bin)"""
        route_name = config.FEED_ROUTES.get(route_id, {}).get('name', route_id)
        ctx = self.controller.route_state_manager.get_route_context(route_id)
        fp_id = ctx.feed_point if ctx else ''
        fp_name = config.FEED_POINTS.get(fp_id, {}).get('name', fp_id)
        silo_bin = self.controller.route_silo_bin.get(route_id, '')
        target_bin = (ctx.target_bin if ctx else '') or self.controller.route_to_bin.get(route_id, '')
        return route_name, fp_name, target_bin, silo_bin

    def _on_route_state_changed(self, route_id: str, old_state: str, new_state: str):
        """路线状态变化（输出详细日志）"""
        route_name, fp_name, target_bin, silo_bin = self._get_route_detail(route_id)
        colors = {
            'moving_to_target': '#4A90D9',
            'feeding': '#2ECC71',
            'clearing': '#F39C12',
            'waiting': '#E67E22',
            'idle': '#8B949E',
        }

        if new_state == 'feeding':
            if old_state == 'moving_to_target':
                cart = target_bin or ''
                msg = f"小车已到达{cart}，开始上料 → {target_bin}"
            elif old_state == 'waiting':
                msg = f"恢复上料：{fp_name} → {target_bin}"
            else:
                msg = f"正在上料：{fp_name} → {target_bin}"
            self._log_belt(route_id, msg, colors['feeding'])

        elif new_state == 'clearing':
            msg = f"{target_bin}料仓将满，清空皮带余料"
            self._log_belt(route_id, msg, colors['clearing'])

            if self.controller._auto_feeding_active:
                for belt_id, r in list(self.controller._executing_route.items()):
                    if r == route_id:
                        self._log_belt(route_id, "清料中预请求下一轮调度", "#4A90D9")
                        self.controller._request_immediate_scheduling(belt_id)
                        break

        elif new_state == 'waiting':
            msg = f"{target_bin}上料完成，等待下次"
            self._log_belt(route_id, msg, colors['waiting'])

            if self.controller._auto_feeding_active:
                for belt_id, r in list(self.controller._executing_route.items()):
                    if r == route_id:
                        self._log_belt(route_id, f"路线完成，触发下一轮", "#4A90D9")
                        self.controller._on_auto_feed_route_completed(route_id)
                        break

        elif new_state == 'idle':
            if old_state not in ('moving_to_target',):
                if target_bin:
                    msg = f"已停止{target_bin}上料"
                else:
                    msg = "已停止"
                self._log_belt(route_id, msg, colors['idle'])

    def _on_route_bin_selected(self, route_id: str, bin_id: str):
        self.controller.set_route_target_bin(route_id, bin_id)

    def _on_route_silo_bin_selected(self, route_id: str, silo_bin: str, dest_bin: str):
        self.controller.set_route_silo_bin(route_id, silo_bin)
        self.controller.set_route_target_bin(route_id, dest_bin)

    def _on_fault_config_changed(self, config: dict):
        self.controller.set_fault_config(config)
        mode = config.get('mode')
        if mode and mode.value != 'off':
            count = config.get('count', 0)
            faulty_sensors = config.get('faulty_sensors', [])
            if faulty_sensors:
                self._update_status_bar(f"故障模拟: {count}个传感器 - {', '.join(faulty_sensors)}")
            else:
                self._update_status_bar("故障模拟: 请先启动至少一条路线")
        else:
            self._update_status_bar("故障模拟已关闭")

    def _on_speed_changed(self, speed: float):
        self.controller.set_speed(speed)

    def _on_start_all_routes(self):
        pass

    def _on_stop_all_routes(self):
        pass

    def _on_reset_simulation(self):
        """复位仿真（直接复位，无需确认弹窗）"""
        self.controller.stop_tcp_scheduling()
        self.control_panel.sched_tcp_btn.setChecked(False)
        self.control_panel.sched_tcp_btn.setText("调度服务：断开")
        self.control_panel.sched_tcp_status.setText("状态：D7○ D8○ D9○")
        self.control_panel.sched_tcp_status.setStyleSheet("color: #6E7681; font-size: 11px;")
        self.controller.reset()
        self.control_panel.set_speed(config.DEFAULT_SPEED)
        self.control_panel.set_tcp_status(False)
        self.control_panel.set_udp_status(False)
        # 重置故障设置UI
        self.control_panel.fault_mode_combo.setCurrentIndex(0)
        self.control_panel.hopper_fault_combo.setCurrentIndex(0)
        self.control_panel.hopper_select_combo.setCurrentIndex(0)
        self.control_panel.conveyor_fault_combo.setCurrentIndex(0)
        self.control_panel.conveyor_fault_type_combo.setCurrentIndex(0)
        self.control_panel.fault_status_label.setText("当前无故障设置")
        self.control_panel.conveyor_fault_status_label.setText("当前无皮带故障")
        self.operation_log.clear()
        self._log_sys("系统已复位", "#8B949E")
        self._update_status_bar("系统已复位")

    def _on_emergency_stop(self):
        """紧急停止（已废弃，由停止按钮替代）"""
        self.controller.reset()
        self._update_status_bar("系统已复位")

    def _on_conveyor_fault_changed(self, action: str, faults: dict = None):
        """皮带故障配置改变"""
        if action == 'clear':
            self._update_status_bar("已清除所有皮带故障")
        else:
            self._update_status_bar("皮带故障设置已更新")

    def _on_sensor_triggered(self, sensor_id: str, triggered: bool):
        """传感器触发"""
        pass

    def _on_alarm_raised(self, alarm_type: str, message: str):
        """报警触发"""
        self._update_status_bar(f"报警: {message}")

    def _on_material_spawned(self, material):
        """物料生成"""
        pass

    def _on_route_started(self, route_id: str):
        """路线启动"""
        pass

    def _on_route_stopped(self, route_id: str):
        """路线停止"""
        pass

    def _on_bin_clicked(self, bin_id: str):
        """处理画布上的小仓点击事件"""
        # 获取该小仓可用的上料路线
        if bin_id not in config.BIN_TO_AVAILABLE_ROUTES:
            QMessageBox.information(
                self,
                "无可用路线",
                f"小仓 {bin_id} 没有可用的上料路线。"
            )
            return

        available_routes = config.BIN_TO_AVAILABLE_ROUTES[bin_id]

        # 显示上料点选择对话框
        dialog = FeedPointSelectDialog(bin_id, available_routes, self)
        dialog.feed_point_selected.connect(self._on_feed_point_selected)
        dialog.exec_()

    def _on_feed_point_selected(self, feed_point: str, route_id: str, dest_bin: str, silo_bin: str = ''):
        """处理上料点选择"""
        from controllers.route_state_manager import RouteState

        if self.controller.is_auto_mode():
            QMessageBox.information(
                self, "自动模式",
                "当前为自动模式，上料操作由调度模块接管，手动操作被拦截。\n请先切换到手动模式。"
            )
            return

        ctx = self.controller.route_state_manager.get_route_context(route_id)

        # 小车繁忙检查：不允许小车处于移动或补料状态时被其他路线共用
        cart_id = self.controller.route_state_manager.ROUTE_CARTS.get(route_id)
        if cart_id:
            busy_route = self.controller.route_state_manager.get_cart_busy_route(cart_id, exclude_route=route_id)
            if busy_route:
                busy_ctx = self.controller.route_state_manager.get_route_context(busy_route)
                busy_state_name = busy_ctx.state.value if busy_ctx else 'unknown'
                QMessageBox.warning(
                    self,
                    "小车被占用",
                    f"小车 {cart_id} 正被路线 {busy_route} 使用（状态: {busy_state_name}），"
                    f"无法启动路线 {route_id}。"
                )
                return

        # 路线⑧⑨：先设置起点S仓
        if silo_bin:
            self.controller.set_route_silo_bin(route_id, silo_bin)

        # 设置终点小仓
        self.controller.set_route_target_bin(route_id, dest_bin)

        route_name = config.FEED_ROUTES.get(route_id, {}).get('name', route_id)
        fp_name = config.FEED_POINTS.get(feed_point, {}).get('name', feed_point)

        if ctx and ctx.state == RouteState.WAITING:
            success = self.controller.resume_route(route_id)
            if success:
                self.control_panel.active_routes.add(route_id)
                if route_id in self.control_panel.route_buttons:
                    self.control_panel.route_buttons[route_id].setChecked(True)
                if silo_bin:
                    self._update_status_bar(f"已恢复 {route_name}，起点: {silo_bin}，终点: {dest_bin}")
                    self._log_belt(route_id, f"恢复上料：{fp_name}({silo_bin}) → {dest_bin}", "#2ECC71")
                else:
                    self._update_status_bar(f"已恢复 {route_name}，目标小仓: {dest_bin}")
                    self._log_belt(route_id, f"恢复上料：{fp_name} → {dest_bin}", "#2ECC71")
        else:
            success = self.controller.start_route(route_id)
            if success:
                self.control_panel.active_routes.add(route_id)
                if route_id in self.control_panel.route_buttons:
                    self.control_panel.route_buttons[route_id].setChecked(True)
                if silo_bin:
                    self._update_status_bar(f"已启动 {route_name}，起点: {silo_bin}，终点: {dest_bin}")
                    self._log_belt(route_id, f"已启动：{fp_name}({silo_bin}) → {dest_bin}，小车移动中", "#2ECC71")
                else:
                    self._update_status_bar(f"已启动 {route_name}，目标小仓: {dest_bin}")
                    self._log_belt(route_id, f"已启动：{fp_name} → {dest_bin}，小车移动中", "#2ECC71")
            else:
                QMessageBox.warning(
                    self,
                    "启动失败",
                    f"无法启动路线 {route_id}。"
                )

    def _on_hopper_switch_toggled(self, hopper_id: str, new_state: bool):
        """中转斗开关切换处理"""
        # state: True=开, False=关
        self.controller.set_hopper_switch_state(hopper_id, new_state)
        state_text = "开" if new_state else "关"
        self._update_status_bar(f"中转斗 {hopper_id} 开关已设置为: {state_text}")

    def _on_data_reset_requested(self):
        """传感器数据初始化"""
        self.controller.reset_sensor_data()
        self.status_panel.update_all_status(collect_status_data(self.controller))
        self._update_status_bar("传感器数据已初始化")
        self._log_sys("传感器数据已初始化", "#8E44AD")

    def _on_laser_sensor_changed(self, laser_id: str, has_material: bool):
        """激光传感器状态改变"""
        self.controller.set_laser_sensor_state(laser_id, has_material)
        # 更新状态面板显示（强制更新，忽略缓存）
        self.status_panel.update_laser_sensor_display(laser_id, has_material, force_update=True)
        # 更新仿真视图（重绘激光传感器）
        self.simulation_view.mark_needs_repaint()
        self.simulation_view.update()
        state_text = "有料" if has_material else "无料"
        self._update_status_bar(f"激光传感器 {laser_id} 已设置为: {state_text}")

    def _on_bin_levels_uniform(self, percent: float):
        """统一设置全部料仓料位百分比"""
        self.controller.apply_bin_level_percent_uniform(percent)
        self.simulation_view.mark_needs_repaint()
        self.status_panel.update_all_status(collect_status_data(self.controller))
        self._update_status_bar(f"全部料仓料位已设为 {percent}%")

    def _on_bin_levels_random(self):
        """随机初始化各料仓料位"""
        self.controller.randomize_bin_levels_percent(5.0, 95.0)
        self.simulation_view.mark_needs_repaint()
        self.status_panel.update_all_status(collect_status_data(self.controller))
        self._update_status_bar("各料仓料位已在 5%–95% 范围内随机初始化")

    def _on_consumption_uniform(self, rate: float):
        """统一设置全部料仓消耗速度"""
        self.controller.apply_consumption_rate_uniform(rate)
        self._update_status_bar(f"全部料仓消耗速度已设为 {rate:.3f} t/s")

    def _on_consumption_random(self):
        """随机初始化各料仓消耗速度 (0.05-0.1)"""
        self.controller.randomize_consumption_rates(0.05, 0.1)
        self._update_status_bar("各料仓消耗速度已在 0.05–0.1 t/s 范围内随机初始化")

    def _on_consumption_toggled(self, active: bool):
        """启动/停止料仓消耗"""
        self.controller.toggle_consumption(active)
        state = "启动" if active else "停止"
        self._update_status_bar(f"料仓消耗已{state}")

    def _on_tcp_communication_toggled(self, enabled: bool):
        """下位机通信开关"""
        if enabled:
            self.controller.start_tcp_sender()
            status = "已连接" if self.controller.is_tcp_connected else "连接中（文件写入已启动）"
            self._update_status_bar(f"下位机通信已开启 - {status}")
            self._log_sys(f"下位机通信已开启 - {status}", "#2ECC71" if self.controller.is_tcp_connected else "#F39C12")
        else:
            self.controller.stop_tcp_sender()
            self._update_status_bar("下位机通信已关闭")
            self._log_sys("下位机通信已关闭", "#8B949E")

    def _on_udp_sender_toggled(self, enabled: bool):
        """UDP 二进制发送开关"""
        if enabled:
            self.controller.start_udp_sender()
            self._update_status_bar("UDP 二进制发送已开启")
            self._log_sys("UDP 二进制发送已开启", "#2ECC71")
        else:
            self.controller.stop_udp_sender()
            self._update_status_bar("UDP 二进制发送已关闭")
            self._log_sys("UDP 二进制发送已关闭", "#8B949E")

    def _on_diagnosis_mode_changed(self, mode: str):
        """诊断模式切换"""
        self.controller.set_diagnosis_mode(mode)
        if mode == "tcp":
            self._update_status_bar("诊断模式切换为：TCP 远程诊断")
            self._log_sys("诊断模式：TCP 远程诊断", "#4A90D9")
        else:
            self._update_status_bar("诊断模式切换为：本地诊断")
            self._log_sys("诊断模式：本地诊断", "#2ECC71")

    def _on_diagnosis_tcp_toggled(self, enabled: bool):
        """TCP 诊断服务连接开关"""
        if enabled:
            self.controller.start_tcp_diagnosis()
            self._update_status_bar("TCP 诊断服务连接中...")
            self._log_sys("TCP 诊断服务连接中...", "#F39C12")
        else:
            self.controller.stop_tcp_diagnosis()
            self.control_panel.set_diagnosis_tcp_status(False)
            self._update_status_bar("TCP 诊断服务已断开")
            self._log_sys("TCP 诊断服务已断开", "#8B949E")

    def _on_scheduling_tcp_toggled(self, enabled: bool):
        """TCP 调度服务连接开关 —— 自动上料模式"""
        if enabled:
            self.controller.start_tcp_scheduling()
            self._update_status_bar("自动上料：正在连接调度服务...")
            self._log_sys("自动上料模式已开启，连接调度服务...", "#2ECC71")
        else:
            self.controller.stop_tcp_scheduling()
            self.control_panel.set_scheduling_tcp_status({})
            self._update_status_bar("自动上料模式已关闭")
            self._log_sys("自动上料模式已关闭", "#8B949E")

    def _on_auto_mode_toggled(self, enabled: bool):
        """手动/自动模式切换"""
        self.controller.set_auto_mode(enabled)
        if enabled:
            self._update_status_bar("自动模式：调度模块接管上料控制")
            self._log_sys("已切换到自动模式，手动操作将被拦截", "#2ECC71")
        else:
            self._update_status_bar("手动模式：手动点击上料")
            self._log_sys("已切换到手动模式", "#8B949E")

    def _on_maintenance_line_added(self, line_num: int):
        self.controller.add_maintenance_line(line_num)
        self.control_panel.set_maintenance_list(self.controller.get_maintenance_bins())
        self._log_sys(f"产线{line_num}已设为检修", "#F39C12")

    def _on_maintenance_bin_added(self, bin_id: str):
        self.controller.add_maintenance_bin(bin_id)
        self.control_panel.set_maintenance_list(self.controller.get_maintenance_bins())
        self._log_sys(f"料仓{bin_id}已设为检修", "#F39C12")

    def _on_maintenance_clear(self):
        self.controller._maintenance_bins.clear()
        self.control_panel.set_maintenance_list([])
        self._log_sys("已清除全部检修", "#8B949E")

    def _on_export_log(self):
        """导出日志"""
        pass

    def _on_about(self):
        """关于"""
        QMessageBox.about(
            self, "关于",
            "搅拌站后料场上料系统仿真软件\n\n"
            "版本: 1.0\n"
            "皮带: E1, E2, E4, E5, E6, E7, E8, E9, E10, D1-D9, D13\n"
            "传感器: 18个接近开关\n"
            "上料路线: 9条\n"
            "配料站: 28仓\n\n"
            "基于 PyQt5 开发"
        )

    def closeEvent(self, event):
        """关闭事件"""
        reply = QMessageBox.question(
            self, "确认退出",
            "确定要退出仿真软件吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.controller.reset()
            self.update_timer.stop()
            self.logger.info("仿真软件关闭")
            event.accept()
        else:
            event.ignore()