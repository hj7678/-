"""
状态监控面板 - Status Monitor Panel
显示19条皮带、18个传感器、7个中转斗、3个激光测距仪、3个小车的状态
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QGroupBox, QLabel, QProgressBar, QScrollArea, QPushButton)
from PyQt5.QtCore import Qt, pyqtSignal
from typing import Dict
import styles
from views.status_data import (
    StatusData, CONVEYOR_IDS, SENSOR_IDS, HOPPER_IDS,
    LASER_SENSOR_IDS, LASER_SENSORS_CONFIG, CART_IDS, CART_SENSORS_CONFIG,
    TRANSFER_HOPPERS_CONFIG, FEED_POINT_DISPLAY_NAMES, CATEGORY_CN,
)


class StatusPanel(QWidget):
    """状态监控面板组件"""

    # 中转斗开关切换信号
    hopper_switch_toggled = pyqtSignal(str, bool)  # hopper_id, new_state
    data_reset_requested = pyqtSignal()  # 传感器数据初始化请求

    def __init__(self, parent=None):
        super().__init__(parent)

        self.conveyor_labels = {}
        self.sensor_labels = {}
        self.hopper_labels = {}
        self.laser_sensor_labels = {}  # 激光传感器显示标签
        self.cart_sensor_labels = {}   # 运料小车传感器显示标签
        self.level_sensor_labels = {}  # 料位传感器显示标签
        self.schedule_labels = {}     # 调度结果显示标签 D7/D8/D9

        # 状态缓存，用于优化更新
        self._conveyor_cache = {}
        self._sensor_cache = {}
        self._hopper_cache = {}
        self._stats_cache = {}
        self._laser_sensor_cache = {}
        self._cart_sensor_cache = {}
        self._level_sensor_cache = {}

        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(6)

        # 可滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(8)

        # 运料小车传感器状态（放在最前面）
        cart_group = self._create_cart_sensor_group()
        scroll_layout.addWidget(cart_group)

        # 激光测距仪传感器状态
        laser_group = self._create_laser_sensor_group()
        scroll_layout.addWidget(laser_group)

        # 皮带状态（合并E/D系列）
        conv_group = self._create_conveyor_group()
        scroll_layout.addWidget(conv_group)

        # 传感器状态
        sensor_group = self._create_sensor_group()
        scroll_layout.addWidget(sensor_group)

        # 中转斗状态
        hopper_group = self._create_hopper_group()
        scroll_layout.addWidget(hopper_group)

        # 高位储料仓料位传感器状态（只显示储料仓，配料站在动画中显示）
        level_group = self._create_level_sensors_display_group()
        scroll_layout.addWidget(level_group)

        # 故障诊断结果
        fault_diagnosis_group = self._create_fault_diagnosis_result_group()
        scroll_layout.addWidget(fault_diagnosis_group)

        # 调度结果（D7/D8/D9 上料顺序）
        schedule_group = self._create_schedule_display_group()
        scroll_layout.addWidget(schedule_group)

        # 统计信息
        stats_group = self._create_stats_group()
        scroll_layout.addWidget(stats_group)

        scroll_layout.addStretch()

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)

    def _create_cart_sensor_group(self) -> QGroupBox:
        """创建运料小车传感器状态组"""
        group = QGroupBox("运料小车传感器")
        group.setStyleSheet(styles.get_group_box_style())

        layout = QVBoxLayout()
        layout.setSpacing(4)

        # 创建小车传感器的显示单元格，4个小车分两行显示（每行2个）
        cart_ids = list(CART_IDS)

        # 第一行：Cart1, Cart2
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(6)
        for cart_id in cart_ids[:2]:
            cell = self._create_cart_sensor_cell(cart_id)
            self.cart_sensor_labels[cart_id] = cell
            row1_layout.addWidget(cell)

        # 第二行：Cart3, Cart4
        row2_layout = QHBoxLayout()
        row2_layout.setSpacing(6)
        for cart_id in cart_ids[2:]:
            cell = self._create_cart_sensor_cell(cart_id)
            self.cart_sensor_labels[cart_id] = cell
            row2_layout.addWidget(cell)

        layout.addLayout(row1_layout)
        layout.addLayout(row2_layout)

        group.setLayout(layout)
        return group

    def _create_cart_sensor_cell(self, cart_id: str) -> QWidget:
        """创建小车传感器状态单元格"""
        cart_config = CART_SENSORS_CONFIG[cart_id]

        cell = QWidget()
        cell.setFixedWidth(160)  # 固定宽度，确保一致
        cell_layout = QVBoxLayout(cell)
        cell_layout.setContentsMargins(4, 4, 4, 4)
        cell_layout.setSpacing(4)

        # 小车名称和目标配料站
        header_label = QLabel(f"{cart_config['name']} ({cart_config['destination']})")
        header_label.setAlignment(Qt.AlignCenter)
        header_label.setStyleSheet("font-weight: bold; color: #E74C3C; font-size: 11px;")
        cell_layout.addWidget(header_label)

        # 位置传感器显示
        pos_layout = QHBoxLayout()
        pos_layout.setSpacing(4)

        pos_label = QLabel("位置:")
        pos_label.setStyleSheet("color: #8B949E; font-size: 10px; min-width: 28px;")
        pos_layout.addWidget(pos_label)

        pos_value = QLabel("1")
        pos_value.setStyleSheet("color: #00FF00; font-size: 11px; font-weight: bold;")
        pos_value.setAlignment(Qt.AlignCenter)
        pos_value.setFixedWidth(20)
        pos_value.setObjectName(f"cart_pos_{cart_id}")
        pos_layout.addWidget(pos_value)

        pos_layout.addStretch()
        cell_layout.addLayout(pos_layout)

        # 极限位置传感器显示
        limit_layout = QHBoxLayout()
        limit_layout.setSpacing(8)

        # 左极限
        llimit_indicator = QLabel()
        llimit_indicator.setFixedSize(10, 10)
        llimit_indicator.setAlignment(Qt.AlignCenter)
        llimit_indicator.setStyleSheet(styles.get_status_indicator_style(False))
        llimit_indicator.setObjectName(f"cart_llimit_{cart_id}")

        llimit_label = QLabel("左极")
        llimit_label.setStyleSheet("color: #8B949E; font-size: 9px;")
        limit_layout.addWidget(llimit_indicator)
        limit_layout.addWidget(llimit_label)

        # 右极限
        rlimit_indicator = QLabel()
        rlimit_indicator.setFixedSize(10, 10)
        rlimit_indicator.setAlignment(Qt.AlignCenter)
        rlimit_indicator.setStyleSheet(styles.get_status_indicator_style(False))
        rlimit_indicator.setObjectName(f"cart_rlimit_{cart_id}")

        rlimit_label = QLabel("右极")
        rlimit_label.setStyleSheet("color: #8B949E; font-size: 9px;")
        limit_layout.addWidget(rlimit_indicator)
        limit_layout.addWidget(rlimit_label)

        limit_layout.addStretch()
        cell_layout.addLayout(limit_layout)

        # 分料传感器显示
        divert_layout = QHBoxLayout()
        divert_layout.setSpacing(8)

        # 左分料
        ldiv_indicator = QLabel()
        ldiv_indicator.setFixedSize(10, 10)
        ldiv_indicator.setAlignment(Qt.AlignCenter)
        ldiv_indicator.setStyleSheet(styles.get_status_indicator_style(False))
        ldiv_indicator.setObjectName(f"cart_ldiv_{cart_id}")

        ldiv_label = QLabel("左分")
        ldiv_label.setStyleSheet("color: #8B949E; font-size: 9px;")
        divert_layout.addWidget(ldiv_indicator)
        divert_layout.addWidget(ldiv_label)

        # 右分料
        rdiv_indicator = QLabel()
        rdiv_indicator.setFixedSize(10, 10)
        rdiv_indicator.setAlignment(Qt.AlignCenter)
        rdiv_indicator.setStyleSheet(styles.get_status_indicator_style(False))
        rdiv_indicator.setObjectName(f"cart_rdiv_{cart_id}")

        rdiv_label = QLabel("右分")
        rdiv_label.setStyleSheet("color: #8B949E; font-size: 9px;")
        divert_layout.addWidget(rdiv_indicator)
        divert_layout.addWidget(rdiv_label)

        divert_layout.addStretch()
        cell_layout.addLayout(divert_layout)

        # 保存组件引用
        cell.pos_value = pos_value
        cell.llimit_indicator = llimit_indicator
        cell.rlimit_indicator = rlimit_indicator
        cell.ldiv_indicator = ldiv_indicator
        cell.rdiv_indicator = rdiv_indicator

        return cell

    def update_cart_sensor_display(self, cart_id: str, position: int, left_limit: bool,
                                   right_limit: bool, left_divert: bool, right_divert: bool,
                                   force_update: bool = False):
        """更新小车传感器显示状态

        Args:
            cart_id: 小车ID
            position: 位置值 (1-7)
            left_limit: 左极限传感器状态
            right_limit: 右极限传感器状态
            left_divert: 左分料传感器状态
            right_divert: 右分料传感器状态
            force_update: 是否强制更新
        """
        if cart_id in self.cart_sensor_labels:
            cell = self.cart_sensor_labels[cart_id]

            # 检查缓存
            cache_key = (position, left_limit, right_limit, left_divert, right_divert)
            if not force_update and self._cart_sensor_cache.get(cart_id) == cache_key:
                return
            self._cart_sensor_cache[cart_id] = cache_key

            # 更新位置值
            cell.pos_value.setText(str(position))

            # 更新左极限传感器
            cell.llimit_indicator.setStyleSheet(styles.get_status_indicator_style(left_limit))
            if left_limit:
                cell.llimit_indicator.setToolTip("左极限位置")
            else:
                cell.llimit_indicator.setToolTip("")

            # 更新右极限传感器
            cell.rlimit_indicator.setStyleSheet(styles.get_status_indicator_style(right_limit))
            if right_limit:
                cell.rlimit_indicator.setToolTip("右极限位置")
            else:
                cell.rlimit_indicator.setToolTip("")

            # 更新左分料传感器
            cell.ldiv_indicator.setStyleSheet(styles.get_status_indicator_style(left_divert))
            if left_divert:
                cell.ldiv_indicator.setToolTip("左分料中")
            else:
                cell.ldiv_indicator.setToolTip("")

            # 更新右分料传感器
            cell.rdiv_indicator.setStyleSheet(styles.get_status_indicator_style(right_divert))
            if right_divert:
                cell.rdiv_indicator.setToolTip("右分料中")
            else:
                cell.rdiv_indicator.setToolTip("")

    def _create_laser_sensor_group(self) -> QGroupBox:
        """创建激光测距仪传感器状态组"""
        group = QGroupBox("激光测距仪传感器")
        group.setStyleSheet(styles.get_group_box_style())

        layout = QGridLayout()
        layout.setSpacing(8)

        # 创建每个激光传感器的显示单元格
        laser_ids = list(LASER_SENSOR_IDS)
        for idx, laser_id in enumerate(laser_ids):
            row = idx // 2
            col = idx % 2

            # 从传感器配置获取上料点信息
            sensor_config = LASER_SENSORS_CONFIG.get(laser_id, {})
            feed_point = sensor_config.get('feed_point', '')

            # 获取上料点中文名称
            feed_point_name = FEED_POINT_DISPLAY_NAMES.get(feed_point, feed_point)

            cell = self._create_laser_sensor_cell(laser_id, feed_point_name)
            self.laser_sensor_labels[laser_id] = cell
            layout.addWidget(cell, row, col)

        group.setLayout(layout)
        return group

    def _create_laser_sensor_cell(self, laser_id: str, feed_point_name: str) -> QWidget:
        """创建激光传感器状态单元格"""
        cell = QWidget()
        cell.setFixedWidth(120)
        cell_layout = QVBoxLayout(cell)
        cell_layout.setContentsMargins(2, 2, 2, 2)
        cell_layout.setSpacing(2)

        # 上料点名称
        name_label = QLabel(feed_point_name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("font-weight: bold; color: #9B59B6; font-size: 11px;")
        name_label.setFixedHeight(14)
        cell_layout.addWidget(name_label)

        # 状态指示灯
        indicator = QLabel()
        indicator.setFixedSize(12, 12)
        indicator.setAlignment(Qt.AlignCenter)
        indicator.setStyleSheet(styles.get_status_indicator_style(True))  # 默认有料=绿色
        indicator.setObjectName(f"laser_indicator_{laser_id}")
        cell_layout.addWidget(indicator, 0, Qt.AlignCenter)

        # 状态文字
        status_label = QLabel("有料")
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setStyleSheet("color: #2ECC71; font-size: 11px; font-weight: bold;")
        status_label.setObjectName(f"laser_status_{laser_id}")
        cell_layout.addWidget(status_label)

        cell.indicator = indicator
        cell.status = status_label

        return cell

    def update_laser_sensor_display(self, laser_id: str, has_material: bool, force_update: bool = False):
        """更新激光传感器显示状态

        Args:
            laser_id: 激光传感器ID
            has_material: 是否有原料
            force_update: 是否强制更新（忽略缓存）
        """
        if laser_id in self.laser_sensor_labels:
            cell = self.laser_sensor_labels[laser_id]
            cache_key = has_material
            if not force_update and self._laser_sensor_cache.get(laser_id) == cache_key:
                return
            self._laser_sensor_cache[laser_id] = cache_key

            if has_material:
                cell.indicator.setStyleSheet(styles.get_status_indicator_style(True))
                cell.status.setText("有料")
                cell.status.setStyleSheet("color: #2ECC71; font-size: 11px; font-weight: bold;")
            else:
                cell.indicator.setStyleSheet(styles.get_status_indicator_style(False))
                cell.status.setText("无料")
                cell.status.setStyleSheet("color: #E74C3C; font-size: 11px; font-weight: bold;")

    def _create_conveyor_group(self) -> QGroupBox:
        """创建皮带状态组（所有皮带）"""
        group = QGroupBox("皮带状态")
        group.setStyleSheet(styles.get_group_box_style())

        # 所有皮带列表
        conv_ids = list(CONVEYOR_IDS)

        layout = QGridLayout()
        layout.setSpacing(4)

        for idx, conv_id in enumerate(conv_ids):
            row = idx // 5
            col = idx % 5

            cell = self._create_conveyor_cell(conv_id)
            self.conveyor_labels[conv_id] = cell
            layout.addWidget(cell, row, col)

        group.setLayout(layout)
        return group

    def _create_conveyor_cell(self, conv_id: str) -> QWidget:
        """创建皮带状态单元格"""
        cell = QWidget()
        cell.setFixedWidth(55)
        cell_layout = QVBoxLayout(cell)
        cell_layout.setContentsMargins(1, 1, 1, 1)
        cell_layout.setSpacing(0)

        # 皮带名称
        name_label = QLabel(conv_id)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("font-weight: bold; color: #4A90D9; font-size: 11px;")
        name_label.setFixedHeight(14)
        cell_layout.addWidget(name_label)

        # 状态指示灯
        indicator = QLabel()
        indicator.setFixedSize(12, 12)
        indicator.setAlignment(Qt.AlignCenter)
        indicator.setStyleSheet(styles.get_status_indicator_style(False))
        indicator.setObjectName(f"conv_indicator_{conv_id}")
        cell_layout.addWidget(indicator)

        # 状态文字
        status_label = QLabel("停")
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setStyleSheet("color: #6E7681; font-size: 10px;")
        status_label.setObjectName(f"conv_status_{conv_id}")
        cell_layout.addWidget(status_label)

        cell.indicator = indicator
        cell.status = status_label

        return cell

    def _create_sensor_group(self) -> QGroupBox:
        """创建传感器状态组"""
        group = QGroupBox("接近开关传感器")
        group.setStyleSheet(styles.get_group_box_style())

        layout = QGridLayout()
        layout.setSpacing(3)

        # 所有传感器 - 使用新的传感器ID格式
        sensor_ids = list(SENSOR_IDS)

        for idx, sensor_id in enumerate(sensor_ids):
            row = idx // 5
            col = idx % 5

            cell = self._create_sensor_cell(sensor_id)
            self.sensor_labels[sensor_id] = cell
            layout.addWidget(cell, row, col)

        group.setLayout(layout)
        return group

    def _create_sensor_cell(self, sensor_id: str) -> QWidget:
        """创建传感器状态单元格"""
        cell = QWidget()
        cell.setFixedWidth(55)
        cell_layout = QVBoxLayout(cell)
        cell_layout.setContentsMargins(1, 1, 1, 1)
        cell_layout.setSpacing(0)

        # 传感器名称
        name_label = QLabel(sensor_id)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("font-weight: bold; color: #E67E22; font-size: 10px;")
        name_label.setFixedHeight(14)
        cell_layout.addWidget(name_label)

        # 状态指示灯（开关图标）
        indicator = QLabel()
        indicator.setFixedSize(12, 10)
        indicator.setAlignment(Qt.AlignCenter)
        indicator.setStyleSheet(styles.get_status_indicator_style(False))
        indicator.setObjectName(f"sensor_indicator_{sensor_id}")
        cell_layout.addWidget(indicator)

        # 状态文字
        status_label = QLabel("OFF")
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setStyleSheet("color: #6E7681; font-size: 9px;")
        status_label.setObjectName(f"sensor_status_{sensor_id}")
        cell_layout.addWidget(status_label)

        # 故障标记
        fault_indicator = QLabel()
        fault_indicator.setFixedSize(10, 10)
        fault_indicator.setAlignment(Qt.AlignCenter)
        fault_indicator.setStyleSheet("""
            QLabel {
                background-color: transparent;
                border-radius: 5px;
                min-width: 10px;
                max-width: 10px;
                min-height: 10px;
                max-height: 10px;
            }
        """)
        fault_indicator.setObjectName(f"sensor_fault_{sensor_id}")
        fault_indicator.setVisible(False)
        cell_layout.addWidget(fault_indicator)

        cell.indicator = indicator
        cell.status = status_label
        cell.fault_indicator = fault_indicator
        cell.is_faulty = False

        return cell

    def _create_hopper_group(self) -> QGroupBox:
        """创建中转斗状态组"""
        group = QGroupBox("中转斗")
        group.setStyleSheet(styles.get_group_box_style())

        layout = QGridLayout()
        layout.setSpacing(4)

        hopper_ids = list(HOPPER_IDS)

        for idx, hopper_id in enumerate(hopper_ids):
            row = idx // 4
            col = idx % 4

            cell = self._create_hopper_cell(hopper_id)
            self.hopper_labels[hopper_id] = cell
            layout.addWidget(cell, row, col)

        group.setLayout(layout)
        return group

    def _create_hopper_cell(self, hopper_id: str) -> QWidget:
        """创建中转斗状态单元格"""
        hopper_config = TRANSFER_HOPPERS_CONFIG[hopper_id]

        cell = QWidget()
        cell.setFixedWidth(75)
        cell_layout = QVBoxLayout(cell)
        cell_layout.setContentsMargins(1, 1, 1, 1)
        cell_layout.setSpacing(1)

        # 中转斗名称
        name_label = QLabel(hopper_config['name'])
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("font-weight: bold; color: #8E44AD; font-size: 10px;")
        name_label.setFixedHeight(12)
        cell_layout.addWidget(name_label)

        # 开关状态（可点击的按钮）
        switch_layout = QHBoxLayout()
        switch_layout.setSpacing(2)

        switch_label = QLabel("开关:")
        switch_label.setStyleSheet("color: #8B949E; font-size: 9px;")
        switch_label.setFixedWidth(22)
        switch_layout.addWidget(switch_label)

        # 可点击的开关按钮
        switch_btn = QPushButton("开")
        switch_btn.setFixedSize(24, 16)
        switch_btn.setCheckable(True)
        switch_btn.setChecked(True)
        switch_btn.setObjectName(f"hopper_switch_{hopper_id}")
        switch_btn.setStyleSheet("""
            QPushButton {
                background-color: #27AE60;
                color: white;
                border: none;
                border-radius: 3px;
                font-size: 9px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:checked {
                background-color: #27AE60;
                color: white;
            }
            QPushButton:!checked {
                background-color: #E74C3C;
                color: white;
            }
            QPushButton:hover:!checked {
                background-color: #C0392B;
            }
            QPushButton:hover:checked {
                background-color: #229954;
            }
        """)
        switch_btn.clicked.connect(lambda checked, hid=hopper_id, btn=switch_btn: self._on_hopper_switch_clicked(hid, checked, btn))
        switch_layout.addWidget(switch_btn)

        switch_layout.addStretch()
        cell_layout.addLayout(switch_layout)

        # 称重传感器
        weight_layout = QHBoxLayout()
        weight_layout.setSpacing(2)

        weight_label = QLabel("称重:")
        weight_label.setStyleSheet("color: #8B949E; font-size: 9px;")
        weight_label.setFixedWidth(22)
        weight_layout.addWidget(weight_label)

        weight_value = QLabel("0kg")
        weight_value.setStyleSheet("color: #F39C12; font-size: 9px; font-weight: bold;")
        weight_value.setFixedWidth(45)
        weight_value.setObjectName(f"hopper_weight_{hopper_id}")
        weight_layout.addWidget(weight_value)

        weight_layout.addStretch()
        cell_layout.addLayout(weight_layout)

        # 料位条
        bar = QProgressBar()
        bar.setMinimum(0)
        bar.setMaximum(100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(5)
        bar.setStyleSheet("""
            QProgressBar {
                background-color: #21262d;
                border: 1px solid #8E44AD;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #8E44AD;
            }
        """)
        bar.setObjectName(f"hopper_bar_{hopper_id}")
        cell_layout.addWidget(bar)

        cell.bar = bar
        cell.switch_btn = switch_btn
        cell.weight_value = weight_value

        return cell

    def _on_hopper_switch_clicked(self, hopper_id: str, checked: bool, btn: QPushButton):
        """中转斗开关点击处理"""
        # checked=True 表示设置为"开", checked=False 表示设置为"关"
        new_state = checked
        # 更新按钮文本
        btn.setText("开" if new_state else "关")
        # 发射信号
        self.hopper_switch_toggled.emit(hopper_id, new_state)

    def _create_stats_group(self) -> QGroupBox:
        """创建统计信息组"""
        group = QGroupBox("数据统计")
        group.setStyleSheet(styles.get_group_box_style())
        layout = QGridLayout()
        layout.setSpacing(10)

        # 运行时间
        time_label = QLabel("运行时间:")
        time_label.setStyleSheet("color: #8B949E; font-size: 13px;")
        layout.addWidget(time_label, 0, 0)

        self.runtime_label = QLabel("00:00:00")
        self.runtime_label.setStyleSheet("font-family: Consolas; color: #2ECC71; font-size: 14px;")
        layout.addWidget(self.runtime_label, 0, 1)

        # 上料重量
        material_label = QLabel("上料重量:")
        material_label.setStyleSheet("color: #8B949E; font-size: 13px;")
        layout.addWidget(material_label, 1, 0)

        self.material_counter = QLabel("0.00 t")
        self.material_counter.setStyleSheet("font-weight: bold; color: #F39C12; font-size: 14px;")
        layout.addWidget(self.material_counter, 1, 1)

        # 活跃路线
        route_label = QLabel("活跃路线:")
        route_label.setStyleSheet("color: #8B949E; font-size: 13px;")
        layout.addWidget(route_label, 2, 0)

        self.route_counter = QLabel("0/9")
        self.route_counter.setStyleSheet("font-weight: bold; color: #4A90D9; font-size: 14px;")
        layout.addWidget(self.route_counter, 2, 1)

        # 报警次数（暂时隐藏）
        alarm_label = QLabel("报警次数:")
        alarm_label.setStyleSheet("color: #8B949E; font-size: 13px;")
        alarm_label.hide()
        layout.addWidget(alarm_label, 3, 0)

        self.alarm_counter = QLabel("0")
        self.alarm_counter.setStyleSheet("font-weight: bold; color: #E74C3C; font-size: 14px;")
        self.alarm_counter.hide()
        layout.addWidget(self.alarm_counter, 3, 1)

        # 故障传感器数
        fault_label = QLabel("故障传感器:")
        fault_label.setStyleSheet("color: #8B949E; font-size: 13px;")
        layout.addWidget(fault_label, 4, 0)

        self.fault_sensor_counter = QLabel("0")
        self.fault_sensor_counter.setStyleSheet("font-weight: bold; color: #E74C3C; font-size: 14px;")
        layout.addWidget(self.fault_sensor_counter, 4, 1)

        # 数据初始化按钮
        reset_btn = QPushButton("传感器数据初始化")
        reset_btn.setMinimumHeight(28)
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #8E44AD;
                color: #ECF0F1;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #9B59B6;
            }
            QPushButton:pressed {
                background-color: #7D3C98;
            }
        """)
        reset_btn.clicked.connect(self.data_reset_requested.emit)
        layout.addWidget(reset_btn, 5, 0, 1, 2)

        group.setLayout(layout)
        return group

    def _create_fault_diagnosis_result_group(self) -> QGroupBox:
        """创建故障诊断结果组"""
        group = QGroupBox("故障诊断结果")
        group.setStyleSheet(styles.get_group_box_style())
        layout = QVBoxLayout()
        layout.setSpacing(8)

        # 诊断状态标签
        self.diagnosis_status_label = QLabel("系统正常")
        self.diagnosis_status_label.setStyleSheet("""
            QLabel {
                color: #2ECC71;
                font-size: 13px;
                font-weight: bold;
                padding: 6px;
                background-color: #21262d;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.diagnosis_status_label)

        # 故障列表
        self.fault_list_label = QLabel("未检测到传感器故障")
        self.fault_list_label.setStyleSheet("""
            QLabel {
                color: #6E7681;
                font-size: 12px;
                padding: 6px;
            }
        """)
        self.fault_list_label.setWordWrap(True)
        self.fault_list_label.setMinimumHeight(30)
        layout.addWidget(self.fault_list_label)

        group.setLayout(layout)
        return group

    def _create_schedule_display_group(self) -> QGroupBox:
        """创建调度结果显示组"""
        group = QGroupBox("调度上料顺序")
        group.setStyleSheet(styles.get_group_box_style())
        layout = QVBoxLayout()
        layout.setSpacing(4)

        for belt_id in ['D7', 'D8', 'D9']:
            label = QLabel(f"{belt_id}：等待调度结果...")
            label.setStyleSheet("""
                QLabel {
                    color: #6E7681;
                    font-size: 12px;
                    padding: 4px;
                }
            """)
            label.setWordWrap(True)
            label.setMinimumHeight(20)
            self.schedule_labels[belt_id] = label
            layout.addWidget(label)

        group.setLayout(layout)
        return group

    def update_schedule_display(self, schedules: dict, executing_bins: dict = None):
        executing_bins = executing_bins or {}
        for belt_id in ['D7', 'D8', 'D9']:
            label = self.schedule_labels.get(belt_id)
            if label is None:
                continue
            result = schedules.get(belt_id)
            executing_bin = executing_bins.get(belt_id)
            if result:
                seq = result.get("sequence", [])
                if seq:
                    parts = []
                    for i, s in enumerate(seq[:7]):
                        if s == executing_bin:
                            parts.append(f"▶{s}")
                        else:
                            parts.append(str(s))
                    seq_str = " → ".join(parts)
                    move_time = result.get("summary", {}).get("total_move", 0)
                    text = f"{belt_id}：{seq_str}  |  移动耗时 {move_time:.1f}s"
                    if executing_bin:
                        label.setStyleSheet("""
                            QLabel {
                                color: #2ECC71;
                                font-size: 12px;
                                padding: 4px;
                                font-weight: bold;
                            }
                        """)
                    else:
                        label.setStyleSheet("""
                            QLabel {
                                color: #4A90D9;
                                font-size: 12px;
                                padding: 4px;
                            }
                        """)
                    label.setText(text)
                else:
                    label.setText(f"{belt_id}：无可行的上料顺序")
                    label.setStyleSheet("""
                        QLABEL {
                            color: #F39C12;
                            font-size: 12px;
                            padding: 4px;
                        }
                    """)
            else:
                label.setText(f"{belt_id}：等待调度结果...")
                label.setStyleSheet("""
                    QLabel {
                        color: #6E7681;
                        font-size: 12px;
                        padding: 4px;
                    }
                """)

    def _create_level_sensors_display_group(self) -> QGroupBox:
        """创建料位传感器显示组（只显示高位储料仓）"""
        group = QGroupBox("高位储料仓料位")
        group.setStyleSheet(styles.get_group_box_style())

        layout = QVBoxLayout()
        layout.setSpacing(4)

        # 高位储料仓料位（只显示S1-S12）
        silo_grid = QGridLayout()
        silo_grid.setSpacing(2)
        for i in range(1, 13):
            bin_id = f"S{i}"
            cell = self._create_level_sensor_display_cell(bin_id)
            self.level_sensor_labels[bin_id] = cell
            row = (i - 1) // 4
            col = (i - 1) % 4
            silo_grid.addWidget(cell, row, col)
        layout.addLayout(silo_grid)

        group.setLayout(layout)
        return group

    def _create_level_sensor_display_cell(self, bin_id: str) -> QWidget:
        """创建料位显示单元格"""
        cell = QWidget()
        cell.setFixedWidth(60)
        cell_layout = QVBoxLayout(cell)
        cell_layout.setContentsMargins(1, 1, 1, 1)
        cell_layout.setSpacing(0)

        # 料仓名称
        name_label = QLabel(bin_id)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet("color: #8B949E; font-size: 9px;")
        name_label.setFixedHeight(12)
        cell_layout.addWidget(name_label)

        # 料位进度条
        bar = QProgressBar()
        bar.setMinimum(0)
        bar.setMaximum(100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        bar.setStyleSheet("""
            QProgressBar {
                background-color: #21262d;
                border: 1px solid #8E44AD;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #8E44AD;
            }
        """)
        cell_layout.addWidget(bar)

        # 料位数值
        value_label = QLabel("0%")
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setStyleSheet("color: #8E44AD; font-size: 8px; font-weight: bold;")
        cell_layout.addWidget(value_label)

        cell.bar = bar
        cell.value_label = value_label

        return cell

    def update_level_sensors_display(self, level_sensors: Dict[str, float]):
        """更新料位传感器显示"""
        for bin_id, level in level_sensors.items():
            if bin_id in self.level_sensor_labels:
                cell = self.level_sensor_labels[bin_id]
                value = int(level)
                cell.bar.setValue(value)
                cell.value_label.setText(f"{value}%")

                # 根据料位调整颜色
                if value >= 95:
                    color = '#E74C3C'  # 满仓红色
                elif value >= 90:
                    color = '#F39C12'  # 高位橙色
                elif value >= 70:
                    color = '#8E44AD'  # 中位紫色
                else:
                    color = '#2ECC71'  # 正常绿色

                cell.bar.setStyleSheet(f"""
                    QProgressBar {{
                        background-color: #21262d;
                        border: 1px solid {color};
                        border-radius: 2px;
                    }}
                    QProgressBar::chunk {{
                        background-color: {color};
                    }}
                """)
                cell.value_label.setStyleSheet(f"color: {color}; font-size: 8px; font-weight: bold;")

    def update_conveyor_status(self, conv_id: str, is_running: bool, on_route: bool = False,
                               fault_type: str = None, raw_speed: int = 0):
        """更新皮带状态

        Args:
            conv_id: 皮带ID
            is_running: 是否运行
            on_route: 是否在活跃路线上
            fault_type: 故障类型，None=正常，'stopped'=关闭，'speed_abnormal'=转速异常
            raw_speed: 原始转速值（sint类型）
        """
        if conv_id in self.conveyor_labels:
            # 计算当前状态
            if fault_type == 'stopped' or (raw_speed == 0 and not is_running):
                status_key = 'stopped'
            elif fault_type == 'speed_abnormal':
                status_key = 'abnormal'
            elif is_running and on_route:
                status_key = 'running_route'
            elif is_running:
                status_key = 'running'
            else:
                status_key = 'stopped'

            # 检查是否与缓存的状态相同，避免不必要的UI更新
            if self._conveyor_cache.get(conv_id) == status_key:
                return
            self._conveyor_cache[conv_id] = status_key

            cell = self.conveyor_labels[conv_id]

            # 关闭状态：转速为0或设置了stopped
            if fault_type == 'stopped' or raw_speed == 0 and is_running is False:
                cell.indicator.setStyleSheet(styles.get_status_indicator_style(False))
                cell.status.setText("停止")
                cell.status.setStyleSheet("color: #6E7681; font-size: 10px;")
            # 转速异常状态：皮带启动但速度异常
            elif fault_type == 'speed_abnormal':
                cell.indicator.setStyleSheet(styles.get_status_indicator_style(active=True, fault=True))
                cell.status.setText("异常")
                cell.status.setStyleSheet("color: #E74C3C; font-size: 10px; font-weight: bold;")
            # 正常运行状态
            elif is_running:
                if on_route:
                    cell.indicator.setStyleSheet(styles.get_status_indicator_style(True))
                    cell.status.setText("运行")
                    cell.status.setStyleSheet("color: #00FF00; font-size: 10px; font-weight: bold;")
                else:
                    cell.indicator.setStyleSheet(styles.get_status_indicator_style(True))
                    cell.status.setText("运行")
                    cell.status.setStyleSheet("color: #2ECC71; font-size: 10px;")
            # 默认停止状态
            else:
                cell.indicator.setStyleSheet(styles.get_status_indicator_style(False))
                cell.status.setText("停止")
                cell.status.setStyleSheet("color: #6E7681; font-size: 10px;")

    def update_sensor_status(self, sensor_id: str, is_active: bool, is_faulty: bool = False):
        """更新传感器状态"""
        if sensor_id in self.sensor_labels:
            # 检查是否与缓存的状态相同
            cache_key = (is_active, is_faulty)
            if self._sensor_cache.get(sensor_id) == cache_key:
                return
            self._sensor_cache[sensor_id] = cache_key

            cell = self.sensor_labels[sensor_id]

            cell.indicator.setStyleSheet(styles.get_status_indicator_style(is_active))

            if is_active:
                cell.status.setText("ON")
                cell.status.setStyleSheet("color: #00FF00; font-size: 10px; font-weight: bold;")
            else:
                cell.status.setText("OFF")
                cell.status.setStyleSheet("color: #6E7681; font-size: 10px;")

            # 更新故障指示器
            cell.is_faulty = is_faulty
            if is_faulty:
                cell.fault_indicator.setVisible(True)
                cell.fault_indicator.setStyleSheet("""
                    QLabel {
                        background-color: #E74C3C;
                        border-radius: 5px;
                        min-width: 10px;
                        max-width: 10px;
                        min-height: 10px;
                        max-height: 10px;
                    }
                """)
                cell.status.setText("FLT")
                cell.status.setStyleSheet("color: #E74C3C; font-size: 9px; font-weight: bold;")
            else:
                cell.fault_indicator.setVisible(False)
                cell.fault_indicator.setStyleSheet("""
                    QLabel {
                        background-color: transparent;
                        border-radius: 5px;
                        min-width: 10px;
                        max-width: 10px;
                        min-height: 10px;
                        max-height: 10px;
                    }
                """)

    def update_hopper_level(self, hopper_id: str, level_percent: float, is_full: bool = False,
                           switch_open: bool = True, weight: float = 0.0):
        """更新中转斗状态"""
        if hopper_id in self.hopper_labels:
            # 检查缓存（包含开关状态）
            cache_key = (int(level_percent), is_full, weight, switch_open)
            if self._hopper_cache.get(hopper_id) == cache_key:
                return
            self._hopper_cache[hopper_id] = cache_key

            cell = self.hopper_labels[hopper_id]
            value = int(level_percent)

            cell.bar.setValue(value)

            # 更新开关按钮状态
            if hasattr(cell, 'switch_btn'):
                cell.switch_btn.setChecked(switch_open)
                cell.switch_btn.setText("开" if switch_open else "关")

            # 更新称重值（weight参数为吨，转换为kg显示）
            weight_kg = int(weight * 1000)
            cell.weight_value.setText(f"{weight_kg}kg")

            # 料位条颜色
            if is_full:
                color = '#E74C3C'
            elif value > 70:
                color = '#F39C12'
            else:
                color = '#8E44AD'

            cell.bar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: #21262d;
                    border: 1px solid {color};
                    border-radius: 2px;
                }}
                QProgressBar::chunk {{
                    background-color: {color};
                }}
            """)

    def update_runtime(self, seconds: float):
        """更新运行时间"""
        # 检查缓存
        cache_key = int(seconds)
        if self._stats_cache.get('runtime') == cache_key:
            return
        self._stats_cache['runtime'] = cache_key

        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        self.runtime_label.setText(f"{hours:02d}:{minutes:02d}:{secs:02d}")

    def update_material_count(self, weight_tons: float):
        """更新上料重量"""
        # 检查缓存（保留两位小数）
        cache_key = round(weight_tons, 2)
        if self._stats_cache.get('material') == cache_key:
            return
        self._stats_cache['material'] = cache_key
        self.material_counter.setText(f"{weight_tons:.2f} t")

    def update_alarm_count(self, count: int):
        """更新报警计数"""
        if self._stats_cache.get('alarm') == count:
            return
        self._stats_cache['alarm'] = count
        self.alarm_counter.setText(str(count))

    def update_active_routes(self, routes: list):
        """更新活跃路线数"""
        cache_key = len(routes)
        if self._stats_cache.get('routes') == cache_key:
            return
        self._stats_cache['routes'] = cache_key
        self.route_counter.setText(f"{len(routes)}/9")

    def update_fault_count(self, count: int):
        """更新故障传感器计数"""
        if self._stats_cache.get('fault') == count:
            return
        self._stats_cache['fault'] = count

        self.fault_sensor_counter.setText(str(count))
        if count > 0:
            self.fault_sensor_counter.setStyleSheet("font-weight: bold; color: #E74C3C; font-size: 14px;")
        else:
            self.fault_sensor_counter.setStyleSheet("font-weight: bold; color: #2ECC71; font-size: 14px;")

    def update_diagnosis_result(self, faults: list, full_results: list = None):
        """
        更新故障诊断结果
        faults: [(sensor_id, reason), ...]  兼容旧格式
        full_results: [DiagnosisResult, ...]  完整结果（含置信度、类别）
        """
        if faults:
            self.diagnosis_status_label.setText(f"检测到 {len(faults)} 个故障")
            self.diagnosis_status_label.setStyleSheet("""
                QLabel {
                    color: #E74C3C;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 6px;
                    background-color: #21262d;
                    border: 1px solid #E74C3C;
                    border-radius: 4px;
                }
            """)
            # 构建带置信度和类别的故障文本
            lines = []
            if full_results:
                for r in full_results:
                    if r.confidence >= 0.7:
                        conf_pct = int(r.confidence * 100)
                        cat_cn = CATEGORY_CN.get(r.category, r.category)
                        lines.append(f"[{cat_cn}] {r.sensor_id}: {r.description} (置信度{conf_pct}%)")
                    elif r.confidence >= 0.5:
                        conf_pct = int(r.confidence * 100)
                        cat_cn = CATEGORY_CN.get(r.category, r.category)
                        lines.append(f"[{cat_cn}·低] {r.sensor_id}: {r.description} (置信度{conf_pct}%)")
            else:
                lines = [f"{sid}: {reason}" for sid, reason in faults]

            fault_text = "\n".join(lines)
            self.fault_list_label.setText(fault_text)
            self.fault_list_label.setStyleSheet("""
                QLabel {
                    color: #E74C3C;
                    font-size: 12px;
                    padding: 6px;
                    background-color: #21262d;
                    border-radius: 4px;
                }
            """)
        else:
            self.diagnosis_status_label.setText("系统正常")
            self.diagnosis_status_label.setStyleSheet("""
                QLabel {
                    color: #2ECC71;
                    font-size: 13px;
                    font-weight: bold;
                    padding: 6px;
                    background-color: #21262d;
                    border-radius: 4px;
                }
            """)
            self.fault_list_label.setText("未检测到传感器故障")
            self.fault_list_label.setStyleSheet("""
                QLabel {
                    color: #6E7681;
                    font-size: 12px;
                    padding: 6px;
                }
            """)

    def update_all_status(self, data: StatusData):
        """从 StatusData 更新所有状态"""

        # 更新运料小车传感器状态
        for cart_id in self.cart_sensor_labels.keys():
            cart_info = data.cart_sensors.get(cart_id, {})
            if cart_info:
                self.update_cart_sensor_display(
                    cart_id,
                    cart_info.get('position', 1),
                    cart_info.get('left_limit', False),
                    cart_info.get('right_limit', False),
                    cart_info.get('left_divert', False),
                    cart_info.get('right_divert', False)
                )

        # 更新皮带状态
        for conv_id in list(self.conveyor_labels.keys()):
            state = data.conveyors.get(conv_id, {})
            self.update_conveyor_status(
                conv_id, state.get('is_running', False), state.get('on_route', False),
                state.get('fault_type'), state.get('raw_speed', 0)
            )

        # 更新传感器状态
        for sensor_id in self.sensor_labels.keys():
            is_active = data.sensors.get(sensor_id, False)
            is_faulty = sensor_id in data.faulty_sensors
            self.update_sensor_status(sensor_id, is_active, is_faulty)

        # 更新中转斗
        for hopper_id in self.hopper_labels.keys():
            h = data.hoppers.get(hopper_id, {})
            self.update_hopper_level(hopper_id, h.get('level_percent', 0),
                                     switch_open=h.get('switch_open', True),
                                     weight=h.get('weight', 0.0))

        # 更新故障传感器计数
        self.update_fault_count(len(data.faulty_sensors))

        # 更新故障诊断结果
        if data.diagnosis_faults:
            self.update_diagnosis_result(data.diagnosis_faults, data.full_diagnosis_results)

        # 更新激光传感器状态
        for laser_id in self.laser_sensor_labels.keys():
            has_material = data.laser_sensors.get(laser_id, False)
            self.update_laser_sensor_display(laser_id, has_material)

        # 更新料位传感器状态
        if data.level_sensors:
            self.update_level_sensors_display(data.level_sensors)

        # 更新调度结果显示
        if data.schedules:
            self.update_schedule_display(data.schedules, data.executing_bins)

        # 更新统计
        self.update_runtime(data.total_runtime)
        self.update_material_count(data.total_feed_weight)
        self.update_alarm_count(data.alarm_count)
        self.update_active_routes(data.active_routes)
