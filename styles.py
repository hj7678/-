"""
样式定义 - 深色工业风格界面
"""

from PyQt5.QtGui import QColor, QPalette, QFont, QIcon
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt


# 颜色常量
DARK_BG = '#1a1a2e'
PANEL_BG = '#16213e'
PANEL_BORDER = '#0f3460'
TEXT_COLOR = '#ECF0F1'
TEXT_SECONDARY = '#BDC3C7'
ACCENT_BLUE = '#4A90D9'
ACCENT_GREEN = '#2ECC71'
ACCENT_RED = '#E74C3C'
ACCENT_ORANGE = '#F39C12'
ACCENT_PURPLE = '#8E44AD'


def get_dark_palette() -> QPalette:
    """获取深色主题调色板"""
    palette = QPalette()

    # 窗口背景
    palette.setColor(QPalette.Window, QColor(DARK_BG))
    palette.setColor(QPalette.WindowText, QColor(TEXT_COLOR))

    # 面板背景
    palette.setColor(QPalette.Base, QColor(PANEL_BG))
    palette.setColor(QPalette.AlternateBase, QColor('#1e2a4a'))

    # 按钮
    palette.setColor(QPalette.Button, QColor(PANEL_BORDER))
    palette.setColor(QPalette.ButtonText, QColor(TEXT_COLOR))
    palette.setColor(QPalette.Highlight, QColor(ACCENT_BLUE))
    palette.setColor(QPalette.HighlightedText, QColor(TEXT_COLOR))

    # 状态颜色
    palette.setColor(QPalette.Link, QColor(ACCENT_BLUE))
    palette.setColor(QPalette.LinkVisited, QColor(ACCENT_PURPLE))

    return palette


def get_panel_style() -> str:
    """面板样式"""
    return f"""
        QWidget {{
            background-color: {PANEL_BG};
            color: {TEXT_COLOR};
            font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
            font-size: 13px;
        }}
        QLabel {{
            color: {TEXT_COLOR};
        }}
    """


def get_group_box_style() -> str:
    """分组框样式"""
    return f"""
        QGroupBox {{
            background-color: {PANEL_BG};
            border: 1px solid {PANEL_BORDER};
            border-radius: 5px;
            margin-top: 6px;
            padding: 6px;
            font-weight: bold;
            font-size: 11px;
            color: {TEXT_COLOR};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 6px;
            color: {ACCENT_BLUE};
        }}
    """


def get_button_style(color: str = ACCENT_BLUE, hover_color: str = None) -> str:
    """按钮样式"""
    if hover_color is None:
        hover_color = lighten_color(color, 20)
    return f"""
        QPushButton {{
            background-color: {color};
            color: white;
            border: none;
            border-radius: 4px;
            padding: 8px 16px;
            font-weight: bold;
            min-width: 80px;
        }}
        QPushButton:hover {{
            background-color: {hover_color};
        }}
        QPushButton:pressed {{
            background-color: {darken_color(color, 10)};
        }}
        QPushButton:disabled {{
            background-color: #4a5568;
            color: #718096;
        }}
    """


def get_small_button_style(color: str = ACCENT_BLUE, hover_color: str = None) -> str:
    """小尺寸按钮样式，适用于正方形或紧凑按钮"""
    if hover_color is None:
        hover_color = lighten_color(color, 20)
    return f"""
        QPushButton {{
            background-color: {color};
            color: white;
            border: none;
            border-radius: 4px;
            padding: 0px;
            font-size: 10px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {hover_color};
        }}
        QPushButton:pressed {{
            background-color: {darken_color(color, 10)};
        }}
        QPushButton:disabled {{
            background-color: #4a5568;
            color: #718096;
        }}
    """


def get_start_button_style() -> str:
    """启动按钮样式"""
    return get_button_style(ACCENT_GREEN, '#27AE60')


def get_stop_button_style() -> str:
    """停止按钮样式"""
    return get_button_style(ACCENT_RED, '#C0392B')


def get_emergency_button_style() -> str:
    """紧急停止按钮样式"""
    return get_button_style(ACCENT_RED, '#C0392B')


def get_status_indicator_style(active=True, fault=False) -> str:
    """状态指示器样式

    Args:
        active: 是否激活（绿色）
        fault: 是否故障（红色）
    """
    if fault:
        color = ACCENT_RED  # 故障状态 - 红色
    elif active:
        color = ACCENT_GREEN  # 运行状态 - 绿色
    else:
        color = '#7F8C8D'  # 停止状态 - 灰色
    return f"""
        background-color: {color};
        border-radius: 6px;
        min-width: 12px;
        max-width: 12px;
        min-height: 12px;
        max-height: 12px;
    """


def get_slider_style() -> str:
    """滑块样式"""
    return f"""
        QSlider::groove:horizontal {{
            border: 1px solid #4a5568;
            height: 8px;
            background: #2d3748;
            border-radius: 4px;
        }}
        QSlider::handle:horizontal {{
            background: {ACCENT_BLUE};
            border: 1px solid #4a90d9;
            width: 18px;
            margin: -5px 0;
            border-radius: 9px;
        }}
        QSlider::handle:horizontal:hover {{
            background: {lighten_color(ACCENT_BLUE, 15)};
        }}
    """


def get_table_style() -> str:
    """表格样式"""
    return f"""
        QTableWidget, QTableView {{
            background-color: {DARK_BG};
            alternate-background-color: {PANEL_BG};
            color: {TEXT_COLOR};
            gridline-color: {PANEL_BORDER};
            border: 1px solid {PANEL_BORDER};
            border-radius: 4px;
        }}
        QTableWidget::item, QTableView::item {{
            padding: 4px;
        }}
        QTableWidget::item:selected, QTableView::item:selected {{
            background-color: {ACCENT_BLUE};
            color: white;
        }}
        QHeaderView::section {{
            background-color: {PANEL_BORDER};
            color: {TEXT_COLOR};
            padding: 6px;
            border: none;
            font-weight: bold;
        }}
    """


def get_log_table_style() -> str:
    """日志表格样式"""
    return f"""
        QTableWidget {{
            background-color: {DARK_BG};
            alternate-background-color: #1e1e32;
            color: {TEXT_COLOR};
            gridline-color: {PANEL_BORDER};
            border: none;
            font-family: "Consolas", "Courier New", monospace;
            font-size: 12px;
        }}
        QTableWidget::item {{
            padding: 3px 6px;
        }}
        QHeaderView::section {{
            background-color: {PANEL_BORDER};
            color: {TEXT_COLOR};
            padding: 4px;
            border: none;
            font-weight: bold;
        }}
    """


def get_line_edit_style() -> str:
    """输入框样式"""
    return f"""
        QLineEdit {{
            background-color: {DARK_BG};
            color: {TEXT_COLOR};
            border: 1px solid {PANEL_BORDER};
            border-radius: 4px;
            padding: 6px;
        }}
        QLineEdit:focus {{
            border-color: {ACCENT_BLUE};
        }}
    """


def get_combo_box_style() -> str:
    """下拉框样式"""
    return f"""
        QComboBox {{
            background-color: {DARK_BG};
            color: {TEXT_COLOR};
            border: 1px solid {PANEL_BORDER};
            border-radius: 4px;
            padding: 6px 12px;
        }}
        QComboBox:hover {{
            border-color: {ACCENT_BLUE};
        }}
        QComboBox::drop-down {{
            border: none;
        }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 5px solid transparent;
            border-right: 5px solid transparent;
            border-top: 6px solid {TEXT_COLOR};
            margin-right: 10px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {DARK_BG};
            color: {TEXT_COLOR};
            selection-background-color: {ACCENT_BLUE};
            border: 1px solid {PANEL_BORDER};
        }}
    """


def get_toolbar_style() -> str:
    """工具栏样式"""
    return f"""
        QToolBar {{
            background-color: {PANEL_BG};
            border: none;
            spacing: 8px;
            padding: 4px;
        }}
        QToolBar::separator {{
            background-color: {PANEL_BORDER};
            width: 1px;
            margin: 4px 8px;
        }}
    """


def get_menu_style() -> str:
    """菜单样式"""
    return f"""
        QMenuBar {{
            background-color: {PANEL_BG};
            color: {TEXT_COLOR};
        }}
        QMenuBar::item:selected {{
            background-color: {PANEL_BORDER};
        }}
        QMenu {{
            background-color: {PANEL_BG};
            color: {TEXT_COLOR};
            border: 1px solid {PANEL_BORDER};
        }}
        QMenu::item:selected {{
            background-color: {ACCENT_BLUE};
        }}
    """


def get_small_combo_style() -> str:
    """紧凑下拉框样式"""
    return f"""
        QComboBox {{
            background-color: #1a1a2e;
            color: #ECF0F1;
            border: 1px solid #0f3460;
            border-radius: 3px;
            padding: 2px 4px;
            font-size: 9px;
        }}
        QComboBox:hover {{
            border-color: #4A90D9;
        }}
        QComboBox::drop-down {{
            border: none;
        }}
        QComboBox::down-arrow {{
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid #ECF0F1;
            margin-right: 6px;
        }}
        QComboBox QAbstractItemView {{
            background-color: #1a1a2e;
            color: #ECF0F1;
            selection-background-color: #4A90D9;
            border: 1px solid #0f3460;
            font-size: 9px;
        }}
    """


def get_scrollbar_style() -> str:
    """滚动条样式"""
    return f"""
        QScrollBar:vertical {{
            background-color: {DARK_BG};
            width: 12px;
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {PANEL_BORDER};
            border-radius: 5px;
            min-height: 20px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {ACCENT_BLUE};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar:horizontal {{
            background-color: {DARK_BG};
            height: 12px;
            border-radius: 6px;
        }}
        QScrollBar::handle:horizontal {{
            background-color: {PANEL_BORDER};
            border-radius: 5px;
            min-width: 20px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background-color: {ACCENT_BLUE};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
    """


def get_title_font(size: int = 14) -> QFont:
    """标题字体"""
    font = QFont()
    font.setPointSize(size)
    font.setBold(True)
    return font


def get_default_font(size: int = 13) -> QFont:
    """默认字体"""
    font = QFont()
    font.setPointSize(size)
    return font


def get_monospace_font(size: int = 12) -> QFont:
    """等宽字体"""
    font = QFont()
    font.setFamily("Consolas")
    font.setPointSize(size)
    return font


# 颜色工具函数
def lighten_color(hex_color: str, percent: int) -> str:
    """使颜色变亮"""
    hex_color = hex_color.lstrip('#')
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)

    def clamp(val):
        return min(255, max(0, val + int(255 * percent / 100)))

    return f"#{clamp(r):02x}{clamp(g):02x}{clamp(b):02x}"


def darken_color(hex_color: str, percent: int) -> str:
    """使颜色变暗"""
    return lighten_color(hex_color, -percent)
