"""
小仓选择对话框 - 用于选择上料目标小仓
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
                              QLabel, QPushButton, QGroupBox, QButtonGroup,
                              QRadioButton, QScrollArea, QWidget)
from PyQt5.QtCore import Qt, pyqtSignal
from typing import Dict, List, Optional


class SmallBinSelectDialog(QDialog):
    """小仓选择对话框"""

    bin_selected = pyqtSignal(str, str)  # route_id, bin_id

    def __init__(self, route_id: str, route_name: str, target_conveyor: str,
                 available_bins: List[str], parent=None):
        super().__init__(parent)
        self.route_id = route_id
        self.route_name = route_name
        self.target_conveyor = target_conveyor
        self.available_bins = available_bins
        self.selected_bin = None

        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        self.setWindowTitle(f"选择上料目标仓 - {self.route_name}")
        self.setMinimumWidth(400)
        self.setMinimumHeight(350)
        self.setModal(True)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # 标题
        title_label = QLabel(f"路线: {self.route_name}")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: #4A90D9;
                padding: 5px;
            }
        """)
        main_layout.addWidget(title_label)

        # 说明
        info_label = QLabel(f"目标皮带: {self.target_conveyor}  |  请选择目标小仓:")
        info_label.setStyleSheet("color: #8B949E; font-size: 11px;")
        main_layout.addWidget(info_label)

        # 小仓选择区域
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

        # 按列分组显示小仓
        bins_by_section = self._group_bins_by_section()

        for section_name, bins in bins_by_section.items():
            section_group = QGroupBox(section_name)
            section_group.setStyleSheet("""
                QGroupBox {
                    font-weight: bold;
                    color: #E6EDF3;
                    border: 1px solid #30363d;
                    border-radius: 4px;
                    margin-top: 8px;
                    padding-top: 8px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                }
            """)

            section_layout = QGridLayout()
            section_layout.setSpacing(5)

            # 高位储料仓使用6列显示
            is_silo_section = '高位储料仓' in section_name
            col_count = 6 if is_silo_section else 4

            for idx, bin_id in enumerate(bins):
                btn = QRadioButton(bin_id)
                btn.setStyleSheet("""
                    QRadioButton {
                        color: #E6EDF3;
                        padding: 8px;
                        min-width: 60px;
                    }
                    QRadioButton:hover {
                        color: #4A90D9;
                    }
                    QRadioButton::indicator {
                        width: 16px;
                        height: 16px;
                    }
                    QRadioButton::indicator::unchecked {
                        border: 2px solid #484F58;
                        border-radius: 8px;
                        background-color: #21262d;
                    }
                    QRadioButton::indicator::checked {
                        border: 2px solid #4A90D9;
                        border-radius: 8px;
                        background-color: #4A90D9;
                    }
                """)
                btn.bin_id = bin_id
                btn.toggled.connect(lambda checked, b=bin_id: self._on_bin_toggled(b, checked))

                row = idx // col_count
                col = idx % col_count
                section_layout.addWidget(btn, row, col)

            section_group.setLayout(section_layout)
            content_layout.addWidget(section_group)

        content_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area, 1)

        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.confirm_btn = QPushButton("确认")
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 20px;
                font-weight: bold;
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
                padding: 10px 20px;
            }
            QPushButton:hover {
                background-color: #30363d;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        main_layout.addLayout(btn_layout)

    def _group_bins_by_section(self) -> Dict[str, List[str]]:
        """按区段分组小仓"""
        sections = {}

        # 高位储料仓小仓（S1-S12）需要特殊显示为两行
        silo_bins = [b for b in self.available_bins if b.startswith('S')]
        if silo_bins:
            # 分成两行：第一行S1-S6，第二行S7-S12
            row1 = [f'S{i}' for i in range(1, 7) if f'S{i}' in silo_bins]
            row2 = [f'S{i}' for i in range(7, 13) if f'S{i}' in silo_bins]
            sections['高位储料仓 第1行'] = row1
            sections['高位储料仓 第2行'] = row2

        for bin_id in self.available_bins:
            if bin_id.startswith('P1-'):
                section = 'P1配料仓 (D7皮带)'
            elif bin_id.startswith('P2-'):
                section = 'P2配料仓 (D8皮带)'
            elif bin_id.startswith('P3-'):
                section = 'P3配料仓 (D8皮带)'
            elif bin_id.startswith('P4-'):
                section = 'P4配料仓 (D9皮带)'
            else:
                continue  # 跳过S仓（已在上面处理）

            if section not in sections:
                sections[section] = []
            sections[section].append(bin_id)
        return sections

    def _on_bin_toggled(self, bin_id: str, checked: bool):
        """小仓选择改变"""
        if checked:
            self.selected_bin = bin_id
            self.confirm_btn.setEnabled(True)

    def _on_confirm(self):
        """确认选择"""
        if self.selected_bin:
            self.bin_selected.emit(self.route_id, self.selected_bin)
            self.accept()

    def get_selected_bin(self) -> Optional[str]:
        """获取选中的小仓"""
        return self.selected_bin
