"""
日志面板 - Log Panel
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
                             QTableWidget, QTableWidgetItem, QPushButton,
                             QHeaderView, QAbstractItemView)
from PyQt5.QtCore import Qt, QTime
from PyQt5.QtGui import QColor
import styles
import config


class LogEntry:
    """日志条目"""

    LOG_TYPES = {
        'INFO': ('#2ECC71', '信息'),
        'WARNING': ('#F39C12', '警告'),
        'ERROR': ('#E74C3C', '错误'),
        'SENSOR': ('#4A90D9', '传感器'),
        'CONVEYOR': ('#9B59B6', '皮带'),
        'MATERIAL': ('#F39C12', '物料'),
        'ALARM': ('#E74C3C', '报警'),
    }

    def __init__(self, log_type: str, message: str, timestamp: int = None):
        self.log_type = log_type
        self.message = message
        self.timestamp = timestamp if timestamp is not None else QTime.currentTime().msecsSinceStartOfDay()
        self.time_str = QTime.currentTime().addMSecs(
            -(QTime.currentTime().msecsSinceStartOfDay() - self.timestamp)
        ).toString("hh:mm:ss.zzz")[:12]

    def get_type_color(self) -> str:
        """获取类型颜色"""
        return self.LOG_TYPES.get(self.log_type, ('#BDC3C7', '未知'))[0]


class LogPanel(QWidget):
    """日志面板组件"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.log_entries = []
        self.max_entries = config.LOG_CONFIG['max_entries']

        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # 日志表格
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(['时间', '类型', '消息', ''])
        self.table.verticalHeader().setVisible(False)

        # 表格设置
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)

        # 列宽设置
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 90)
        self.table.setColumnWidth(1, 50)
        self.table.setColumnWidth(3, 0)  # 隐藏列

        self.table.setStyleSheet(styles.get_log_table_style())
        main_layout.addWidget(self.table)

        # 按钮行
        button_layout = QHBoxLayout()

        clear_btn = QPushButton("清空日志")
        clear_btn.setStyleSheet(styles.get_button_style('#7F8C8D'))
        clear_btn.clicked.connect(self.clear_logs)
        button_layout.addWidget(clear_btn)

        export_btn = QPushButton("导出CSV")
        export_btn.setStyleSheet(styles.get_button_style('#4A90D9'))
        export_btn.clicked.connect(self.export_csv)
        button_layout.addWidget(export_btn)

        button_layout.addStretch()

        main_layout.addLayout(button_layout)

    def add_log(self, log_type: str, message: str):
        """添加日志"""
        entry = LogEntry(log_type, message)

        # 限制日志数量
        if len(self.log_entries) >= self.max_entries:
            self.log_entries.pop(0)
            self.table.removeRow(0)

        self.log_entries.append(entry)
        self._add_row_to_table(entry, len(self.log_entries) - 1)

    def _add_row_to_table(self, entry: LogEntry, row_index: int):
        """添加行到表格"""
        self.table.insertRow(row_index)

        # 时间
        time_item = QTableWidgetItem(entry.time_str)
        time_item.setForeground(QColor('#BDC3C7'))
        self.table.setItem(row_index, 0, time_item)

        # 类型
        type_item = QTableWidgetItem(entry.log_type)
        type_color = entry.get_type_color()
        type_item.setForeground(QColor(type_color))
        type_item.setFont(styles.get_monospace_font(11))
        self.table.setItem(row_index, 1, type_item)

        # 消息
        msg_item = QTableWidgetItem(entry.message)
        msg_item.setForeground(QColor('#ECF0F1'))
        self.table.setItem(row_index, 2, msg_item)

        # 隐藏原始时间戳
        ts_item = QTableWidgetItem(str(entry.timestamp))
        ts_item.setForeground(QColor('transparent'))
        self.table.setItem(row_index, 3, ts_item)

        # 滚动到最后一行
        self.table.scrollToBottom()

    def clear_logs(self):
        """清空日志"""
        self.log_entries.clear()
        self.table.setRowCount(0)

    def export_csv(self):
        """导出CSV"""
        from PyQt5.QtWidgets import QFileDialog
        from PyQt5.QtCore import QDateTime

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "导出日志",
            f"simulation_log_{QDateTime.currentDateTime().toString('yyyyMMdd_hhmmss')}.csv",
            "CSV Files (*.csv);;All Files (*)"
        )

        if filename:
            try:
                with open(filename, 'w', encoding='utf-8-sig') as f:
                    f.write("时间,类型,消息\n")
                    for entry in self.log_entries:
                        # 重新计算时间字符串
                        time_ms = entry.timestamp
                        hours = time_ms // 3600000
                        time_ms %= 3600000
                        minutes = time_ms // 60000
                        time_ms %= 60000
                        seconds = time_ms // 1000
                        ms = time_ms % 1000
                        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}.{ms:03d}"

                        f.write(f'"{time_str}","{entry.log_type}","{entry.message}"\n')

                self.add_log('INFO', f'日志已导出: {filename}')
            except Exception as e:
                self.add_log('ERROR', f'导出失败: {str(e)}')

    def get_logs(self) -> list:
        """获取所有日志"""
        return self.log_entries

    # 便捷的日志方法
    def log_info(self, message: str):
        self.add_log('INFO', message)

    def log_warning(self, message: str):
        self.add_log('WARNING', message)

    def log_error(self, message: str):
        self.add_log('ERROR', message)

    def log_sensor(self, sensor_id: str, triggered: bool):
        state = "触发" if triggered else "释放"
        self.add_log('SENSOR', f'{sensor_id} {state}')

    def log_conveyor(self, conveyor_name: str, action: str):
        self.add_log('CONVEYOR', f'{conveyor_name} {action}')

    def log_material(self, action: str):
        self.add_log('MATERIAL', action)

    def log_alarm(self, message: str):
        self.add_log('ALARM', message)
