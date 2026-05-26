"""
控制面板 - Control Panel
支持9条上料路线的控制
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QGroupBox, QPushButton, QSlider, QLabel, QComboBox,
                             QMessageBox, QCheckBox, QLineEdit, QRadioButton)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QDoubleValidator
from typing import Dict, List, Tuple, Set
import config
import styles
from sensor_fault_diagnosis import SensorFaultDiagnosis, FaultMode
from sensor_data_manager import get_data_manager
from views.bin_select_dialog import SmallBinSelectDialog


# 需要激光传感器的上料点
FEED_POINTS_WITH_LASER_SENSOR = ['feed1_1', 'feed1_2', 'feed2_1', 'feed2_2', 'feed3']

# 激光传感器到路线的映射
LASER_TO_ROUTE_MAPPING = {
    'feed1_1': ['route1'],  # 上料点1-1 -> 路线①
    'feed1_2': ['route2'],  # 上料点1-2 -> 路线②
    'feed2_1': ['route3'],  # 上料点2-1 -> 路线③
    'feed2_2': ['route4', 'route5'],  # 上料点2-2 -> 路线④⑤
    'feed3': ['route6', 'route7'],  # 上料点3 -> 路线⑥⑦
}


# 需要选择小仓的路线（终点是D7/D8/D9/D6）
# D7 -> P1-1 到 P1-7
# D8 -> P2-1 到 P2-7, P3-1 到 P3-7
# D9 -> P4-1 到 P4-7
# D6 -> S1 到 S12（高位储料仓）
ROUTES_REQUIRING_BIN_SELECTION: Set[str] = {
    'route1', 'route2', 'route3',  # D7
    'route4', 'route6', 'route8',   # D9
    'route7', 'route9',             # D8
    'route5',                       # D6 -> 高位储料仓
}


class ControlPanel(QWidget):
    """控制面板组件"""

    # 信号定义
    route_toggled = pyqtSignal(str, bool)  # 路线ID, 启动/停止
    route_bin_selected = pyqtSignal(str, str)  # 路线ID, 小仓ID
    route_silo_bin_selected = pyqtSignal(str, str, str)  # 路线ID, S仓, P仓（路线⑧⑨专用）
    speed_changed = pyqtSignal(float)       # 速度变化
    feed_requested = pyqtSignal(str)       # 供料请求
    reset_requested = pyqtSignal()         # 复位请求
    emergency_stop = pyqtSignal()          # 紧急停止
    fault_config_changed = pyqtSignal(dict)  # 故障配置改变
    conveyor_fault_changed = pyqtSignal(str, object)  # 皮带故障配置改变
    laser_sensor_changed = pyqtSignal(str, bool)  # 激光传感器ID, 有料状态
    cart_sensor_changed = pyqtSignal(str, dict)  # 小车传感器改变信号 (cart_id, {sensor_type: value})
    bin_levels_uniform_requested = pyqtSignal(float)  # 统一料位百分比 0-100
    bin_levels_random_requested = pyqtSignal()  # 随机初始化料位
    consumption_random_requested = pyqtSignal()
    consumption_uniform_requested = pyqtSignal(float)
    consumption_toggled = pyqtSignal(bool)
    tcp_communication_toggled = pyqtSignal(bool)  # 下位机通信开关
    udp_sender_toggled = pyqtSignal(bool)  # UDP 二进制发送开关
    diagnosis_mode_changed = pyqtSignal(str)   # 诊断模式切换 "local" / "tcp"
    diagnosis_tcp_toggled = pyqtSignal(bool)   # TCP 诊断服务连接开关
    scheduling_tcp_toggled = pyqtSignal(bool)  # TCP 调度服务连接开关
    auto_mode_toggled = pyqtSignal(bool)  # 手动/自动模式切换
    maintenance_line_added = pyqtSignal(int)    # 产线检修添加 (line_num)
    maintenance_bin_added = pyqtSignal(str)     # 料仓检修添加 (bin_id)
    maintenance_clear_requested = pyqtSignal()  # 清除全部检修

    def __init__(self, parent=None):
        super().__init__(parent)

        self.route_buttons = {}
        self.speed_slider = None
        self.speed_label = None
        self.active_routes = set()
        self.route_to_bin: Dict[str, str] = {}  # 路线到小仓的映射
        self._cart_init_written: Set[str] = set()  # 已写入初始化数据的小车ID集合

        # 故障诊断系统
        self.fault_diagnosis = SensorFaultDiagnosis()
        self.fault_mode_combo = None
        self.fault_count_combo = None
        self.fault_apply_btn = None
        self.fault_clear_btn = None
        self.fault_status_label = None
        self.current_fault_count = 0

        # 传感器数据管理器（用于皮带转速故障）
        self._sensor_data_manager = get_data_manager()

        # 激光传感器状态复选框
        self.laser_sensor_checkboxes: Dict[str, QCheckBox] = {}

        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        self.setMinimumWidth(240)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # 标题
        title = QLabel("控制面板")
        title.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #4A90D9;
                padding: 5px;
                border-bottom: 2px solid #4A90D9;
                margin-bottom: 5px;
            }
        """)
        main_layout.addWidget(title)

        bin_level_group = self._create_bin_level_init_group()
        main_layout.addWidget(bin_level_group)

        consumption_group = self._create_consumption_rate_group()
        main_layout.addWidget(consumption_group)

        # 速度控制组
        speed_group = self._create_speed_control_group()
        main_layout.addWidget(speed_group)

        # 激光传感器设置组（上料点原料状态）
        laser_group = self._create_laser_sensor_group()
        main_layout.addWidget(laser_group)

        # 小车传感器设置组
        cart_sensor_group = self._create_cart_sensor_group()
        main_layout.addWidget(cart_sensor_group)

        # 上料路线控制组
        route_group = self._create_route_control_group()
        main_layout.addWidget(route_group)

        # 操作按钮组
        operation_group = self._create_operation_group()
        main_layout.addWidget(operation_group)

        # 传感器故障诊断组
        fault_group = self._create_fault_diagnosis_group()
        main_layout.addWidget(fault_group)

        # 检修设置组
        maintenance_group = self._create_maintenance_group()
        main_layout.addWidget(maintenance_group)

        main_layout.addStretch()

    def _create_speed_control_group(self) -> QGroupBox:
        """创建速度控制组"""
        group = QGroupBox("皮带速度")
        group.setStyleSheet(styles.get_group_box_style())
        layout = QVBoxLayout()
        layout.setSpacing(4)

        # 速度标签和滑块一行
        speed_row_layout = QHBoxLayout()
        speed_label = QLabel("速度:")
        speed_label.setStyleSheet("color: #ECF0F1;")
        speed_row_layout.addWidget(speed_label)
        self.speed_label = QLabel(f"{config.DEFAULT_SPEED:.1f}")
        self.speed_label.setAlignment(Qt.AlignRight)
        self.speed_label.setStyleSheet("font-weight: bold; color: #4A90D9;")
        speed_row_layout.addWidget(self.speed_label)
        speed_unit_label = QLabel("m/s")
        speed_unit_label.setStyleSheet("color: #8B949E;")
        speed_row_layout.addWidget(speed_unit_label)
        layout.addLayout(speed_row_layout)

        # 速度滑块
        self.speed_slider = QSlider(Qt.Horizontal)
        self.speed_slider.setMinimum(int(config.MIN_SPEED * 10))
        self.speed_slider.setMaximum(int(config.MAX_SPEED * 10))
        self.speed_slider.setValue(int(config.DEFAULT_SPEED * 10))
        self.speed_slider.setTickPosition(QSlider.NoTicks)
        self.speed_slider.setFixedHeight(20)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        layout.addWidget(self.speed_slider)

        # 速度范围
        range_layout = QHBoxLayout()
        min_label = QLabel(f"{config.MIN_SPEED}")
        min_label.setStyleSheet("color: #6E7681; font-size: 9px;")
        range_layout.addWidget(min_label)
        range_layout.addStretch()
        max_label = QLabel(f"{config.MAX_SPEED}")
        max_label.setStyleSheet("color: #6E7681; font-size: 9px;")
        range_layout.addWidget(max_label)
        layout.addLayout(range_layout)

        group.setLayout(layout)
        return group

    def _create_bin_level_init_group(self) -> QGroupBox:
        """配料站与高位储料仓料位初始化（百分比）"""
        group = QGroupBox("料位初始化")
        group.setStyleSheet(styles.get_group_box_style())
        layout = QVBoxLayout()
        layout.setSpacing(6)

        info = QLabel("统一设置全部料仓料位百分比，或随机 5–95。")
        info.setStyleSheet("color: #8B949E; font-size: 10px;")
        layout.addWidget(info)

        row = QHBoxLayout()
        level_label = QLabel("料位%:")
        level_label.setStyleSheet("color: #ECF0F1;")
        row.addWidget(level_label)
        self._bin_level_edit = QLineEdit()
        self._bin_level_edit.setPlaceholderText("0–100，一位小数")
        self._bin_level_edit.setStyleSheet("color: #ECF0F1; background-color: #21262d;")
        self._bin_level_edit.setFixedWidth(72)
        val = QDoubleValidator(0.0, 100.0, 1, self)
        val.setNotation(QDoubleValidator.StandardNotation)
        self._bin_level_edit.setValidator(val)
        row.addWidget(self._bin_level_edit)

        apply_btn = QPushButton("应用")
        apply_btn.setStyleSheet(styles.get_small_button_style('#27AE60'))
        apply_btn.clicked.connect(self._on_bin_level_uniform_apply)
        row.addWidget(apply_btn)
        layout.addLayout(row)

        rand_btn = QPushButton("随机初始化 (5–95%)")
        rand_btn.setStyleSheet(styles.get_small_button_style('#8E44AD'))
        rand_btn.clicked.connect(lambda: self.bin_levels_random_requested.emit())
        layout.addWidget(rand_btn)

        group.setLayout(layout)
        return group

    def _on_bin_level_uniform_apply(self):
        text = self._bin_level_edit.text().strip().replace(',', '.')
        if not text:
            QMessageBox.warning(self, "料位初始化", "请输入料位百分比。")
            return
        try:
            v = round(float(text), 1)
        except ValueError:
            QMessageBox.warning(self, "料位初始化", "请输入有效数字。")
            return
        if v < 0 or v > 100:
            QMessageBox.warning(self, "料位初始化", "料位百分比应在 0–100 之间。")
            return
        self.bin_levels_uniform_requested.emit(v)

    def _create_consumption_rate_group(self) -> QGroupBox:
        """消耗速度设置（各配料站料仓）"""
        group = QGroupBox("消耗速度设置")
        group.setStyleSheet(styles.get_group_box_style())
        layout = QVBoxLayout()
        layout.setSpacing(6)

        info = QLabel("统一设置全部料仓消耗速度(t/s)，或随机 0.05–0.1。")
        info.setStyleSheet("color: #8B949E; font-size: 10px;")
        layout.addWidget(info)

        row = QHBoxLayout()
        rate_label = QLabel("速度:")
        rate_label.setStyleSheet("color: #ECF0F1;")
        row.addWidget(rate_label)
        self._consumption_rate_edit = QLineEdit()
        self._consumption_rate_edit.setPlaceholderText("0.05–0.2 t/s")
        self._consumption_rate_edit.setStyleSheet("color: #ECF0F1; background-color: #21262d;")
        self._consumption_rate_edit.setFixedWidth(72)
        val = QDoubleValidator(0.01, 1.0, 3, self)
        val.setNotation(QDoubleValidator.StandardNotation)
        self._consumption_rate_edit.setValidator(val)
        row.addWidget(self._consumption_rate_edit)

        apply_btn = QPushButton("应用")
        apply_btn.setStyleSheet(styles.get_small_button_style('#27AE60'))
        apply_btn.clicked.connect(self._on_consumption_rate_uniform_apply)
        row.addWidget(apply_btn)
        layout.addLayout(row)

        rand_btn = QPushButton("随机初始化 (0.05–0.1 t/s)")
        rand_btn.setStyleSheet(styles.get_small_button_style('#8E44AD'))
        rand_btn.clicked.connect(lambda: self.consumption_random_requested.emit())
        layout.addWidget(rand_btn)

        self._consumption_toggle_btn = QPushButton("启动消耗")
        self._consumption_toggle_btn.setCheckable(True)
        self._consumption_toggle_btn.setStyleSheet(styles.get_small_button_style('#E67E22'))
        self._consumption_toggle_btn.clicked.connect(self._on_consumption_toggle)
        layout.addWidget(self._consumption_toggle_btn)

        group.setLayout(layout)
        return group

    def _on_consumption_toggle(self, checked: bool):
        if checked:
            self._consumption_toggle_btn.setText("停止消耗")
            self._consumption_toggle_btn.setStyleSheet(styles.get_small_button_style('#E74C3C'))
        else:
            self._consumption_toggle_btn.setText("启动消耗")
            self._consumption_toggle_btn.setStyleSheet(styles.get_small_button_style('#E67E22'))
        self.consumption_toggled.emit(checked)

    def _on_consumption_rate_uniform_apply(self):
        text = self._consumption_rate_edit.text().strip().replace(',', '.')
        if not text:
            QMessageBox.warning(self, "消耗速度设置", "请输入消耗速度。")
            return
        try:
            v = round(float(text), 3)
        except ValueError:
            QMessageBox.warning(self, "消耗速度设置", "请输入有效数字。")
            return
        if v < 0.01 or v > 1.0:
            QMessageBox.warning(self, "消耗速度设置", "消耗速度应在 0.01–1.0 t/s 之间。")
            return
        self.consumption_uniform_requested.emit(v)

    def _create_laser_sensor_group(self) -> QGroupBox:
        """创建激光测距仪传感器设置组"""
        group = QGroupBox("上料点原料状态")
        group.setStyleSheet(styles.get_group_box_style())
        layout = QVBoxLayout()
        layout.setSpacing(6)

        # 说明标签
        info_label = QLabel("设置各上料点是否有原料（激光测距仪检测）")
        info_label.setStyleSheet("color: #8B949E; font-size: 10px;")
        layout.addWidget(info_label)

        # 上料点名称映射
        feed_point_names = {
            'feed1_1': '上料点1-1',
            'feed1_2': '上料点1-2',
            'feed2_1': '上料点2-1',
            'feed2_2': '上料点2-2',
            'feed3': '上料点3',
        }

        # 激光传感器到上料点的映射
        laser_to_feed = {
            'S-feed1_1': 'feed1_1',
            'S-feed1_2': 'feed1_2',
            'S-feed2_1': 'feed2_1',
            'S-feed2_2': 'feed2_2',
            'S-feed3': 'feed3',
        }

        # 创建每个激光传感器的设置
        for laser_id in config.LASER_SENSORS.keys():
            feed_point = laser_to_feed.get(laser_id, laser_id)
            feed_point_name = feed_point_names.get(feed_point, feed_point) or laser_id
            routes = LASER_TO_ROUTE_MAPPING.get(feed_point, [])

            row_layout = QHBoxLayout()
            row_layout.setSpacing(8)

            # 激光传感器名称
            laser_label = QLabel(f"{feed_point_name}:")
            laser_label.setStyleSheet("color: #E6EDF3; font-weight: bold; min-width: 65px;")
            row_layout.addWidget(laser_label)

            # 有料/无料复选框
            checkbox = QCheckBox("有料")
            checkbox.setChecked(True)  # 默认有料
            checkbox.setStyleSheet("""
                QCheckBox {
                    color: #8B949E;
                    font-size: 11px;
                }
                QCheckBox:checked {
                    color: #2ECC71;
                }
                QCheckBox::indicator {
                    width: 14px;
                    height: 14px;
                }
                QCheckBox::indicator:checked {
                    background-color: #2ECC71;
                    border: 1px solid #27AE60;
                    border-radius: 3px;
                }
                QCheckBox::indicator:unchecked {
                    background-color: #2C3E50;
                    border: 1px solid #34495E;
                    border-radius: 3px;
                }
            """)
            checkbox.stateChanged.connect(
                lambda state, lid=laser_id, fid=feed_point: self._on_laser_sensor_changed(lid, fid, state)
            )
            self.laser_sensor_checkboxes[laser_id] = checkbox
            row_layout.addWidget(checkbox)

            # 相关路线提示
            if routes:
                route_names = [config.FEED_ROUTES[r]['name'] for r in routes]
                routes_label = QLabel(f"({', '.join(route_names)})")
                routes_label.setStyleSheet("color: #6E7681; font-size: 9px;")
                row_layout.addWidget(routes_label)

            row_layout.addStretch()

            layout.addLayout(row_layout)

        # 状态提示
        self.laser_status_label = QLabel("有料=可启用对应路线，无料=路线不可用")
        self.laser_status_label.setStyleSheet("""
            QLabel {
                color: #6E7681;
                font-size: 9px;
                padding: 4px;
                background-color: #21262d;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.laser_status_label)

        group.setLayout(layout)
        return group

    def _on_laser_sensor_changed(self, laser_id: str, feed_point: str, state: int):
        """激光传感器状态改变"""
        has_material = (state == Qt.Checked)
        self.laser_sensor_changed.emit(laser_id, has_material)

    def _create_cart_sensor_group(self) -> QGroupBox:
        """创建小车初始化设置组"""
        group = QGroupBox("运料小车初始化设置")
        group.setStyleSheet(styles.get_group_box_style())
        layout = QVBoxLayout()
        layout.setSpacing(6)

        # 说明标签
        info_label = QLabel("设置小车初始位置和传感器状态，点击应用写入数据文件")
        info_label.setStyleSheet("color: #8B949E; font-size: 10px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # 2x2 网格布局存放小车卡片
        cards_layout = QGridLayout()
        cards_layout.setSpacing(6)
        self.cart_sensor_controls = {}

        cart_ids = list(config.CART_SENSORS.keys())
        for i, cart_id in enumerate(cart_ids):
            cart_config = config.CART_SENSORS[cart_id]
            card_widget, apply_btn = self._create_cart_card(cart_id, cart_config)
            self.cart_sensor_controls[cart_id]['apply_btn'] = apply_btn
            row, col = i // 2, i % 2
            cards_layout.addWidget(card_widget, row, col)

        layout.addLayout(cards_layout)
        group.setLayout(layout)
        return group

    def _create_cart_card(self, cart_id: str, cart_config: dict) -> Tuple[QWidget, QPushButton]:
        """创建单个小车的卡片，返回卡片widget和应用按钮引用"""
        card = QWidget()
        card.setStyleSheet("""
            QWidget {
                background-color: #1E1E1E;
                border: 1px solid #34495E;
                border-radius: 4px;
            }
        """)
        card_layout = QGridLayout(card)
        card_layout.setSpacing(2)
        card_layout.setContentsMargins(6, 4, 6, 4)
        card_layout.setColumnStretch(0, 1)

        # 标题（跨左两列）
        # 运料小车1/2/3/4 显示（去掉 D7/D8/D9 旧命名）
        cart_num_map = {'Cart1': '运料小车1', 'Cart2': '运料小车2', 'Cart3': '运料小车3', 'Cart4': '运料小车4'}
        title = QLabel(f"{cart_num_map.get(cart_id, cart_id)}")
        title.setStyleSheet("color: #1D6; font-weight: bold; font-size: 10px;")
        title.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title, 0, 0, 1, 2)

        # 位置行
        pos_label = QLabel("位:")
        pos_label.setStyleSheet("color: #8B949E; font-size: 9px;")
        card_layout.addWidget(pos_label, 1, 0)

        pos_combo = QComboBox()
        if cart_id == 'Cart4':
            pos_combo.addItems([str(i) for i in range(1, 7)])
        else:
            pos_combo.addItems([str(i) for i in range(1, 8)])
        pos_combo.setFixedWidth(30)
        pos_combo.setStyleSheet(styles.get_small_combo_style())
        pos_combo.setCurrentIndex(0)
        pos_combo.currentIndexChanged.connect(
            lambda idx, c=cart_id: self._on_cart_position_changed(c, idx + 1)
        )
        card_layout.addWidget(pos_combo, 1, 1)

        # 左极限 / 右极限（放在同一行）
        llimit_btn = QPushButton("左极")
        llimit_btn.setCheckable(True)
        llimit_btn.setStyleSheet("""
            QPushButton {
                background-color: #2D2D2D;
                color: #8B949E;
                border: 1px solid #444;
                border-radius: 3px;
                font-size: 9px;
                padding: 2px 6px;
            }
            QPushButton:checked {
                background-color: #1D6;
                color: #FFFFFF;
                border: 1px solid #1D6;
            }
        """)
        llimit_btn.clicked.connect(
            lambda checked, c=cart_id: self._on_cart_limit_changed(c, 'left_limit', checked)
        )

        rlimit_btn = QPushButton("右极")
        rlimit_btn.setCheckable(True)
        rlimit_btn.setStyleSheet("""
            QPushButton {
                background-color: #2D2D2D;
                color: #8B949E;
                border: 1px solid #444;
                border-radius: 3px;
                font-size: 9px;
                padding: 2px 6px;
            }
            QPushButton:checked {
                background-color: #1D6;
                color: #FFFFFF;
                border: 1px solid #1D6;
            }
        """)
        rlimit_btn.clicked.connect(
            lambda checked, c=cart_id: self._on_cart_limit_changed(c, 'right_limit', checked)
        )
        card_layout.addWidget(llimit_btn, 2, 0)
        card_layout.addWidget(rlimit_btn, 2, 1)

        # 左分料 / 右分料（放在同一行）
        ldiv_btn = QPushButton("左分")
        ldiv_btn.setCheckable(True)
        ldiv_btn.setStyleSheet("""
            QPushButton {
                background-color: #2D2D2D;
                color: #8B949E;
                border: 1px solid #444;
                border-radius: 3px;
                font-size: 9px;
                padding: 2px 6px;
            }
            QPushButton:checked {
                background-color: #27AE60;
                color: #FFFFFF;
                border: 1px solid #27AE60;
            }
        """)
        ldiv_btn.clicked.connect(
            lambda checked, c=cart_id: self._on_cart_divert_changed(c, 'left_divert', checked)
        )

        rdiv_btn = QPushButton("右分")
        rdiv_btn.setCheckable(True)
        rdiv_btn.setStyleSheet("""
            QPushButton {
                background-color: #2D2D2D;
                color: #8B949E;
                border: 1px solid #444;
                border-radius: 3px;
                font-size: 9px;
                padding: 2px 6px;
            }
            QPushButton:checked {
                background-color: #27AE60;
                color: #FFFFFF;
                border: 1px solid #27AE60;
            }
        """)
        rdiv_btn.clicked.connect(
            lambda checked, c=cart_id: self._on_cart_divert_changed(c, 'right_divert', checked)
        )
        card_layout.addWidget(ldiv_btn, 3, 0)
        card_layout.addWidget(rdiv_btn, 3, 1)

        # 应用按钮（正方形，固定在右侧）
        apply_btn = QPushButton("应用")
        apply_btn.setFixedSize(34, 34)
        apply_btn.setStyleSheet(styles.get_small_button_style('#27AE60'))
        apply_btn.clicked.connect(lambda _, c=cart_id: self._write_cart_init_data(c))
        card_layout.addWidget(apply_btn, 0, 2, 4, 1, alignment=Qt.AlignVCenter)

        # 保存控件引用
        self.cart_sensor_controls[cart_id] = {
            'position_combo': pos_combo,
            'llimit_btn': llimit_btn,
            'rlimit_btn': rlimit_btn,
            'ldiv_btn': ldiv_btn,
            'rdiv_btn': rdiv_btn,
        }

        return card, apply_btn

    def _on_cart_position_changed(self, cart_id: str, position: int):
        """小车位置改变"""
        self.cart_sensor_changed.emit(cart_id, {'position': position})

        # 小车4有特殊的位置控制逻辑
        if cart_id == 'Cart4':
            if hasattr(self, '_controller') and self._controller:
                self._controller.set_cart4_target_position(position)

    def _on_cart_limit_changed(self, cart_id: str, sensor_type: str, value: bool):
        """小车极限传感器改变"""
        self.cart_sensor_changed.emit(cart_id, {sensor_type: value})

    def _on_cart_divert_changed(self, cart_id: str, sensor_type: str, value: bool):
        """小车分料传感器改变"""
        self.cart_sensor_changed.emit(cart_id, {sensor_type: value})

    def _write_cart_init_data(self, cart_id: str):
        """将单个小车的初始化数据写入generate_data.json，并同步到控制器"""
        controls = self.cart_sensor_controls[cart_id]
        position = controls['position_combo'].currentIndex() + 1
        left_limit = controls['llimit_btn'].isChecked()
        right_limit = controls['rlimit_btn'].isChecked()
        left_divert = controls['ldiv_btn'].isChecked()
        right_divert = controls['rdiv_btn'].isChecked()
        self._sensor_data_manager.write_all_cart_sensors(
            cart_id, position, left_limit, right_limit, left_divert, right_divert
        )
        # 同步到控制器内存（Cart1/2/3），Cart4 在 _on_cart_position_changed 中已处理
        if hasattr(self, '_controller') and self._controller and cart_id != 'Cart4':
            self._controller.cart_positions[cart_id] = position
            self._controller.cart_target_positions[cart_id] = position
            self._controller.cart_sensor_positions[cart_id] = position
            self._controller.cart_divert[cart_id] = (left_divert, right_divert)
        controls['apply_btn'].setText("已应用")
        controls['apply_btn'].setEnabled(False)
        self._cart_init_written.add(cart_id)

    def _create_route_control_group(self) -> QGroupBox:
        """创建上料路线控制组"""
        group = QGroupBox("上料路线控制")
        group.setStyleSheet(styles.get_group_box_style())
        layout = QVBoxLayout()
        layout.setSpacing(4)

        # 9条路线分三列显示
        routes = list(config.FEED_ROUTES.items())
        for i in range(0, len(routes), 3):
            row_layout = QHBoxLayout()
            row_layout.setSpacing(4)

            for j in range(3):
                if i + j < len(routes):
                    route_id, route_info = routes[i + j]
                    btn = self._create_route_button(route_id, route_info)
                    self.route_buttons[route_id] = btn
                    row_layout.addWidget(btn)

            layout.addLayout(row_layout)

        group.setLayout(layout)
        return group

    def _create_route_button(self, route_id: str, route_info: dict) -> QPushButton:
        """创建路线按钮"""
        btn = QPushButton(route_info['name'])
        btn.setMinimumHeight(36)
        btn.setCheckable(True)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #2C3E50;
                color: #BDC3C7;
                border: 1px solid #34495E;
                border-radius: 4px;
                padding: 6px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #34495E;
                border-color: #4A90D9;
            }
            QPushButton:checked {
                background-color: #27AE60;
                color: white;
                border-color: #2ECC71;
            }
        """)
        btn.clicked.connect(lambda checked, rid=route_id: self._on_route_clicked(rid, checked))
        return btn

    def _create_operation_group(self) -> QGroupBox:
        """创建操作按钮组"""
        group = QGroupBox("系统操作")
        group.setStyleSheet(styles.get_group_box_style())
        layout = QVBoxLayout()
        layout.setSpacing(8)

        # 停止按钮
        stop_btn = QPushButton("停止")
        stop_btn.setMinimumHeight(36)
        stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                border: none;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
            QPushButton:pressed {
                background-color: #A93226;
            }
            QPushButton:disabled {
                background-color: #555;
                color: #999;
            }
        """)
        stop_btn.clicked.connect(self._on_stop_route_dialog)
        layout.addWidget(stop_btn)

        # 与下位机通信按钮
        self.tcp_btn = QPushButton("与下位机通信：关")
        self.tcp_btn.setCheckable(True)
        self.tcp_btn.setChecked(False)
        self.tcp_btn.setMinimumHeight(36)
        self.tcp_btn.setStyleSheet("""
            QPushButton {
                background-color: #2C3E50;
                color: #8B949E;
                border: 2px solid #34495E;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #34495E;
                border-color: #4A90D9;
            }
            QPushButton:checked {
                background-color: #1B5E20;
                color: #00FF00;
                border-color: #00FF00;
            }
            QPushButton:checked:hover {
                background-color: #2E7D32;
            }
        """)
        self.tcp_btn.clicked.connect(self._on_tcp_toggled)
        layout.addWidget(self.tcp_btn)

        # UDP 二进制发送按钮
        self.udp_btn = QPushButton("UDP 二进制发送：关")
        self.udp_btn.setCheckable(True)
        self.udp_btn.setChecked(False)
        self.udp_btn.setMinimumHeight(36)
        self.udp_btn.setStyleSheet("""
            QPushButton {
                background-color: #2C3E50;
                color: #8B949E;
                border: 2px solid #34495E;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #34495E;
                border-color: #4A90D9;
            }
            QPushButton:checked {
                background-color: #1B5E20;
                color: #00FF00;
                border-color: #00FF00;
            }
            QPushButton:checked:hover {
                background-color: #2E7D32;
            }
        """)
        self.udp_btn.clicked.connect(self._on_udp_toggled)
        layout.addWidget(self.udp_btn)

        # ---- 诊断模式选择 ----
        diag_mode_label = QLabel("诊断模式")
        diag_mode_label.setStyleSheet("color: #8B949E; font-weight: bold; font-size: 12px; margin-top: 4px;")
        layout.addWidget(diag_mode_label)

        diag_mode_layout = QHBoxLayout()
        self.diag_local_radio = QRadioButton("本地诊断")
        self.diag_local_radio.setChecked(True)
        self.diag_local_radio.setStyleSheet("color: #BDC3C7; font-size: 12px;")
        self.diag_local_radio.toggled.connect(self._on_diagnosis_mode_toggled)
        diag_mode_layout.addWidget(self.diag_local_radio)

        self.diag_tcp_radio = QRadioButton("TCP 远程诊断")
        self.diag_tcp_radio.setStyleSheet("color: #BDC3C7; font-size: 12px;")
        self.diag_tcp_radio.toggled.connect(self._on_diagnosis_mode_toggled)
        diag_mode_layout.addWidget(self.diag_tcp_radio)
        layout.addLayout(diag_mode_layout)

        # ---- TCP 诊断服务连接按钮 ----
        self.diag_tcp_btn = QPushButton("诊断服务：断开")
        self.diag_tcp_btn.setCheckable(True)
        self.diag_tcp_btn.setChecked(False)
        self.diag_tcp_btn.setEnabled(False)
        self.diag_tcp_btn.setMinimumHeight(34)
        self.diag_tcp_btn.setStyleSheet("""
            QPushButton {
                background-color: #2C3E50;
                color: #8B949E;
                border: 2px solid #34495E;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #34495E;
                border-color: #4A90D9;
            }
            QPushButton:checked {
                background-color: #1B5E20;
                color: #00FF00;
                border-color: #00FF00;
            }
            QPushButton:disabled {
                background-color: #1a1a2e;
                color: #555;
                border-color: #333;
            }
        """)
        self.diag_tcp_btn.clicked.connect(self._on_diagnosis_tcp_toggled)
        layout.addWidget(self.diag_tcp_btn)

        self.diag_tcp_status = QLabel("状态：未连接")
        self.diag_tcp_status.setStyleSheet("color: #6E7681; font-size: 11px;")
        layout.addWidget(self.diag_tcp_status)

        # ---- TCP 调度服务连接按钮 ----
        self.sched_tcp_btn = QPushButton("调度服务：断开")
        self.sched_tcp_btn.setCheckable(True)
        self.sched_tcp_btn.setChecked(False)
        self.sched_tcp_btn.setMinimumHeight(34)
        self.sched_tcp_btn.setStyleSheet("""
            QPushButton {
                background-color: #2C3E50;
                color: #8B949E;
                border: 2px solid #34495E;
                border-radius: 5px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #34495E;
                border-color: #4A90D9;
            }
            QPushButton:checked {
                background-color: #1B5E20;
                color: #00FF00;
                border-color: #00FF00;
            }
        """)
        self.sched_tcp_btn.clicked.connect(self._on_scheduling_tcp_toggled)
        layout.addWidget(self.sched_tcp_btn)

        self.sched_tcp_status = QLabel("状态：D6○ D7○ D8○ D9○")
        self.sched_tcp_status.setStyleSheet("color: #6E7681; font-size: 11px;")
        layout.addWidget(self.sched_tcp_status)

        # ---- 手动/自动模式切换按钮 ----
        self.auto_mode_btn = QPushButton("手动模式")
        self.auto_mode_btn.setCheckable(True)
        self.auto_mode_btn.setChecked(False)
        self.auto_mode_btn.setMinimumHeight(36)
        self.auto_mode_btn.setStyleSheet("""
            QPushButton {
                background-color: #1A5276;
                color: #85C1E9;
                border: 2px solid #2E86C1;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2E86C1;
                border-color: #3498DB;
            }
            QPushButton:checked {
                background-color: #1B5E20;
                color: #00FF00;
                border-color: #00FF00;
            }
        """)
        self.auto_mode_btn.clicked.connect(self._on_auto_mode_toggled)
        layout.addWidget(self.auto_mode_btn)

        # 系统复位按钮
        reset_btn = QPushButton("系统复位")
        reset_btn.setMinimumHeight(36)
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #9B59B6;
                color: white;
                border: none;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #8E44AD;
            }
            QPushButton:pressed {
                background-color: #7D3C98;
            }
        """)
        reset_btn.clicked.connect(self._on_reset_clicked)
        layout.addWidget(reset_btn)

        group.setLayout(layout)
        return group

    def _create_fault_diagnosis_group(self) -> QGroupBox:
        """创建传感器故障诊断组"""
        group = QGroupBox("故障模拟")
        group.setStyleSheet(styles.get_group_box_style())
        layout = QVBoxLayout()
        layout.setSpacing(8)

        # ===== 接近开关故障 (诊断类别: proximity) =====
        sensor_fault_label = QLabel("接近开关故障 → 诊断: 卡低(0.90)/卡高(0.90)")
        sensor_fault_label.setStyleSheet("color: #4A90D9; font-weight: bold; font-size: 11px;")
        sensor_fault_label.setToolTip("诊断规则（仅取上游邻位传感器）:\n- 上游邻居true稳定10s + 本传感器false持续30s → stuck_low (0.90)\n- 上游邻居false稳定10s + 本传感器true持续30s → stuck_high (0.90)")
        layout.addWidget(sensor_fault_label)

        # 故障模式选择
        mode_layout = QHBoxLayout()
        mode_label = QLabel("故障模式:")
        mode_label.setStyleSheet("color: #8B949E; font-size: 11px;")
        mode_layout.addWidget(mode_label)

        self.fault_mode_combo = QComboBox()
        self.fault_mode_combo.addItems([
            "关闭",
            "卡在低电平(常0)",
            "卡在高电平(常1)",
            "灵敏度降低",
            "响应延迟",
            "间歇性故障"
        ])
        self.fault_mode_combo.setStyleSheet(styles.get_combo_box_style())
        self.fault_mode_combo.setFixedHeight(28)
        mode_layout.addWidget(self.fault_mode_combo, 1)
        layout.addLayout(mode_layout)

        # 故障数量选择
        count_layout = QHBoxLayout()
        count_label = QLabel("故障数量:")
        count_label.setStyleSheet("color: #8B949E; font-size: 11px;")
        count_layout.addWidget(count_label)

        self.fault_count_combo = QComboBox()
        self.fault_count_combo.addItems(["1个", "2个"])
        self.fault_count_combo.setStyleSheet(styles.get_combo_box_style())
        self.fault_count_combo.setFixedHeight(28)
        count_layout.addWidget(self.fault_count_combo, 1)
        layout.addLayout(count_layout)

        # ===== 中转斗故障 (诊断类别: hopper_switch / hopper_weight) =====
        hopper_fault_label = QLabel("中转斗故障 → 诊断: 卡关(0.85)/卡开(0.85)/称重异常(0.80)")
        hopper_fault_label.setStyleSheet("color: #8E44AD; font-weight: bold; font-size: 11px;")
        hopper_fault_label.setContentsMargins(0, 10, 0, 0)
        hopper_fault_label.setToolTip("诊断规则:\n- 开关开+称重递增+下游无物料 → hopper_switch_stuck_closed (0.85)\n- 开关关+下游有物料+称重≈0 → hopper_switch_stuck_open (0.85)\n- 称重不变+应有物料进入 → weight_stuck (0.80)")
        layout.addWidget(hopper_fault_label)

        # 中转斗选择
        hopper_select_layout = QHBoxLayout()
        hopper_select_label = QLabel("选择斗:")
        hopper_select_label.setStyleSheet("color: #8B949E; font-size: 11px;")
        hopper_select_layout.addWidget(hopper_select_label)

        self.hopper_select_combo = QComboBox()
        self.hopper_select_combo.addItems([
            "全部",
            "中转斗1",
            "中转斗2",
            "中转斗3",
            "中转斗4",
            "中转斗5",
            "中转斗6",
            "中转斗7"
        ])
        self.hopper_select_combo.setStyleSheet(styles.get_combo_box_style())
        self.hopper_select_combo.setFixedHeight(28)
        hopper_select_layout.addWidget(self.hopper_select_combo, 1)
        layout.addLayout(hopper_select_layout)

        # 中转斗故障类型选择（括号内为对应的诊断规则+置信度）
        self.hopper_fault_combo = QComboBox()
        self.hopper_fault_combo.addItems([
            "无故障",
            "开关卡在关 → 诊断: 卡关(0.85)",
            "开关卡在开 → 诊断: 卡开(0.85)",
            "称重显示0 → 诊断: 称重卡住(0.80)",
            "称重偏移 → 诊断: 变化率异常(0.70)",
        ])
        self.hopper_fault_combo.setStyleSheet(styles.get_combo_box_style())
        self.hopper_fault_combo.setFixedHeight(28)
        layout.addWidget(self.hopper_fault_combo)

        # 故障状态显示（增大显示空间）
        self.fault_status_label = QLabel("当前无故障设置")
        self.fault_status_label.setStyleSheet("""
            QLabel {
                color: #8B949E;
                font-size: 10px;
                padding: 8px;
                background-color: #21262d;
                border-radius: 4px;
                min-height: 40px;
            }
        """)
        self.fault_status_label.setWordWrap(True)
        self.fault_status_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(self.fault_status_label)

        # 按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self.fault_apply_btn = QPushButton("应用设置")
        self.fault_apply_btn.setMinimumHeight(30)
        self.fault_apply_btn.setStyleSheet(styles.get_button_style('#E67E22'))
        self.fault_apply_btn.clicked.connect(self._on_apply_fault)
        btn_layout.addWidget(self.fault_apply_btn)

        self.fault_clear_btn = QPushButton("清除故障")
        self.fault_clear_btn.setMinimumHeight(30)
        self.fault_clear_btn.setStyleSheet(styles.get_button_style('#9B59B6'))
        self.fault_clear_btn.clicked.connect(self._on_clear_fault)
        btn_layout.addWidget(self.fault_clear_btn)

        layout.addLayout(btn_layout)

        # 诊断信息提示
        diagnosis_tip = QLabel(
            "诊断引擎(独立模块) 6类规则:\n"
            "接近开关: 邻居全true+本false持续30s→卡低(0.90) | 邻居全false+本true持续30s→卡高(0.90)\n"
            "中转斗开关: 开关开+称重增+下游无→卡关(0.85) | 开关关+下游有+称重≈0→卡开(0.85)\n"
            "中转斗称重: 变化率异常(0.70) | 卡住无变化(0.80) | 抖动(0.60) | 开关开称重非零(0.65)\n"
            "小车传感器: 极限互斥(0.95) | 分料互斥(0.95)\n"
            "皮带转速: 运行为0(0.90) | 停止非0(0.90) | 波动>30%(0.50)\n"
            "跨传感器: 开关称重矛盾(0.75) | 全false(0.55) | 时序异常(0.70)"
        )
        diagnosis_tip.setStyleSheet("""
            QLabel {
                color: #6E7681;
                font-size: 9px;
                padding: 4px;
            }
        """)
        diagnosis_tip.setWordWrap(True)
        layout.addWidget(diagnosis_tip)

        # ===== 皮带故障 (诊断类别: conveyor) =====
        conveyor_fault_label = QLabel("皮带转速故障 → 诊断: 运行为0(0.90)/停止非0(0.90)/波动(0.50)")
        conveyor_fault_label.setStyleSheet("color: #E74C3C; font-weight: bold; font-size: 11px;")
        conveyor_fault_label.setContentsMargins(0, 10, 0, 0)
        conveyor_fault_label.setToolTip("诊断规则（均需持续10s以上）:\n- 皮带运行+转速=0 → speed_zero_while_running (0.90)\n- 皮带停止+转速≠0 → speed_nonzero_while_stopped (0.90)\n- 匀速阶段波动>30% → speed_volatile (0.50)")
        layout.addWidget(conveyor_fault_label)

        # 皮带选择
        conv_select_layout = QHBoxLayout()
        conv_select_label = QLabel("选择皮带:")
        conv_select_label.setStyleSheet("color: #8B949E; font-size: 11px;")
        conv_select_layout.addWidget(conv_select_label)

        self.conveyor_fault_combo = QComboBox()
        self.conveyor_fault_combo.addItems([
            "无故障",
            "E1", "E2", "E4", "E5", "E6", "E7", "E8", "E9", "E10",
            "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D13"
        ])
        self.conveyor_fault_combo.setStyleSheet(styles.get_combo_box_style())
        self.conveyor_fault_combo.setFixedHeight(28)
        conv_select_layout.addWidget(self.conveyor_fault_combo, 1)
        layout.addLayout(conv_select_layout)

        # 皮带故障类型选择（诊断对齐）
        self.conveyor_fault_type_combo = QComboBox()
        self.conveyor_fault_type_combo.addItems([
            "正常（跟随仿真）",
            "皮带运行但转速为0 → 诊断: 运行为0(0.90,持续10s)",
            "皮带停止但转速非0 → 诊断: 停止非0(0.90,持续10s)",
            "皮带转速波动 → 诊断: 波动(0.50,持续10s)",
        ])
        self.conveyor_fault_type_combo.setStyleSheet(styles.get_combo_box_style())
        self.conveyor_fault_type_combo.setFixedHeight(28)
        layout.addWidget(self.conveyor_fault_type_combo)

        # 皮带故障状态显示
        self.conveyor_fault_status_label = QLabel("当前无皮带故障")
        self.conveyor_fault_status_label.setStyleSheet("""
            QLabel {
                color: #8B949E;
                font-size: 10px;
                padding: 6px;
                background-color: #21262d;
                border-radius: 4px;
                min-height: 30px;
            }
        """)
        self.conveyor_fault_status_label.setWordWrap(True)
        layout.addWidget(self.conveyor_fault_status_label)

        # 皮带故障按钮行
        conv_btn_layout = QHBoxLayout()
        conv_btn_layout.setSpacing(6)

        conv_apply_btn = QPushButton("应用")
        conv_apply_btn.setMinimumHeight(28)
        conv_apply_btn.setStyleSheet(styles.get_button_style('#E67E22'))
        conv_apply_btn.clicked.connect(self._on_apply_conveyor_fault)
        conv_btn_layout.addWidget(conv_apply_btn)

        conv_clear_btn = QPushButton("清除")
        conv_clear_btn.setMinimumHeight(28)
        conv_clear_btn.setStyleSheet(styles.get_button_style('#9B59B6'))
        conv_clear_btn.clicked.connect(self._on_clear_conveyor_fault)
        conv_btn_layout.addWidget(conv_clear_btn)

        layout.addLayout(conv_btn_layout)

        # ===== 小车传感器故障 (诊断类别: cart) =====
        cart_fault_label = QLabel("小车传感器故障 → 诊断: 极限互斥(0.95)/分料互斥(0.95)")
        cart_fault_label.setStyleSheet("color: #3498DB; font-weight: bold; font-size: 11px;")
        cart_fault_label.setContentsMargins(0, 10, 0, 0)
        cart_fault_label.setToolTip("诊断规则:\n- 左右极限同时true → limit_mutual_exclusion (0.95)\n- 左右分料同时true → divert_mutual_exclusion (0.95)")
        layout.addWidget(cart_fault_label)

        # 小车选择
        cart_select_layout = QHBoxLayout()
        cart_select_label = QLabel("选择小车:")
        cart_select_label.setStyleSheet("color: #8B949E; font-size: 11px;")
        cart_select_layout.addWidget(cart_select_label)

        self.cart_select_combo = QComboBox()
        self.cart_select_combo.addItems(["小车1", "小车2", "小车3", "小车4"])
        self.cart_select_combo.setStyleSheet(styles.get_combo_box_style())
        self.cart_select_combo.setFixedHeight(28)
        cart_select_layout.addWidget(self.cart_select_combo, 1)
        layout.addLayout(cart_select_layout)

        # 传感器类型选择
        sensor_type_layout = QHBoxLayout()
        sensor_type_label = QLabel("传感器类型:")
        sensor_type_label.setStyleSheet("color: #8B949E; font-size: 11px;")
        sensor_type_layout.addWidget(sensor_type_label)

        self.cart_sensor_type_combo = QComboBox()
        self.cart_sensor_type_combo.addItems([
            "位置传感器",
            "左极限传感器",
            "右极限传感器",
            "左分料传感器",
            "右分料传感器",
        ])
        self.cart_sensor_type_combo.setStyleSheet(styles.get_combo_box_style())
        self.cart_sensor_type_combo.setFixedHeight(28)
        self.cart_sensor_type_combo.currentIndexChanged.connect(self._on_cart_sensor_type_changed)
        sensor_type_layout.addWidget(self.cart_sensor_type_combo, 1)
        layout.addLayout(sensor_type_layout)

        # 故障类型选择（动态变化）
        fault_type_layout = QHBoxLayout()
        fault_type_label = QLabel("故障类型:")
        fault_type_label.setStyleSheet("color: #8B949E; font-size: 11px;")
        fault_type_layout.addWidget(fault_type_label)

        self.cart_fault_type_combo = QComboBox()
        self.cart_fault_type_combo.setStyleSheet(styles.get_combo_box_style())
        self.cart_fault_type_combo.setFixedHeight(28)
        self.cart_fault_type_combo.currentIndexChanged.connect(self._update_cart_fault_extra_visibility)
        fault_type_layout.addWidget(self.cart_fault_type_combo, 1)
        layout.addLayout(fault_type_layout)

        # 初始化位置传感器故障类型列表
        self._update_cart_fault_type_combo(0)

        # 卡死值/偏移量设置（仅位置传感器卡死故障和定位不准时显示）
        self.cart_fault_extra_widget = QWidget()
        extra_layout = QHBoxLayout(self.cart_fault_extra_widget)
        extra_layout.setContentsMargins(0, 0, 0, 0)

        extra_label = QLabel("参数:")
        extra_label.setStyleSheet("color: #8B949E; font-size: 11px;")
        extra_layout.addWidget(extra_label)

        self.cart_fault_extra_combo = QComboBox()
        self.cart_fault_extra_combo.setStyleSheet(styles.get_combo_box_style())
        self.cart_fault_extra_combo.setFixedHeight(28)
        extra_layout.addWidget(self.cart_fault_extra_combo, 1)

        self.cart_fault_extra_widget.setVisible(False)
        layout.addWidget(self.cart_fault_extra_widget)

        # 小车故障状态显示
        self.cart_fault_status_label = QLabel("当前无小车传感器故障")
        self.cart_fault_status_label.setStyleSheet("""
            QLabel {
                color: #8B949E;
                font-size: 10px;
                padding: 6px;
                background-color: #21262d;
                border-radius: 4px;
                min-height: 30px;
            }
        """)
        self.cart_fault_status_label.setWordWrap(True)
        layout.addWidget(self.cart_fault_status_label)

        # 小车故障按钮行
        cart_btn_layout = QHBoxLayout()
        cart_btn_layout.setSpacing(6)

        cart_apply_btn = QPushButton("应用")
        cart_apply_btn.setMinimumHeight(28)
        cart_apply_btn.setStyleSheet(styles.get_button_style('#E67E22'))
        cart_apply_btn.clicked.connect(self._on_apply_cart_fault)
        cart_btn_layout.addWidget(cart_apply_btn)

        cart_clear_btn = QPushButton("清除")
        cart_clear_btn.setMinimumHeight(28)
        cart_clear_btn.setStyleSheet(styles.get_button_style('#9B59B6'))
        cart_clear_btn.clicked.connect(self._on_clear_cart_fault_btn)
        cart_btn_layout.addWidget(cart_clear_btn)

        layout.addLayout(cart_btn_layout)

        group.setLayout(layout)
        return group

    def _create_maintenance_group(self) -> QGroupBox:
        """创建检修设置组"""
        group = QGroupBox("检修设置")
        group.setStyleSheet(styles.get_group_box_style())
        layout = QVBoxLayout()
        layout.setSpacing(6)

        # ---- 产线检修 ----
        line_label = QLabel("产线检修（该产线全部4个料仓检修）")
        line_label.setStyleSheet("color: #F39C12; font-size: 10px;")
        layout.addWidget(line_label)

        line_row = QHBoxLayout()
        self.maintenance_line_combo = QComboBox()
        self.maintenance_line_combo.setStyleSheet(styles.get_combo_box_style())
        self.maintenance_line_combo.setFixedHeight(28)
        for i in range(1, 8):
            self.maintenance_line_combo.addItem(f"产线 {i}", i)
        line_row.addWidget(self.maintenance_line_combo, 1)

        add_line_btn = QPushButton("添加")
        add_line_btn.setMinimumHeight(28)
        add_line_btn.setStyleSheet(styles.get_button_style('#F39C12'))
        add_line_btn.clicked.connect(self._on_add_maintenance_line)
        line_row.addWidget(add_line_btn)
        layout.addLayout(line_row)

        # ---- 料仓检修 ----
        bin_label = QLabel("料仓检修（单个料仓）")
        bin_label.setStyleSheet("color: #F39C12; font-size: 10px;")
        layout.addWidget(bin_label)

        bin_row = QHBoxLayout()
        self.maintenance_bin_combo = QComboBox()
        self.maintenance_bin_combo.setStyleSheet(styles.get_combo_box_style())
        self.maintenance_bin_combo.setFixedHeight(28)
        all_bins = []
        for col in ['P1', 'P2', 'P3', 'P4']:
            for row in range(1, 8):
                all_bins.append(f"{col}-{row}")
        for i in range(1, 13):
            all_bins.append(f"S{i}")
        for b in all_bins:
            self.maintenance_bin_combo.addItem(b, b)
        bin_row.addWidget(self.maintenance_bin_combo, 1)

        add_bin_btn = QPushButton("添加")
        add_bin_btn.setMinimumHeight(28)
        add_bin_btn.setStyleSheet(styles.get_button_style('#F39C12'))
        add_bin_btn.clicked.connect(self._on_add_maintenance_bin)
        bin_row.addWidget(add_bin_btn)
        layout.addLayout(bin_row)

        # ---- 当前检修列表 ----
        self.maintenance_list_label = QLabel("当前检修：无")
        self.maintenance_list_label.setStyleSheet("color: #E74C3C; font-size: 10px;")
        self.maintenance_list_label.setWordWrap(True)
        layout.addWidget(self.maintenance_list_label)

        clear_btn = QPushButton("清除全部检修")
        clear_btn.setMinimumHeight(28)
        clear_btn.setStyleSheet(styles.get_button_style('#E74C3C'))
        clear_btn.clicked.connect(self._on_clear_maintenance)
        layout.addWidget(clear_btn)

        group.setLayout(layout)
        return group

    def _on_add_maintenance_line(self):
        line_num = self.maintenance_line_combo.currentData()
        if line_num:
            self.maintenance_line_added.emit(line_num)

    def _on_add_maintenance_bin(self):
        bin_id = self.maintenance_bin_combo.currentData()
        if bin_id:
            bin = str(bin_id)
            if bin.startswith('S'):
                self.maintenance_bin_added.emit(bin)
            else:
                self.maintenance_bin_added.emit(bin)

    def _on_clear_maintenance(self):
        self.maintenance_clear_requested.emit()

    def set_maintenance_list(self, bins: list):
        if bins:
            self.maintenance_list_label.setText("当前检修：" + "、".join(bins))
        else:
            self.maintenance_list_label.setText("当前检修：无")

    def _on_route_clicked(self, route_id: str, checked: bool):
        """路线按钮点击"""
        if checked:
            # 需要选择小仓的路线，先弹出选择对话框
            if route_id in ROUTES_REQUIRING_BIN_SELECTION:
                target_conveyor = self._get_target_conveyor(route_id)
                available_bins = self._get_available_bins(route_id)
                route_name = config.FEED_ROUTES[route_id]['name']

                dialog = SmallBinSelectDialog(
                    route_id, route_name, target_conveyor, available_bins, self
                )
                dialog.bin_selected.connect(self._on_bin_selected_from_dialog)
                result = dialog.exec_()

                if result != dialog.Accepted or not dialog.get_selected_bin():
                    # 用户取消选择，复位按钮状态
                    self.route_buttons[route_id].setChecked(False)
                    return

            self.active_routes.add(route_id)
        else:
            self.active_routes.discard(route_id)
            # 清除该路线的小仓映射
            if route_id in self.route_to_bin:
                del self.route_to_bin[route_id]
        self.route_toggled.emit(route_id, checked)

    def _on_bin_selected_from_dialog(self, route_id: str, bin_id: str):
        """从小仓选择对话框接收选择"""
        self.route_to_bin[route_id] = bin_id
        self.route_bin_selected.emit(route_id, bin_id)

        # 如果是路线⑤（D6皮带 -> 高位储料仓），控制小车4移动到对应位置
        if route_id == 'route5':
            # 从bin_id（如'S5'）提取列号
            # S1-S6在第1行，S7-S12在第2行
            silo_num = int(bin_id[1:]) if bin_id.startswith('S') else 1
            # 计算小车4的位置（1-6）
            # 位置1-3: 第1行（S1-S3左，S4-S6右分料）
            # 位置4-6: 第2行（S7-S9左，S10-S12右分料）
            # 但用户说左分料为S1-S6，右分料为S7-S12
            # 所以位置1对应S1/S7, 位置2对应S2/S8, ..., 位置6对应S6/S12
            if 1 <= silo_num <= 12:
                # 列号从1开始，(1-1)%6+1=1, (6-1)%6+1=6, (7-1)%6+1=1, (12-1)%6+1=6
                cart4_pos = (silo_num - 1) % 6 + 1
                if hasattr(self, '_controller') and self._controller:
                    self._controller.set_cart4_target_position(cart4_pos)

    def _get_target_conveyor(self, route_id: str) -> str:
        """获取路线终点皮带"""
        route = config.FEED_ROUTES[route_id]
        conveyors = route['conveyors']
        if not conveyors:
            return ''
        return conveyors[-1]  # 终点皮带

    def _get_available_bins(self, route_id: str) -> List[str]:
        """获取路线的可用小仓列表"""
        import pos

        target_conveyor = self._get_target_conveyor(route_id)
        if target_conveyor in pos.CONVEYOR_TO_BINS:
            return pos.CONVEYOR_TO_BINS[target_conveyor]
        return []

    def _on_speed_changed(self, value: int):
        """速度滑块改变"""
        speed = value / 10.0
        self.speed_label.setText(f"{speed:.1f} m/s")
        self.speed_changed.emit(speed)

    def _on_start_all_routes(self):
        """启动所有路线"""
        for route_id in config.FEED_ROUTES.keys():
            if route_id not in self.active_routes:
                self.active_routes.add(route_id)
                self.route_buttons[route_id].setChecked(True)
                self.route_toggled.emit(route_id, True)

    def _on_stop_all_routes(self):
        """停止所有路线"""
        for route_id in list(self.active_routes):
            self.active_routes.discard(route_id)
            self.route_buttons[route_id].setChecked(False)
            self.route_toggled.emit(route_id, False)

    def _on_stop_route_dialog(self):
        """停止按钮点击 - 弹出对话框选择停止哪条路线"""
        if not self.active_routes:
            QMessageBox.information(self, "提示", "当前没有运行中的上料路线。")
            return

        # 构建选项列表
        route_list = sorted(self.active_routes)
        route_names = [
            f"{rid} {config.FEED_ROUTES[rid]['name']}" for rid in route_list
        ]

        # 使用自定义对话框
        from PyQt5.QtWidgets import QDialog, QListWidget, QListWidgetItem, QDialogButtonBox, QCheckBox

        dialog = QDialog(self)
        dialog.setWindowTitle("选择要停止的路线")
        dialog.setMinimumWidth(320)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #1E1E1E;
                color: #E6EDF3;
            }
            QLabel {
                color: #8B949E;
                font-size: 12px;
            }
            QListWidget {
                background-color: #2C3E50;
                color: #E6EDF3;
                border: 1px solid #34495E;
                border-radius: 4px;
                font-size: 12px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 6px;
                border-bottom: 1px solid #34495E;
            }
            QListWidget::item:hover {
                background-color: #34495E;
            }
            QCheckBox {
                color: #E6EDF3;
                font-size: 12px;
            }
            QPushButton {
                background-color: #2C3E50;
                color: #E6EDF3;
                border: 1px solid #34495E;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #34495E;
                border-color: #4A90D9;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)

        # 提示标签
        tip_label = QLabel("请勾选要停止的路线（可多选）：")
        layout.addWidget(tip_label)

        # 路线列表
        list_widget = QListWidget()
        for i, rname in enumerate(route_names):
            item = QListWidgetItem(rname)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, route_list[i])
            list_widget.addItem(item)
        layout.addWidget(list_widget)

        # 全选复选框
        select_all_cb = QCheckBox("全选（全部停止）")
        select_all_cb.setStyleSheet("color: #E74C3C; font-weight: bold;")
        select_all_cb.toggled.connect(
            lambda checked: self._toggle_all_items(list_widget, checked)
        )
        layout.addWidget(select_all_cb)

        # 按钮
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = btn_box.button(QDialogButtonBox.Ok)
        ok_btn.setText("停止选中")
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
        """)
        cancel_btn = btn_box.button(QDialogButtonBox.Cancel)
        cancel_btn.setText("取消")
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)

        if dialog.exec_() == QDialog.Accepted:
            selected_routes = []
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                if item.checkState() == Qt.Checked:
                    selected_routes.append(item.data(Qt.UserRole))

            if not selected_routes:
                return

            for route_id in selected_routes:
                self.active_routes.discard(route_id)
                self.route_buttons[route_id].setChecked(False)
                if route_id in self.route_to_bin:
                    del self.route_to_bin[route_id]
                self.route_toggled.emit(route_id, False)

    def _toggle_all_items(self, list_widget, checked: bool):
        """切换列表中所有项的选中状态"""
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(list_widget.count()):
            list_widget.item(i).setCheckState(state)

    def _on_tcp_toggled(self, checked: bool):
        """下位机通信按钮切换"""
        if checked:
            self.tcp_btn.setText("与下位机通信：开")
        else:
            self.tcp_btn.setText("与下位机通信：关")
        self.tcp_communication_toggled.emit(checked)

    def set_tcp_status(self, connected: bool):
        """更新 TCP 通信按钮状态（由外部调用）"""
        self.tcp_btn.setChecked(connected)
        if connected:
            self.tcp_btn.setText("与下位机通信：开")
        else:
            self.tcp_btn.setText("与下位机通信：关")

    def _on_udp_toggled(self, checked: bool):
        """UDP 二进制发送按钮切换"""
        if checked:
            self.udp_btn.setText("UDP 二进制发送：开")
        else:
            self.udp_btn.setText("UDP 二进制发送：关")
        self.udp_sender_toggled.emit(checked)

    def set_udp_status(self, active: bool):
        """更新 UDP 发送按钮状态（由外部调用）"""
        self.udp_btn.setChecked(active)
        if active:
            self.udp_btn.setText("UDP 二进制发送：开")
        else:
            self.udp_btn.setText("UDP 二进制发送：关")

    def _on_diagnosis_mode_toggled(self):
        """诊断模式 RadioButton 切换"""
        if self.diag_tcp_radio.isChecked():
            self.diag_tcp_btn.setEnabled(True)
            self.diagnosis_mode_changed.emit("tcp")
        else:
            self.diag_tcp_btn.setEnabled(False)
            self.diag_tcp_btn.setChecked(False)
            self.diag_tcp_btn.setText("诊断服务：断开")
            self.diag_tcp_status.setText("状态：未连接")
            self.diagnosis_mode_changed.emit("local")

    def _on_diagnosis_tcp_toggled(self, checked: bool):
        """TCP 诊断服务连接按钮切换"""
        if checked:
            self.diag_tcp_btn.setText("诊断服务：连接中...")
        else:
            self.diag_tcp_btn.setText("诊断服务：断开")
            self.diag_tcp_status.setText("状态：未连接")
        self.diagnosis_tcp_toggled.emit(checked)

    def set_diagnosis_tcp_status(self, connected: bool):
        """更新诊断 TCP 连接状态（由外部调用）"""
        if connected:
            self.diag_tcp_btn.setText("诊断服务：已连接")
            self.diag_tcp_status.setText("状态：已连接")
            self.diag_tcp_status.setStyleSheet("color: #00FF00; font-size: 11px;")
        else:
            self.diag_tcp_btn.setText("诊断服务：断开")
            self.diag_tcp_status.setText("状态：未连接")
            self.diag_tcp_status.setStyleSheet("color: #6E7681; font-size: 11px;")

    def _on_scheduling_tcp_toggled(self, checked: bool):
        """TCP 调度服务连接按钮切换"""
        if checked:
            self.sched_tcp_btn.setText("调度服务：连接中...")
        else:
            self.sched_tcp_btn.setText("调度服务：断开")
            self.sched_tcp_status.setText("状态：D6○ D7○ D8○ D9○")
            self.sched_tcp_status.setStyleSheet("color: #6E7681; font-size: 11px;")
        self.scheduling_tcp_toggled.emit(checked)

    def _on_auto_mode_toggled(self, checked: bool):
        """手动/自动模式切换"""
        if checked:
            self.auto_mode_btn.setText("自动模式")
        else:
            self.auto_mode_btn.setText("手动模式")
        self.auto_mode_toggled.emit(checked)

    def set_scheduling_tcp_status(self, connections: dict):
        """更新调度 TCP 连接状态（由外部调用）
        connections: {'D7': True, 'D8': False, 'D9': True}
        """
        parts = []
        for belt_id in ['D6', 'D7', 'D8', 'D9']:
            status = "●" if connections.get(belt_id, False) else "○"
            parts.append(f"{belt_id}{status}")
        text = "状态：" + " ".join(parts)
        self.sched_tcp_status.setText(text)
        connected_count = sum(1 for v in connections.values() if v)
        if connected_count > 0:
            self.sched_tcp_status.setStyleSheet("color: #00FF00; font-size: 11px;")
            self.sched_tcp_btn.setText("调度服务：已连接")
        else:
            self.sched_tcp_status.setStyleSheet("color: #6E7681; font-size: 11px;")
            self.sched_tcp_btn.setText("调度服务：断开")

    def _on_reset_clicked(self):
        """复位按钮点击"""
        self.reset_requested.emit()

    def _on_emergency_stop(self):
        """紧急停止按钮点击（已废弃，由停止按钮替代）"""
        self.active_routes.clear()
        for btn in self.route_buttons.values():
            btn.setChecked(False)
        self.emergency_stop.emit()

    def _on_apply_fault(self):
        """应用故障设置"""
        # 获取选中的故障模式
        mode_index = self.fault_mode_combo.currentIndex()
        mode_mapping = {
            0: FaultMode.OFF,
            1: FaultMode.STUCK_LOW,
            2: FaultMode.STUCK_HIGH,
            3: FaultMode.SENSITIVITY_LOSS,
            4: FaultMode.RESPONSE_DELAY,
            5: FaultMode.INTERMITTENT,
        }
        mode = mode_mapping.get(mode_index, FaultMode.OFF)

        # 获取中转斗故障类型
        hopper_fault_index = self.hopper_fault_combo.currentIndex()
        hopper_fault_mapping = {
            0: None,
            1: 'switch_stuck_closed',
            2: 'switch_stuck_open',
            3: 'weight_stuck_zero',
            4: 'weight_offset',
        }
        hopper_fault_type = hopper_fault_mapping.get(hopper_fault_index)

        # 获取故障数量
        count_index = self.fault_count_combo.currentIndex()
        count = 1 if count_index == 0 else 2

        # 获取当前活跃路线
        active_routes = list(self.active_routes)

        if mode == FaultMode.OFF:
            self.fault_diagnosis.clear_all_faults()
            self.current_fault_count = 0
            self.fault_status_label.setText("故障已清除")
            self.fault_status_label.setStyleSheet("""
                QLabel {
                    color: #6E7681;
                    font-size: 10px;
                    padding: 4px;
                    background-color: #21262d;
                    border-radius: 4px;
                }
            """)
        else:
            self.fault_diagnosis.set_faults_on_active_routes(active_routes, mode, count)
            self.current_fault_count = len(self.fault_diagnosis.get_faulty_sensor_ids())
            faulty_sensors = list(self.fault_diagnosis.get_faulty_sensor_ids())

            mode_names = {
                FaultMode.STUCK_LOW: "卡在低电平 → 诊断: 卡低(0.90)",
                FaultMode.STUCK_HIGH: "卡在高电平 → 诊断: 卡高(0.90)",
                FaultMode.SENSITIVITY_LOSS: "灵敏度降低",
                FaultMode.RESPONSE_DELAY: "响应延迟",
                FaultMode.INTERMITTENT: "间歇性故障",
            }
            mode_name = mode_names.get(mode, "未知")

            if self.current_fault_count > 0:
                self.fault_status_label.setText(
                    f"传感器故障: {', '.join(faulty_sensors)}\n模式: {mode_name}"
                )
                self.fault_status_label.setStyleSheet("""
                    QLabel {
                        color: #E74C3C;
                        font-size: 10px;
                        padding: 4px;
                        background-color: #21262d;
                        border-radius: 4px;
                        border: 1px solid #E74C3C;
                    }
                """)
            else:
                self.fault_status_label.setText("请先启动至少一条路线")
                self.fault_status_label.setStyleSheet("""
                    QLabel {
                        color: #F39C12;
                        font-size: 10px;
                        padding: 4px;
                        background-color: #21262d;
                        border-radius: 4px;
                    }
                """)

        # 发送故障配置改变信号
        hopper_faults = []

        # 添加中转斗故障（只应用到选中的斗）
        if hopper_fault_type:
            hopper_select_index = self.hopper_select_combo.currentIndex()
            hopper_id_mapping = {
                0: None,  # 全部
                1: 'hopper1',
                2: 'hopper2',
                3: 'hopper3',
                4: 'hopper4',
                5: 'hopper5',
                6: 'hopper6',
                7: 'hopper7',
            }
            selected_hopper = hopper_id_mapping.get(hopper_select_index)

            if selected_hopper:
                # 只设置选中的斗
                hopper_faults.append({
                    'hopper_id': selected_hopper,
                    'fault_type': hopper_fault_type
                })
            else:
                # 全部斗
                for hp_id in config.TRANSFER_HOPPERS.keys():
                    hopper_faults.append({
                        'hopper_id': hp_id,
                        'fault_type': hopper_fault_type
                    })

        self.fault_config_changed.emit({
            'mode': mode,
            'count': self.current_fault_count,
            'faulty_sensors': list(self.fault_diagnosis.get_faulty_sensor_ids()),
            'hopper_faults': hopper_faults
        })

    def _on_clear_fault(self):
        """清除故障设置"""
        self.fault_diagnosis.clear_all_faults()
        self.current_fault_count = 0
        self.fault_mode_combo.setCurrentIndex(0)
        self.hopper_fault_combo.setCurrentIndex(0)
        self.hopper_select_combo.setCurrentIndex(0)
        self.fault_status_label.setText("当前无故障设置")
        self.fault_status_label.setStyleSheet("""
            QLabel {
                color: #6E7681;
                font-size: 10px;
                padding: 4px;
                background-color: #21262d;
                border-radius: 4px;
            }
        """)

        # 发送故障配置改变信号
        self.fault_config_changed.emit({
            'mode': FaultMode.OFF,
            'count': 0,
            'faulty_sensors': [],
            'hopper_faults': []
        })

    def _on_apply_conveyor_fault(self):
        """应用皮带故障设置"""
        conv_index = self.conveyor_fault_combo.currentIndex()
        fault_type_index = self.conveyor_fault_type_combo.currentIndex()

        if conv_index == 0:
            for conv_id in config.CONVEYOR_STATES:
                config.CONVEYOR_STATES[conv_id] = None
                speed_sensor_id = config.CONVEYOR_SPEED_SENSORS.get(conv_id)
                if speed_sensor_id:
                    self._sensor_data_manager.set_conveyor_speed_fault(speed_sensor_id, None)
            self.conveyor_fault_status_label.setText("已清除所有皮带设置")
        else:
            conv_ids = [
                "E1", "E2", "E4", "E5", "E6", "E7", "E8", "E9", "E10",
                "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D13"
            ]
            conv_id = conv_ids[conv_index - 1]
            speed_sensor_id = config.CONVEYOR_SPEED_SENSORS.get(conv_id)

            if fault_type_index == 0:
                # 正常：跟随仿真运行
                config.CONVEYOR_STATES[conv_id] = None
                if speed_sensor_id:
                    self._sensor_data_manager.set_conveyor_speed_fault(speed_sensor_id, None)
                self.conveyor_fault_status_label.setText(f"{conv_id}: 正常（跟随仿真）")
            elif fault_type_index == 1:
                # 皮带运行但转速为0 → 诊断: speed_zero_while_running(0.90)
                config.CONVEYOR_STATES[conv_id] = 'speed_abnormal'
                if speed_sensor_id:
                    self._sensor_data_manager.set_conveyor_speed_fault(speed_sensor_id, 'force_zero')
                self.conveyor_fault_status_label.setText(f"{conv_id}: 运行但转速为0 → 诊断: speed_zero_while_running(0.90)")
            elif fault_type_index == 2:
                # 皮带停止但转速非0 → 诊断: speed_nonzero_while_stopped(0.90)
                config.CONVEYOR_STATES[conv_id] = 'stopped'
                if speed_sensor_id:
                    self._sensor_data_manager.set_conveyor_speed_fault(speed_sensor_id, 'force_nonzero')
                self.conveyor_fault_status_label.setText(f"{conv_id}: 停止但转速非0 → 诊断: speed_nonzero_while_stopped(0.90)")
            else:
                # 皮带转速波动 → 诊断: speed_volatile(0.50)
                config.CONVEYOR_STATES[conv_id] = None
                if speed_sensor_id:
                    self._sensor_data_manager.set_conveyor_speed_fault(speed_sensor_id, 'volatile')
                self.conveyor_fault_status_label.setText(f"{conv_id}: 转速波动 → 诊断: speed_volatile(0.50)")

        self.conveyor_fault_changed.emit('update', dict(config.CONVEYOR_STATES))

    def _on_clear_conveyor_fault(self):
        """清除皮带状态设置"""
        for conv_id in config.CONVEYOR_STATES:
            config.CONVEYOR_STATES[conv_id] = None
            # 清除传感器数据管理器中的故障
            speed_sensor_id = config.CONVEYOR_SPEED_SENSORS.get(conv_id)
            if speed_sensor_id:
                self._sensor_data_manager.set_conveyor_speed_fault(speed_sensor_id, None)
        self.conveyor_fault_combo.setCurrentIndex(0)
        self.conveyor_fault_type_combo.setCurrentIndex(0)
        self.conveyor_fault_status_label.setText("当前无皮带设置")
        self.conveyor_fault_changed.emit('clear', None)

    def update_route_button(self, route_id: str, is_active: bool):
        """更新路线按钮状态"""
        if route_id in self.route_buttons:
            btn = self.route_buttons[route_id]
            btn.setChecked(is_active)
            if is_active:
                self.active_routes.add(route_id)
            else:
                self.active_routes.discard(route_id)

    def set_speed(self, speed: float):
        """设置速度"""
        self.speed_slider.setValue(int(speed * 10))
        self.speed_label.setText(f"{speed:.1f} m/s")

    def get_speed(self) -> float:
        """获取当前速度"""
        return self.speed_slider.value() / 10.0

    def get_fault_diagnosis(self) -> SensorFaultDiagnosis:
        """获取故障诊断系统"""
        return self.fault_diagnosis

    def is_sensor_faulty(self, sensor_id: str) -> bool:
        """检查传感器是否被设置为故障"""
        return self.fault_diagnosis.is_sensor_faulty(sensor_id)

    def update_sensor_state_with_fault(self, sensor_id: str, original_state: bool) -> bool:
        """
        更新传感器状态，如果设置了故障则返回模拟的故障状态
        用于仿真控制器获取经过故障模拟后的传感器状态
        """
        return self.fault_diagnosis.update_sensor_state(sensor_id, original_state)

    def get_diagnosis_result(self, sensor_states: Dict[str, bool]) -> List[Tuple[str, str]]:
        """
        诊断所有传感器
        返回: [(sensor_id, 故障原因), ...]
        """
        return self.fault_diagnosis.diagnose_all_sensors(
            list(self.active_routes),
            sensor_states
        )

    # ============ 运料小车传感器故障处理方法 ============

    def _on_cart_sensor_type_changed(self, index: int):
        """小车传感器类型改变时，更新故障类型下拉框"""
        if not hasattr(self, 'cart_fault_type_combo'):
            return
        self._update_cart_fault_type_combo(index)
        self._update_cart_fault_extra_visibility()

    def _update_cart_fault_type_combo(self, sensor_type_index: int):
        """根据传感器类型更新故障类型下拉框"""
        if not hasattr(self, 'cart_fault_type_combo'):
            return
        self.cart_fault_type_combo.clear()
        if sensor_type_index == 0:
            # 位置传感器
            self.cart_fault_type_combo.addItems(["定位彻底失效（卡死）", "定位不准（偏移）"])
        else:
            # 极限传感器 / 分料传感器
            self.cart_fault_type_combo.addItems(["恒定为 False（未触发）", "恒定为 True（触发）"])

    def _update_cart_fault_extra_visibility(self):
        """更新额外参数组件的可见性"""
        if not hasattr(self, 'cart_fault_extra_widget'):
            return
        sensor_type_index = self.cart_sensor_type_combo.currentIndex()
        if sensor_type_index == 0:
            # 位置传感器：显示位置/偏移量参数
            self.cart_fault_extra_widget.setVisible(True)
            self.cart_fault_extra_combo.clear()
            fault_type_index = self.cart_fault_type_combo.currentIndex()
            if fault_type_index == 0:
                # 定位卡死：选择固定位置 1-7（小车4为1-6）
                cart_index = self.cart_select_combo.currentIndex()
                max_pos = 6 if cart_index == 3 else 7
                self.cart_fault_extra_combo.addItems([str(i) for i in range(1, max_pos + 1)])
            else:
                # 定位不准：选择最大偏移量 1-5
                self.cart_fault_extra_combo.addItems([str(i) for i in range(1, 6)])
        else:
            # 极限/分料传感器：不需要额外参数
            self.cart_fault_extra_widget.setVisible(False)

    def _on_apply_cart_fault(self):
        """应用小车传感器故障"""
        if not hasattr(self, '_controller') or not self._controller:
            QMessageBox.warning(self, "提示", "控制器尚未初始化")
            return

        cart_index = self.cart_select_combo.currentIndex()
        cart_ids = ["Cart1", "Cart2", "Cart3", "Cart4"]
        cart_id = cart_ids[cart_index]

        sensor_type_index = self.cart_sensor_type_combo.currentIndex()
        fault_type_index = self.cart_fault_type_combo.currentIndex()

        try:
            if sensor_type_index == 0:
                # 位置传感器故障
                if fault_type_index == 0:
                    # 定位彻底失效（卡死）
                    extra_index = self.cart_fault_extra_combo.currentIndex()
                    stuck_value = extra_index + 1
                    self._controller.inject_cart_position_fault(
                        cart_id, fault_type='position_stuck', stuck_value=stuck_value
                    )
                else:
                    # 定位不准（偏移）
                    extra_index = self.cart_fault_extra_combo.currentIndex()
                    offset = extra_index + 1
                    self._controller.inject_cart_position_fault(
                        cart_id, fault_type='position_inaccurate', offset=offset
                    )
            elif sensor_type_index in (1, 2):
                # 极限传感器故障
                side = 'left' if sensor_type_index == 1 else 'right'
                stuck_value = (fault_type_index == 1)  # 0=False, 1=True
                self._controller.inject_cart_limit_fault(
                    cart_id, side=side, stuck_value=stuck_value
                )
            else:
                # 分料传感器故障 (3=左分料, 4=右分料)
                side = 'left' if sensor_type_index == 3 else 'right'
                stuck_value = (fault_type_index == 1)  # 0=False, 1=True
                self._controller.inject_cart_divert_fault(
                    cart_id, side=side, stuck_value=stuck_value
                )

            self._update_cart_fault_status()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"应用小车故障失败：{e}")

    def _on_clear_cart_fault_btn(self):
        """清除当前选中小车和传感器类型的故障"""
        if not hasattr(self, '_controller') or not self._controller:
            return

        cart_index = self.cart_select_combo.currentIndex()
        cart_ids = ["Cart1", "Cart2", "Cart3", "Cart4"]
        cart_id = cart_ids[cart_index]

        sensor_type_index = self.cart_sensor_type_combo.currentIndex()
        sensor_type_mapping = {
            0: 'position',
            1: 'left_limit',
            2: 'right_limit',
            3: 'left_divert',
            4: 'right_divert',
        }
        sensor_type = sensor_type_mapping.get(sensor_type_index, 'all')
        self._controller.clear_cart_fault(cart_id, sensor_type)
        self._update_cart_fault_status()

    def _update_cart_fault_status(self):
        """更新小车故障状态显示"""
        if not hasattr(self, '_controller') or not self._controller:
            self.cart_fault_status_label.setText("当前无小车传感器故障")
            return

        try:
            status = self._controller.get_cart_fault_status()
            if not status:
                self.cart_fault_status_label.setText("当前无小车传感器故障")
                self.cart_fault_status_label.setStyleSheet("""
                    QLabel {
                        color: #8B949E;
                        font-size: 10px;
                        padding: 6px;
                        background-color: #21262d;
                        border-radius: 4px;
                        min-height: 30px;
                    }
                """)
            else:
                lines = []
                cart_name_map = {
                    'Cart1': '小车1', 'Cart2': '小车2',
                    'Cart3': '小车3', 'Cart4': '小车4'
                }
                for key, value in status.items():
                    cart_id = key.split('_')[0]
                    cart_name = cart_name_map.get(cart_id, cart_id)
                    sensor_part = key[len(cart_id) + 1:]
                    sensor_name_map = {
                        'position_fault': '位置',
                        'left_limit': '左极限',
                        'right_limit': '右极限',
                        'left_divert': '左分料',
                        'right_divert': '右分料',
                    }
                    sensor_name = sensor_name_map.get(sensor_part, sensor_part)
                    if sensor_part == 'position_fault' and isinstance(value, dict):
                        desc = value.get('type', '故障')
                        stk = value.get('stuck_value', '')
                        off = value.get('offset', '')
                        extra = f" 位置={stk}" if stk else (f" 偏移±{off}" if off else "")
                        lines.append(f"{cart_name} {sensor_name}: {desc}{extra}")
                    else:
                        lines.append(f"{cart_name} {sensor_name}: 恒定={'True' if value else 'False'}")

                self.cart_fault_status_label.setText('\n'.join(lines))
                self.cart_fault_status_label.setStyleSheet("""
                    QLabel {
                        color: #E74C3C;
                        font-size: 10px;
                        padding: 6px;
                        background-color: #21262d;
                        border-radius: 4px;
                        border: 1px solid #E74C3C;
                        min-height: 30px;
                    }
                """)
        except Exception:
            self.cart_fault_status_label.setText("当前无小车传感器故障")

