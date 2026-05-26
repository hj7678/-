"""
上料点选择对话框 - 用于点击画布后选择上料点

功能：
1. 显示目标小仓信息
2. 显示可选的上料点列表（每条路线一个）
3. 用户选择一个上料点后，确定路线并启动
4. 路线⑧⑨：需额外弹窗选择起点S仓（终点已在画布点击时确定）
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                              QLabel, QPushButton, QButtonGroup,
                              QRadioButton, QScrollArea, QWidget,
                              QMessageBox)
from PyQt5.QtCore import Qt, pyqtSignal
from typing import Dict, List, Optional, Tuple
import config


class FeedPointSelectDialog(QDialog):
    """上料点选择对话框"""

    # 信号: (feed_point, route_id, dest_bin, silo_bin)
    # dest_bin = 终点仓（画布点击的P仓）
    # silo_bin = 起点发料仓（S仓，路线⑧⑨专用）
    feed_point_selected = pyqtSignal(str, str, str, str)

    def __init__(self, bin_id: str, available_routes: List[Tuple[str, str]], parent=None):
        """
        Args:
            bin_id: 点击的小仓ID (如 'P1-1', 'S5')
            available_routes: 可用路线列表 [(feed_point, route_id), ...]
            parent: 父窗口
        """
        super().__init__(parent)
        self.bin_id = bin_id
        self.available_routes = available_routes
        self.selected_feed_point = None
        self.selected_route_id = None

        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        self.setWindowTitle(f"选择上料点 - {self.bin_id}")
        self.setMinimumWidth(450)
        self.setMinimumHeight(300)
        self.setModal(True)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)

        # 标题
        title_label = QLabel(f"目标小仓: {self.bin_id}")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #4A90D9;
                padding: 5px;
            }
        """)
        main_layout.addWidget(title_label)

        # 说明
        info_label = QLabel("请选择上料路线（点击对应的上料点）:")
        info_label.setStyleSheet("color: #8B949E; font-size: 12px; padding: 5px;")
        main_layout.addWidget(info_label)

        # 上料点选择区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #30363d;
                border-radius: 4px;
                background-color: #0d1117;
            }
        """)

        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setSpacing(10)

        # 创建单选按钮组
        self.button_group = QButtonGroup()

        for feed_point, route_id in self.available_routes:
            route_config = config.FEED_ROUTES.get(route_id, {})
            route_name = route_config.get('name', route_id)
            feed_point_name = config.FEED_POINTS.get(feed_point, {}).get('name', feed_point)

            # 创建路线选项卡片
            route_card = QWidget()
            route_card.setStyleSheet("""
                QWidget {
                    background-color: #161b22;
                    border: 1px solid #30363d;
                    border-radius: 6px;
                    padding: 10px;
                }
                QWidget:hover {
                    border-color: #4A90D9;
                }
            """)

            card_layout = QHBoxLayout(route_card)
            card_layout.setContentsMargins(10, 5, 10, 5)

            # 单选按钮
            radio_btn = QRadioButton()
            radio_btn.setStyleSheet("""
                QRadioButton::indicator {
                    width: 20px;
                    height: 20px;
                    border-radius: 10px;
                }
                QRadioButton::indicator::unchecked {
                    border: 2px solid #484F58;
                    background-color: #21262d;
                }
                QRadioButton::indicator::checked {
                    border: 2px solid #4A90D9;
                    background-color: #4A90D9;
                }
            """)
            card_layout.addWidget(radio_btn)

            # 路线信息
            info_layout = QVBoxLayout()
            info_layout.setSpacing(3)

            route_label = QLabel(f"{route_name} ({route_id})")
            route_label.setStyleSheet("""
                QLabel {
                    color: #E6EDF3;
                    font-size: 13px;
                    font-weight: bold;
                }
            """)
            info_layout.addWidget(route_label)

            feed_label = QLabel(f"上料点: {feed_point_name} ({feed_point})")
            feed_label.setStyleSheet("""
                QLabel {
                    color: #8B949E;
                    font-size: 11px;
                }
            """)
            info_layout.addWidget(feed_label)

            # 添加物料类型说明
            material_types = route_config.get('material_types', [])
            if material_types:
                if len(material_types) == 1:
                    material_name = self._get_material_display_name(material_types[0])
                    mat_label = QLabel(f"物料: {material_name}")
                else:
                    mat_label = QLabel(f"物料: {len(material_types)}种骨料随机")
                mat_label.setStyleSheet("""
                    QLabel {
                        color: #F39C12;
                        font-size: 11px;
                    }
                """)
                info_layout.addWidget(mat_label)

            info_layout.addStretch()
            card_layout.addLayout(info_layout, 1)

            content_layout.addWidget(route_card)

            # 关联按钮和数据
            self.button_group.addButton(radio_btn)
            radio_btn.route_data = (feed_point, route_id)
            radio_btn.toggled.connect(
                lambda checked, rd=(feed_point, route_id): self._on_route_toggled(rd, checked)
            )

        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area, 1)

        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)

        self.confirm_btn = QPushButton("启动路线")
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 12px 30px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2EA043;
            }
            QPushButton:disabled {
                background-color: #21262d;
                color: #484F58;
            }
        """)
        self.confirm_btn.clicked.connect(self._on_confirm)
        btn_layout.addWidget(self.confirm_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #21262d;
                color: #E6EDF3;
                border: 1px solid #30363d;
                border-radius: 4px;
                padding: 12px 30px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #30363d;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        main_layout.addLayout(btn_layout)

    def _get_material_display_name(self, material_type: str) -> str:
        """获取物料显示名称"""
        material_names = {
            'stone_powder': '石粉',
            'aggregate_10mm': '10mm碎石',
            'aggregate_20mm': '20mm碎石',
        }
        return material_names.get(material_type, material_type)

    def _on_route_toggled(self, route_data: Tuple[str, str], checked: bool):
        """路线选择改变"""
        if checked:
            self.selected_feed_point, self.selected_route_id = route_data
            self.confirm_btn.setEnabled(True)
            self.confirm_btn.setText(f"启动 {config.FEED_ROUTES.get(self.selected_route_id, {}).get('name', self.selected_route_id)}")

    def _on_confirm(self):
        """确认选择"""
        if self.selected_feed_point and self.selected_route_id:
            # 路线⑧⑨：不再需要手动选S仓，系统自动选择
            self.feed_point_selected.emit(
                self.selected_feed_point,
                self.selected_route_id,
                self.bin_id,  # dest_bin
                ''             # silo_bin由系统自动选择
            )
            self.accept()

    def _show_silo_bin_selection(self):
        """显示高位储料仓选择（路线⑧⑨专用：选S仓）"""
        from views.bin_select_dialog import SmallBinSelectDialog

        route_name = config.FEED_ROUTES[self.selected_route_id]['name']
        available_bins = [f'S{i}' for i in range(1, 13)]

        silo_dialog = SmallBinSelectDialog(
            self.selected_route_id,
            f"{route_name} - 选择发料仓",
            'D1/D2',
            available_bins,
            self
        )
        silo_dialog.bin_selected.connect(self._on_silo_bin_selected)
        silo_dialog.exec_()

    def _on_silo_bin_selected(self, route_id: str, silo_bin: str):
        """S仓选择完成，发出信号"""
        self.feed_point_selected.emit(
            self.selected_feed_point,
            self.selected_route_id,
            self.bin_id,  # dest_bin = 画布点击的P仓
            silo_bin       # silo_bin = S仓
        )
        self.accept()

    def get_selected_data(self) -> Optional[Tuple[str, str, str]]:
        """获取选中的数据 (feed_point, route_id, dest_bin)"""
        if self.selected_feed_point and self.selected_route_id:
            return (self.selected_feed_point, self.selected_route_id, self.bin_id)
        return None
