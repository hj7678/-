"""
主窗口 - Main Window
搅拌站上料系统仿真软件
"""

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QStatusBar, QMenuBar, QMenu, QAction, QToolBar,
                             QMessageBox, QSizePolicy, QLabel, QScrollArea,
                             QPushButton, QInputDialog)
from PyQt5.QtCore import Qt, QTimer, QElapsedTimer
from PyQt5.QtGui import QKeySequence

import config
import styles
from views import SimulationView, ControlPanel, StatusPanel
from views.operation_log_panel import OperationLogPanel
from views.feed_point_select_dialog import FeedPointSelectDialog
from controllers import SimulationController
import logging
from utils.logger import get_logger
from belt_logger import enable_ui_bridge, attach_ui, belt_log, sys_log


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

        # 中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 顶层垂直布局
        top_level = QVBoxLayout(central_widget)
        top_level.setContentsMargins(10, 10, 10, 10)
        top_level.setSpacing(6)

        # ==== 顶部横栏：系统操作 + 自动上料模式 ====
        top_bar = QWidget()
        top_bar.setFixedHeight(48)
        top_bar.setStyleSheet(f"""
            QWidget {{
                background-color: {config.COLORS['panel']};
                border: 1px solid {config.COLORS['panel_border']};
                border-radius: 8px;
            }}
        """)
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(12, 4, 12, 4)
        top_bar_layout.setSpacing(12)

        # 左侧：系统操作
        sys_label = QLabel("系统操作")
        sys_label.setStyleSheet("color: #8B949E; font-weight: bold; font-size: 12px;")
        top_bar_layout.addWidget(sys_label)

        stop_btn = QPushButton("停止")
        stop_btn.setFixedSize(60, 32)
        stop_btn.setStyleSheet("background-color:#E74C3C;color:white;border:none;border-radius:4px;font-weight:bold;font-size:11px;")
        stop_btn.clicked.connect(self._on_top_stop_clicked)
        top_bar_layout.addWidget(stop_btn)

        emerg_btn = QPushButton("急停")
        emerg_btn.setFixedSize(60, 32)
        emerg_btn.setStyleSheet("background-color:#C0392B;color:white;border:2px solid #E74C3C;border-radius:4px;font-weight:bold;font-size:11px;")
        emerg_btn.clicked.connect(self._on_emergency_stop_clicked)
        top_bar_layout.addWidget(emerg_btn)

        reset_btn = QPushButton("复位")
        reset_btn.setFixedSize(60, 32)
        reset_btn.setStyleSheet("background-color:#9B59B6;color:white;border:none;border-radius:4px;font-weight:bold;font-size:11px;")
        reset_btn.clicked.connect(self._on_reset_simulation)
        top_bar_layout.addWidget(reset_btn)

        self_test_btn = QPushButton("自检")
        self_test_btn.setFixedSize(60, 32)
        self_test_btn.setStyleSheet("background-color:#2980B9;color:white;border:none;border-radius:4px;font-weight:bold;font-size:11px;")
        self_test_btn.clicked.connect(self._on_self_test_clicked)
        top_bar_layout.addWidget(self_test_btn)

        top_bar_layout.addSpacing(20)

        # 右侧：自动上料模式
        auto_label = QLabel("自动上料")
        auto_label.setStyleSheet("color: #4A90D9; font-weight: bold; font-size: 12px;")
        top_bar_layout.addWidget(auto_label)

        self.top_sched_btn = QPushButton("调度服务")
        self.top_sched_btn.setCheckable(True)
        self.top_sched_btn.setFixedSize(72, 32)
        self.top_sched_btn.setStyleSheet("""
            QPushButton {background-color:#2C3E50;color:#8B949E;border:2px solid #34495E;border-radius:4px;font-size:10px;}
            QPushButton:checked {background-color:#1B5E20;color:#00FF00;border-color:#00FF00;}
        """)
        top_bar_layout.addWidget(self.top_sched_btn)

        self.top_bridge_btn = QPushButton("桥接模式")
        self.top_bridge_btn.setCheckable(True)
        self.top_bridge_btn.setFixedSize(72, 32)
        self.top_bridge_btn.setToolTip("连接 FeedingMaster 上料主控，将仿真状态发送给外部控制大脑")
        self.top_bridge_btn.setStyleSheet(self.top_sched_btn.styleSheet())
        top_bar_layout.addWidget(self.top_bridge_btn)

        self.top_fm_btn = QPushButton("FM接管")
        self.top_fm_btn.setCheckable(True)
        self.top_fm_btn.setFixedSize(56, 32)
        self.top_fm_btn.setToolTip("FeedingMaster 接管决策: ON=FM控制仿真, OFF=仿真自决(监控模式)")
        self.top_fm_btn.setStyleSheet(self.top_sched_btn.styleSheet())
        top_bar_layout.addWidget(self.top_fm_btn)

        self.top_auto_btn = QPushButton("全部自动")
        self.top_auto_btn.setCheckable(True)
        self.top_auto_btn.setFixedSize(72, 32)
        self.top_auto_btn.setStyleSheet(self.top_sched_btn.styleSheet())
        top_bar_layout.addWidget(self.top_auto_btn)

        for belt_id in ['D6', 'D7', 'D8', 'D9']:
            btn = QPushButton(belt_id)
            btn.setCheckable(True)
            btn.setFixedSize(40, 28)
            btn.setStyleSheet("""
                QPushButton {background-color:#2C3E50;color:#8B949E;border:2px solid #34495E;border-radius:3px;font-size:9px;font-weight:bold;}
                QPushButton:checked {background-color:#1B5E20;color:#00FF00;border-color:#00FF00;}
            """)
            top_bar_layout.addWidget(btn)
            if not hasattr(self, '_top_belt_btns'):
                self._top_belt_btns = {}
            self._top_belt_btns[belt_id] = btn

        top_bar_layout.addSpacing(20)

        # ==== PLC 连接 / 模式指示 ====
        plc_label = QLabel("IO模式")
        plc_label.setStyleSheet("color: #8B949E; font-weight: bold; font-size: 12px;")
        top_bar_layout.addWidget(plc_label)

        self._plc_mode_btn = QPushButton("仿真")
        self._plc_mode_btn.setCheckable(True)
        self._plc_mode_btn.setChecked(False)
        self._plc_mode_btn.setFixedSize(72, 32)
        self._plc_mode_btn.setStyleSheet("""
            QPushButton {background-color:#1B5E20;color:#2ECC71;border:2px solid #2ECC71;border-radius:4px;font-size:11px;font-weight:bold;}
            QPushButton:checked {background-color:#1A5276;color:#3498DB;border-color:#3498DB;}
        """)
        self._plc_mode_btn.clicked.connect(self._on_plc_mode_toggled)
        top_bar_layout.addWidget(self._plc_mode_btn)

        self._plc_status_dot = QLabel("●")
        self._plc_status_dot.setFixedSize(16, 32)
        self._plc_status_dot.setStyleSheet("color:#2ECC71;font-size:16px;font-weight:bold;")
        top_bar_layout.addWidget(self._plc_status_dot)

        top_bar_layout.addStretch()
        top_level.addWidget(top_bar)

        # 主布局（左-中-右）
        main_layout = QHBoxLayout()
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
        center_layout.setSpacing(4)

        self.simulation_view = SimulationView()
        self.simulation_view.set_simulator(self.controller)
        self.simulation_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        center_layout.addWidget(self.simulation_view, 1)

        # 运行信息显示面板
        self.operation_log = OperationLogPanel()
        self.operation_log.setMinimumHeight(200)
        center_layout.addWidget(self.operation_log)

        # 皮带日志 → UI桥接
        enable_ui_bridge()
        for belt_id in ['system', 'D6', 'D7', 'D8', 'D9']:
            if belt_id == 'system':
                attach_ui('system', lambda _, msg: self.operation_log.add_log(msg, '#C0C8D0'))
            else:
                attach_ui(belt_id, lambda _, msg, b=belt_id: self.operation_log.add_belt_log(b, msg, '#C0C8D0'))

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

        # 将主布局加入顶层垂直布局
        top_level.addLayout(main_layout)

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
        # 顶部横栏按钮
        if hasattr(self, 'top_sched_btn'):
            self.top_sched_btn.clicked.connect(self._on_scheduling_tcp_toggled)
            self.top_bridge_btn.clicked.connect(self._on_bridge_toggled)
            self.top_fm_btn.clicked.connect(self._on_fm_takeover_toggled)
            self.top_auto_btn.clicked.connect(self._on_auto_mode_toggled)
        if hasattr(self, '_top_belt_btns'):
            for belt_id, btn in self._top_belt_btns.items():
                btn.clicked.connect(lambda checked, b=belt_id: self._on_belt_auto_mode_toggled(b, checked))
        # 控制面板信号
        self.control_panel.route_toggled.connect(self._on_route_toggled)
        self.control_panel.route_bin_selected.connect(self._on_route_bin_selected)
        self.control_panel.route_silo_bin_selected.connect(self._on_route_silo_bin_selected)
        self.control_panel.speed_changed.connect(self._on_speed_changed)
        self.control_panel.reset_requested.connect(self._on_reset_simulation)
        self.control_panel.fault_config_changed.connect(self._on_fault_config_changed)
        self.control_panel.conveyor_fault_changed.connect(self._on_conveyor_fault_changed)
        self.control_panel.laser_sensor_changed.connect(self._on_laser_sensor_changed)
        self.control_panel.tcp_communication_toggled.connect(self._on_tcp_communication_toggled)
        self.control_panel.scheduling_tcp_toggled.connect(self._on_scheduling_tcp_toggled)
        self.control_panel.auto_mode_toggled.connect(self._on_auto_mode_toggled)
        self.control_panel.belt_auto_mode_toggled.connect(self._on_belt_auto_mode_toggled)
        self.control_panel.bin_levels_uniform_requested.connect(self._on_bin_levels_uniform)
        self.control_panel.bin_levels_random_requested.connect(self._on_bin_levels_random)
        self.control_panel.cart_sensor_changed.connect(self._on_cart_sensor_changed)
        self.control_panel.udp_sender_toggled.connect(self._on_udp_sender_toggled)
        self.control_panel.diagnosis_mode_changed.connect(self._on_diagnosis_mode_changed)
        self.control_panel.diagnosis_tcp_toggled.connect(self._on_diagnosis_tcp_toggled)
        self.control_panel.consumption_toggled.connect(self._on_consumption_toggled)
        self.control_panel.consumption_uniform_requested.connect(self._on_consumption_uniform)
        self.control_panel.consumption_random_requested.connect(self._on_consumption_random)
        self.control_panel.maintenance_line_added.connect(self._on_maintenance_line_added)
        self.control_panel.maintenance_bin_added.connect(self._on_maintenance_bin_added)
        self.control_panel.maintenance_clear_requested.connect(self._on_maintenance_clear)

        # 状态面板信号 - 中转斗开关切换
        self.status_panel.hopper_switch_toggled.connect(self._on_hopper_switch_toggled)

        # 控制器信号
        self.controller.sensor_triggered.connect(self._on_sensor_triggered)
        self.controller.material_spawned.connect(self._on_material_spawned)
        self.controller.route_started.connect(self._on_route_started)
        self.controller.route_stopped.connect(self._on_route_stopped)
        self.controller.route_state_changed.connect(self._on_route_state_changed)

        # 仿真视图信号 - 画布点击选择上料路线
        self.simulation_view.bin_clicked.connect(self._on_bin_clicked)

    def _update_simulation(self):
        """更新仿真 - 使用实际经过的时间，不受UI事件阻塞影响"""
        # 调度数据推送独立于仿真运行状态
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
                # 状态面板限流更新（500ms间隔，减少长时间运行卡顿）
                if not hasattr(self, '_last_status_update_ms'):
                    self._last_status_update_ms = 0
                if current_elapsed_ms - self._last_status_update_ms >= 500:
                    self._last_status_update_ms = current_elapsed_ms
                    self.status_panel.update_all_status(self.controller)

        # 轮询 TCP 诊断/调度客户端连接状态，更新 UI
        self._poll_tcp_status()
        # 每5秒更新一次调度缓存显示
        if not hasattr(self, '_last_schedule_display'):
            self._last_schedule_display = 0.0
        if self.controller.total_runtime - self._last_schedule_display > 5.0:
            self._last_schedule_display = self.controller.total_runtime
            self._update_schedule_display()

    def _log_belt(self, route_id: str, msg: str, color: str = "#C0C8D0"):
        """记录皮带日志"""
        belt_map = {'route1': 'D7', 'route2': 'D7', 'route3': 'D7',
                    'route4': 'D9', 'route5': 'D6',
                    'route6': 'D8', 'route7': 'D9', 'route8': 'D8'}
        belt_id = belt_map.get(route_id, '')
        if belt_id and hasattr(self, 'operation_log'):
            self.operation_log.add_belt_log(belt_id, msg, color)

    def _update_schedule_display(self):
        """更新调度缓存序列显示（状态面板实时 + 运行日志仅变化时）"""
        # 状态面板实时更新
        if hasattr(self, 'status_panel') and hasattr(self.status_panel, 'update_schedule_display'):
            self.status_panel.update_schedule_display(
                self.controller._executing_bin,
                self.controller._scheduled_sequence,
            )
        # 运行日志：仅在序列变化时输出一次
        if not hasattr(self, 'operation_log'):
            return
        if not hasattr(self, '_last_schedule_log'):
            self._last_schedule_log = {}
        for belt_id in ['D6', 'D7', 'D8', 'D9']:
            seq = self.controller._scheduled_sequence.get(belt_id, [])
            exec_bin = self.controller._executing_bin.get(belt_id, '')
            if not seq and not exec_bin:
                self._last_schedule_log.pop(belt_id, None)
                continue
            key = f"{exec_bin}|{','.join(seq)}"
            if self._last_schedule_log.get(belt_id) == key:
                continue  # 未变化，跳过
            self._last_schedule_log[belt_id] = key
            parts = []
            if exec_bin:
                parts.append(f"[执行:{exec_bin}]")
            if seq:
                parts.append(f"队列:{','.join(seq)}")
            self.operation_log.add_belt_log(belt_id, ' '.join(parts), '#8B949E')

    def _poll_tcp_status(self):
        """轮询 TCP 诊断/调度客户端连接状态，更新 UI + 顶栏同步"""
        if hasattr(self.controller, 'get_tcp_diagnosis_status'):
            diag_connected = self.controller.get_tcp_diagnosis_status()
            self.control_panel.set_diagnosis_tcp_status(diag_connected)
        if hasattr(self.controller, 'get_tcp_scheduling_status'):
            sched_status = self.controller.get_tcp_scheduling_status()
            self.control_panel.set_scheduling_tcp_status(sched_status)

    def _update_status_bar(self, message: str):
        """更新状态栏"""
        self.status_bar.showMessage(message)

    # 槽函数
    def _on_route_toggled(self, route_id: str, enable: bool):
        """路线切换"""
        route_name = config.FEED_ROUTES[route_id]['name']
        if self.controller._use_feeding_master:
            if enable:
                return
            else:
                if self.controller._auto_feeding_active:
                    self._update_status_bar("自动模式: 请先关闭调度服务再停止路线")
                    self.control_panel.route_buttons[route_id].setChecked(True)
                    return
                if self.controller._feeding_bridge is not None:
                    self.controller._feeding_bridge.send_manual_stop(route_id)
                    self._update_status_bar(f"FM手动停止: {route_name}")
                return
        if enable:
            # 先检查路线是否可用（路线⑧⑨的 feed_point 是 silo_out，不做激光传感器检查）
            if not self.controller.is_route_available(route_id):
                # 上料点无料，路线不可用
                self._update_status_bar(f"{route_name} 启动失败：上料点无原料！")
                # 取消按钮选中状态
                self.control_panel.route_buttons[route_id].setChecked(False)
                return

            success = self.controller.start_route(route_id)
            if success:
                # 路线⑧⑨显示起点仓+终点仓，其他路线显示终点仓
                silo_bin = self.controller.route_silo_bin.get(route_id)
                dest_bin = self.controller.route_to_bin.get(route_id)
                if silo_bin and dest_bin:
                    self._update_status_bar(f"{route_name} 已启动，起点: {silo_bin}，终点: {dest_bin}")
                elif dest_bin:
                    self._update_status_bar(f"{route_name} 已启动 -> 目标仓: {dest_bin}")
                else:
                    self._update_status_bar(f"{route_name} 已启动")
        else:
            self.controller.stop_route(route_id)
            self._update_status_bar(f"{route_name} 已停止")

    def _on_route_bin_selected(self, route_id: str, bin_id: str):
        """路线小仓选择"""
        self.controller.set_route_target_bin(route_id, bin_id)
        route_name = config.FEED_ROUTES[route_id]['name']
        self._update_status_bar(f"{route_name} 目标仓: {bin_id}")

    def _on_route_silo_bin_selected(self, route_id: str, silo_bin: str, dest_bin: str):
        """处理控制面板路线⑧⑨的S仓+P仓双选完成"""
        # 设置起点仓（S仓，物料来源）
        self.controller.set_route_silo_bin(route_id, silo_bin)
        # 设置终点仓（P仓，小车目标位置）
        self.controller.set_route_target_bin(route_id, dest_bin)
        route_name = config.FEED_ROUTES[route_id]['name']
        self._update_status_bar(f"{route_name} 起点: {silo_bin}，终点: {dest_bin}")

    def _on_fault_config_changed(self, config: dict):
        """故障配置改变"""
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
        """速度改变"""
        self.controller.set_speed(speed)
        self._update_status_bar(f"皮带速度: {speed:.1f} m/s")

    def _on_start_all_routes(self):
        """启动所有路线（已废弃，仅保留兼容性）"""
        pass

    def _on_stop_all_routes(self):
        """停止所有路线（已废弃，仅保留兼容性）"""
        pass

    def _on_reset_simulation(self):
        """复位仿真（直接复位，无需确认弹窗）"""
        self.controller.reset()
        self.control_panel.set_speed(config.DEFAULT_SPEED)
        self._update_status_bar("系统已复位")

    def _on_tcp_communication_toggled(self, enabled: bool):
        """下位机通信开关"""
        if enabled:
            self.controller.start_tcp_sender()
        else:
            self.controller.stop_tcp_sender()
        self._update_status_bar(f"下位机通信: {'开' if enabled else '关'}")

    def _on_scheduling_tcp_toggled(self, enabled: bool):
        """调度服务连接开关"""
        if self.controller._use_feeding_master:
            # FM接管: 只切换_auto_feeding_active, FM的scheduler自动响应
            self.controller._auto_feeding_active = enabled
            self._update_status_bar(f"调度服务: {'开(FM)' if enabled else '关'}")
            return
        if enabled:
            # D7皮带：弹窗让用户选择上料点
            fps = ['feed1_1 (上料点1-1)', 'feed1_2 (上料点1-2)', 'feed2_1 (上料点2-1)']
            item, ok = QInputDialog.getItem(self, "选择D7上料点",
                "请选择D7皮带自动上料使用的上料点:", fps, 0, False)
            if ok:
                fp_id = item.split()[0]
                self.controller._d7_feed_override = fp_id
            self.controller.start_tcp_scheduling()
            # 同步顶栏：启动调度时自动开启所有皮带
            if hasattr(self, 'top_auto_btn'):
                self.top_auto_btn.setChecked(True)
            if hasattr(self, '_top_belt_btns'):
                for btn in self._top_belt_btns.values():
                    btn.setChecked(True)
        else:
            self.controller.stop_tcp_scheduling()
            if hasattr(self, 'top_auto_btn'):
                self.top_auto_btn.setChecked(False)
            if hasattr(self, '_top_belt_btns'):
                for btn in self._top_belt_btns.values():
                    btn.setChecked(False)
        # 关闭调度时同步关闭桥接
        if not enabled and hasattr(self, 'top_bridge_btn'):
            self.top_bridge_btn.setChecked(False)
            self.controller.stop_feeding_bridge()
        self._update_status_bar(f"调度服务: {'开' if enabled else '关'}")

    def _on_bridge_toggled(self, enabled: bool):
        """桥接模式开关 — 连接/断开 FeedingMaster 上料主控"""
        if self.controller._use_feeding_master:
            if not enabled:
                # FM接管时不允许关闭桥接
                if hasattr(self, 'top_bridge_btn'):
                    self.top_bridge_btn.setChecked(True)
            return
        if enabled:
            self.controller.start_feeding_bridge()
        else:
            self.controller.stop_feeding_bridge()
            # 关闭桥接时同步关闭FM接管
            if hasattr(self, 'top_fm_btn'):
                self.top_fm_btn.setChecked(False)
            self.controller.set_use_feeding_master(False)
        self._update_status_bar(f"桥接模式: {'开' if enabled else '关'}")

    def _on_fm_takeover_toggled(self, enabled: bool):
        """FM接管开关 — FeedingMaster 接管仿真决策"""
        if not enabled and self.controller._use_feeding_master:
            # FM接管时不允许关闭
            if hasattr(self, 'top_fm_btn'):
                self.top_fm_btn.setChecked(True)
            return
        self.controller.set_use_feeding_master(enabled)
        self._update_status_bar(f"FM接管: {'开' if enabled else '关(监控)'}")

    def _on_auto_mode_toggled(self, enabled: bool):
        """全部皮带自动模式切换"""
        if self.controller._use_feeding_master:
            # FM接管: 全部自动=开启调度
            self.controller._auto_feeding_active = enabled
            if hasattr(self, 'top_sched_btn'):
                self.top_sched_btn.setChecked(enabled)
            self._update_status_bar(f"自动上料: {'开' if enabled else '关'}")
            return
        self.controller.set_auto_mode(enabled)
        # 同步顶栏按钮
        if hasattr(self, 'top_auto_btn'):
            self.top_auto_btn.setChecked(enabled)
        if hasattr(self, '_top_belt_btns'):
            for btn in self._top_belt_btns.values():
                btn.setChecked(enabled)
        self._update_status_bar(f"自动模式: {'开' if enabled else '关'}")

    def _on_belt_auto_mode_toggled(self, belt_id: str, enabled: bool):
        """单条皮带自动模式切换"""
        if enabled and belt_id == 'D7':
            # D7皮带：弹窗让用户选择上料点
            fps = ['feed1_1 (上料点1-1)', 'feed1_2 (上料点1-2)', 'feed2_1 (上料点2-1)']
            item, ok = QInputDialog.getItem(self, f"选择{belt_id}上料点",
                f"请选择{belt_id}皮带自动上料使用的上料点:", fps, 0, False)
            if ok:
                fp_id = item.split()[0]
                self.controller._d7_feed_override = fp_id
                self._update_status_bar(f"{belt_id} 自动模式: {fp_id}")
            else:
                return  # 用户取消，不启用自动模式
        self.controller.set_belt_auto_mode(belt_id, enabled)
        if hasattr(self, '_top_belt_btns') and belt_id in self._top_belt_btns:
            self._top_belt_btns[belt_id].setChecked(enabled)
        self._update_status_bar(f"{belt_id} 自动模式: {'开' if enabled else '关'}")

    def _on_bin_levels_uniform(self, percent: float):
        """统一设置料位"""
        self.controller.apply_bin_level_percent_uniform(percent)
        self._update_status_bar(f"料位已统一设置为 {percent:.0f}%")

    def _on_bin_levels_random(self):
        """随机初始化料位"""
        self.controller.randomize_bin_levels_percent(25.0, 90.0)
        # 如果桥接模式激活，同步触发 Stock Management 随机化
        if self.controller._feeding_bridge is not None:
            self.controller._feeding_bridge.randomize_stock_levels(25.0, 90.0)
        self._update_status_bar("料位已随机初始化 (25-90%)")

    def _on_cart_sensor_changed(self, cart_id: str, data: dict):
        """小车传感器改变"""
        if 'position' in data and cart_id == 'Cart4':
            self.controller.set_cart4_target_position(data['position'])

    def _on_udp_sender_toggled(self, enabled: bool):
        if enabled:
            self.controller.start_udp_sender()
        else:
            self.controller.stop_udp_sender()

    def _on_diagnosis_mode_changed(self, mode: str):
        self.controller.set_diagnosis_mode(mode)

    def _on_diagnosis_tcp_toggled(self, enabled: bool):
        if enabled:
            self.controller.start_tcp_diagnosis()
        else:
            self.controller.stop_tcp_diagnosis()

    def _on_consumption_toggled(self, active: bool):
        self.controller.toggle_consumption(active)

    def _on_consumption_uniform(self, rate: float):
        self.controller.apply_consumption_rate_uniform(rate)

    def _on_consumption_random(self):
        self.controller.randomize_consumption_rates(0.05, 0.1)

    def _on_maintenance_line_added(self, line_num: int):
        self.controller.add_maintenance_line(line_num)
        self.control_panel.set_maintenance_list(self.controller.get_maintenance_bins())

    def _on_maintenance_bin_added(self, bin_id: str):
        self.controller.add_maintenance_bin(bin_id)
        self.control_panel.set_maintenance_list(self.controller.get_maintenance_bins())

    def _on_maintenance_clear(self):
        for bin_id in list(self.controller.get_maintenance_bins()):
            self.controller.remove_maintenance_bin(bin_id)
        self.control_panel.set_maintenance_list([])

    def _on_top_stop_clicked(self):
        """顶栏停止按钮 - 停止任意运行中的路线（含自动模式启动的）"""
        # 过滤掉节能待机(STANDBY)的路线
        active = [rid for rid in self.controller.active_routes
                  if self.controller.route_state_manager.get_route_state(rid) != 'standby']
        if not active:
            self._update_status_bar("当前没有运行中的路线")
            return
        if len(active) == 1:
            rid = active[0]
            rname = config.FEED_ROUTES.get(rid, {}).get('name', rid)
            self.controller.stop_route(rid)
            self._update_status_bar(f"已停止 {rname}")
            self.operation_log.add_log(f"! 停止 {rname}", "#E74C3C")
            self.logger.info(f"停止 {rname}")
        else:
            # 多条路线时弹出选择框
            items = [f"{rid} {config.FEED_ROUTES.get(rid,{}).get('name',rid)}" for rid in active]
            item, ok = QInputDialog.getItem(self, "停止路线", "选择要停止的路线:", items, 0, False)
            if ok and item:
                rid = item.split()[0]
                self.controller.stop_route(rid)
                self._update_status_bar(f"已停止 {item}")
                self.operation_log.add_log(f"! 停止 {item}", "#E74C3C")
                self.logger.info(f"停止 {item}")

    def _on_plc_mode_toggled(self, checked: bool):
        """切换 IO 模式：仿真 ↔ PLC"""
        if checked:
            # 切换到 PLC 模式
            from modbus_driver import ModbusDriver
            driver = ModbusDriver()
            if driver.connect():
                self.controller.io.set_driver(driver)
                self._plc_mode_btn.setText("PLC在线")
                self._plc_status_dot.setStyleSheet("color:#3498DB;font-size:16px;font-weight:bold;")
                self._update_status_bar("已连接到 PLC")
                self.operation_log.add_log("系统: IO模式切换 → PLC在线", "#3498DB")
            else:
                self._plc_mode_btn.setChecked(False)
                self._update_status_bar("PLC连接失败(检查pymodbus/网络)")
                self.operation_log.add_log("系统: PLC连接失败", "#E74C3C")
        else:
            # 切换回仿真模式
            from io_bus import SimDriver
            self.controller.io.set_driver(SimDriver(self.controller))
            self._plc_mode_btn.setText("仿真")
            self._plc_status_dot.setStyleSheet("color:#2ECC71;font-size:16px;font-weight:bold;")
            self._update_status_bar("已切换到仿真模式")
            self.operation_log.add_log("系统: IO模式切换 → 仿真", "#2ECC71")

    def _on_self_test_clicked(self):
        """自检按钮"""
        self._update_status_bar("正在执行系统自检...")
        result = self.controller.do_self_test()
        if result.passed:
            self._update_status_bar("自检通过")
            self.operation_log.add_log("系统自检: 通过", "#2ECC71")
        else:
            self._update_status_bar(f"自检失败: {len(result.errors)}项错误")
            for e in result.errors:
                self.operation_log.add_log(f"自检错误: {e}", "#E74C3C")

    def _on_emergency_stop_clicked(self):
        """急停按钮：立即切断所有输出"""
        if self.controller._use_feeding_master:
            if self.controller._auto_feeding_active:
                self._update_status_bar("自动模式: 请先关闭调度服务再急停")
                return
            if self.controller._feeding_bridge is not None:
                self.controller._feeding_bridge._fm._send({"type": "emergency_stop"})
                self._update_status_bar("FM急停已发送")
            return
        if hasattr(self.controller, 'lifecycle'):
            self.controller.lifecycle.emergency_stop(self.controller)
            self._update_status_bar("急停！所有输出已切断")
        self.operation_log.add_log("!!! 急停 !!!", "#E74C3C")
        self.logger.info("急停触发")

    def _on_emergency_stop(self):
        """紧急停止（兼容旧接口）"""
        self._on_emergency_stop_clicked()

    def _on_conveyor_fault_changed(self, action: str, faults: dict = None):
        """皮带故障配置改变"""
        if action == 'clear':
            self._update_status_bar("已清除所有皮带故障")
        else:
            self._update_status_bar("皮带故障设置已更新")

    def _on_sensor_triggered(self, sensor_id: str, triggered: bool):
        """传感器触发"""
        pass

    def _on_material_spawned(self, material):
        """物料生成"""
        pass

    def _on_route_started(self, route_id: str):
        """路线启动"""
        route_name = config.FEED_ROUTES.get(route_id, {}).get('name', route_id)
        target = self.controller.route_to_bin.get(route_id, '?')
        self._log_belt(route_id, f"启动 {route_name} → {target}", "#2ECC71")
        self.operation_log.add_log(f"系统: {route_name} 启动", "#2ECC71")
        # 点亮控制面板路线按钮
        self.control_panel.update_route_button(route_id, True)

    def _on_route_stopped(self, route_id: str):
        """路线停止"""
        route_name = config.FEED_ROUTES.get(route_id, {}).get('name', route_id)
        self._log_belt(route_id, f"停止 {route_name}", "#E74C3C")
        self.operation_log.add_log(f"系统: {route_name} 停止", "#E74C3C")
        # 熄灭控制面板路线按钮
        self.control_panel.update_route_button(route_id, False)

    def _on_route_state_changed(self, route_id: str, old_state: str, new_state: str):
        """路线状态变化"""
        route_name = config.FEED_ROUTES.get(route_id, {}).get('name', route_id)
        target = self.controller.route_to_bin.get(route_id, '')
        state_cn = {
            'idle': '空闲', 'feeding': '上料中', 'clearing': '清空中',
            'waiting': '等待', 'standby': '待机', 'moving_to_target': '小车移动',
        }
        new_cn = state_cn.get(new_state, new_state)
        # 更新皮带状态摘要行
        belt_map = {'route1':'D7','route2':'D7','route3':'D7',
                    'route4':'D9','route5':'D6','route6':'D8','route7':'D9','route8':'D8'}
        belt_id = belt_map.get(route_id, '')
        state_colors = {'feeding':'#2ECC71','clearing':'#F39C12','waiting':'#E67E22',
                        'standby':'#8B949E','moving_to_target':'#3498DB','idle':'#555'}
        if belt_id and hasattr(self, 'operation_log'):
            status = f"{route_name} → {target}: {new_cn}" if target else f"{route_name}: {new_cn}"
            self.operation_log.set_belt_status(belt_id, status, state_colors.get(new_state, '#4A90D9'))
        # 分皮带日志
        if target:
            self._log_belt(route_id, f"{route_name} → {target}: {new_cn}", "#4A90D9")
        else:
            self._log_belt(route_id, f"{route_name}: {new_cn}", "#4A90D9")
        # 系统总日志 + 文件日志
        if new_state == 'feeding':
            msg = f"> {route_name} 开始上料 → {target}"
            self.operation_log.add_log(msg, "#2ECC71")
            self.logger.info(msg)
        elif new_state == 'clearing':
            msg = f"> {route_name} 清空余料中..."
            self.operation_log.add_log(msg, "#F39C12")
            self.logger.info(msg)
        elif new_state == 'waiting':
            msg = f"> {route_name} → {target} 上料完成"
            self.operation_log.add_log(msg, "#E67E22")
            self.logger.info(msg)
        elif new_state == 'moving_to_target':
            msg = f"> {route_name} 小车驶向 {target}"
            self.operation_log.add_log(msg, "#3498DB")
            self.logger.info(msg)
        elif new_state == 'standby':
            msg = f"> {route_name} 节能待机"
            self.operation_log.add_log(msg, "#8B949E")
            self.logger.info(msg)
        elif new_state == 'standby':
            self.operation_log.add_log(f"> {route_name} 节能待机", "#8B949E")
        elif new_state == 'moving_to_target':
            self.operation_log.add_log(f"> {route_name} 小车驶向 {target}", "#3498DB")
        # 当进入等待状态时触发下一轮调度
        if new_state == 'waiting':
            self._update_schedule_display()
            if self.controller._auto_feeding_active and not self.controller._use_feeding_master:
                for belt_id, r in list(self.controller._executing_route.items()):
                    if r == route_id:
                        self._log_belt(route_id, "路线完成，触发下一轮", "#4A90D9")
                        self.controller._on_auto_feed_route_completed(route_id)
                        break
        # 进入待机时也更新显示
        if new_state == 'standby':
            self._update_schedule_display()

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
        if self.controller._use_feeding_master:
            if self.controller._auto_feeding_active:
                self._update_status_bar("自动模式: 请先关闭调度服务再手动上料")
                return
            if self.controller._feeding_bridge is not None:
                self.controller._feeding_bridge.send_manual_start(dest_bin, route_id)
                self._update_status_bar(f"FM手动上料: {config.FEED_ROUTES[route_id]['name']} → {dest_bin}")
            return
        from controllers.route_state_manager import RouteState

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

        if ctx and ctx.state == RouteState.WAITING:
            success = self.controller.resume_route(route_id)
            if success:
                # 同步更新控制面板的active_routes和按钮状态
                self.control_panel.active_routes.add(route_id)
                if route_id in self.control_panel.route_buttons:
                    self.control_panel.route_buttons[route_id].setChecked(True)
                route_name = config.FEED_ROUTES.get(route_id, {}).get('name', route_id)
                if silo_bin:
                    self._update_status_bar(f"已恢复 {route_name}，起点: {silo_bin}，终点: {dest_bin}")
                else:
                    self._update_status_bar(f"已恢复 {route_name}，目标小仓: {dest_bin}")
        else:
            success = self.controller.start_route(route_id)
            if success:
                # 同步更新控制面板的active_routes和按钮状态
                self.control_panel.active_routes.add(route_id)
                if route_id in self.control_panel.route_buttons:
                    self.control_panel.route_buttons[route_id].setChecked(True)
                route_name = config.FEED_ROUTES.get(route_id, {}).get('name', route_id)
                if silo_bin:
                    self._update_status_bar(f"已启动 {route_name}，起点: {silo_bin}，终点: {dest_bin}")
                else:
                    self._update_status_bar(f"已启动 {route_name}，目标小仓: {dest_bin}")
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