"""
运行信息显示面板 - 分系统/D6/D7/D8/D9 五个日志区域
"""
from datetime import datetime
from PyQt5.QtWidgets import QTextEdit, QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt
import config


class LogSection(QWidget):
    """单个日志区域"""
    MAX_ENTRIES = 200

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(2)

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet("""
            QLabel {
                font-size: 11px; font-weight: bold; color: #4A90D9;
                padding: 1px 4px;
            }
        """)
        layout.addWidget(self._title_label)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumHeight(120)
        self._text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {config.COLORS['panel']};
                color: #C0C8D0;
                border: 1px solid {config.COLORS['panel_border']};
                border-radius: 4px;
                font-size: 11px;
                font-family: "Consolas", "Microsoft YaHei", monospace;
                padding: 2px;
            }}
            QScrollBar:vertical {{
                background: #21262d; width: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: #484F58; border-radius: 3px; min-height: 15px;
            }}
        """)
        layout.addWidget(self._text)

    def add_log(self, message: str, color: str = "#C0C8D0"):
        now = datetime.now().strftime("%H:%M:%S")
        line = f'<span style="color:#6E7681;">[{now}]</span> <span style="color:{color};">{message}</span>'
        self._text.append(line)
        doc = self._text.document()
        if doc.blockCount() > self.MAX_ENTRIES:
            cursor = self._text.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.movePosition(cursor.Down, cursor.KeepAnchor,
                               doc.blockCount() - self.MAX_ENTRIES)
            cursor.removeSelectedText()

    def clear(self):
        self._text.clear()

    def set_title_color(self, color: str):
        self._title_label.setStyleSheet(f"""
            QLabel {{
                font-size: 11px; font-weight: bold; color: {color};
                padding: 1px 4px;
            }}
        """)


class OperationLogPanel(QWidget):
    """多区域运行信息面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sections = {}
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 4, 0, 0)
        main_layout.setSpacing(0)

        # 系统日志（全局）
        self._sys_log = LogSection("系统")
        self._sys_log.set_title_color("#8B949E")
        self._sections["sys"] = self._sys_log
        main_layout.addWidget(self._sys_log)

        # 四个皮带日志水平排列
        belt_row = QHBoxLayout()
        belt_row.setSpacing(4)

        self._d6_log = LogSection("D6 Cart4 高位储料仓")
        self._d6_log.set_title_color("#3498DB")
        self._sections["D6"] = self._d6_log

        self._d7_log = LogSection("D7 Cart1 配料站P1")
        self._d7_log.set_title_color("#2ECC71")
        self._sections["D7"] = self._d7_log

        self._d8_log = LogSection("D8 Cart2 配料站P2/P3")
        self._d8_log.set_title_color("#F39C12")
        self._sections["D8"] = self._d8_log

        self._d9_log = LogSection("D9 Cart3 配料站P4")
        self._d9_log.set_title_color("#E74C3C")
        self._sections["D9"] = self._d9_log

        for log in [self._d6_log, self._d7_log, self._d8_log, self._d9_log]:
            belt_row.addWidget(log)
        main_layout.addLayout(belt_row)

    def add_log(self, message: str, color: str = "#C0C8D0"):
        """系统日志"""
        self._sys_log.add_log(message, color)

    def add_belt_log(self, belt_id: str, message: str, color: str = "#C0C8D0"):
        """皮带日志"""
        if belt_id in self._sections:
            self._sections[belt_id].add_log(message, color)

    def clear(self):
        for s in self._sections.values():
            s.clear()
