"""
layout_editor.py - 布局编辑器
可视化拖动调整UI布局和大小，保存到pos.py
功能：
  - 拖动调整所有元素位置
  - 调整皮带端点位置
  - 调整元素大小
  - 多选批量操作
  - 网格吸附
  - 完整的保存/加载功能
"""

import sys
import math
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QScrollArea, QSpinBox, QCheckBox, QMessageBox, QApplication,
    QGroupBox, QDoubleSpinBox, QTextEdit, QSplitter, QToolBar,
    QAction, QStatusBar
)
from PyQt5.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QIcon

import pos


class DraggableItem:
    """可拖动项目基类"""
    def __init__(self, item_id, item_type, x, y):
        self.id = item_id
        self.type = item_type
        self.x = float(x)
        self.y = float(y)
        self.selected = False
        self.width = 30
        self.height = 20
        self.name = item_id

    def contains(self, mx, my):
        hw, hh = self.width / 2, self.height / 2
        return (self.x - hw <= mx <= self.x + hw and
                self.y - hh <= my <= self.y + hh)

    def move_by(self, dx, dy):
        self.x += dx
        self.y += dy

    def get_rect(self):
        return QRect(
            int(self.x - self.width / 2),
            int(self.y - self.height / 2),
            int(self.width),
            int(self.height)
        )


class SensorItem(DraggableItem):
    """传感器项目"""
    def __init__(self, sensor_id, x, y, name=""):
        super().__init__(sensor_id, 'sensor', x, y)
        self.width = 20
        self.height = 20
        self.name = name or sensor_id


class FeedPointItem(DraggableItem):
    """上料点项目"""
    def __init__(self, feed_id, x, y, name=""):
        super().__init__(feed_id, 'feed_point', x, y)
        self.width = 60
        self.height = 40
        self.name = name or feed_id


class HopperItem(DraggableItem):
    """中转斗项目"""
    def __init__(self, hopper_id, x, y, width=45, height=30, name=""):
        super().__init__(hopper_id, 'hopper', x, y)
        self.width = float(width)
        self.height = float(height)
        self.name = name or hopper_id


class BatchingStationItem(DraggableItem):
    """高位配料站项目"""
    def __init__(self, x, y, width=350, height=216, name="高位配料站"):
        super().__init__('batching_station', 'batching_station', x, y)
        self.width = float(width)
        self.height = float(height)
        self.name = name


class HighSiloItem(DraggableItem):
    """高位储料仓项目"""
    def __init__(self, x, y, width=200, height=140, name="高位储料仓"):
        super().__init__('high_silo', 'high_silo', x, y)
        self.width = float(width)
        self.height = float(height)
        self.name = name


class ConveyorItem:
    """皮带项目 - 起点到终点"""
    def __init__(self, conv_id, x1, y1, x2, y2, name=""):
        self.id = conv_id
        self.x1 = float(x1)
        self.y1 = float(y1)
        self.x2 = float(x2)
        self.y2 = float(y2)
        self.name = name or conv_id
        self.selected = False
        self.handle_size = 12

    def contains_point(self, px, py, threshold=12):
        """检查点是否靠近皮带线"""
        dx = self.x2 - self.x1
        dy = self.y2 - self.y1
        length_sq = dx * dx + dy * dy

        if length_sq == 0:
            return math.sqrt((px - self.x1) ** 2 + (py - self.y1) ** 2) < threshold

        t = max(0, min(1, ((px - self.x1) * dx + (py - self.y1) * dy) / length_sq))
        proj_x = self.x1 + t * dx
        proj_y = self.y1 + t * dy
        dist = math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)
        return dist < threshold

    def get_endpoint(self, px, py, threshold=15):
        """获取靠近的端点: 'start', 'end', 或 None"""
        d1 = math.sqrt((px - self.x1) ** 2 + (py - self.y1) ** 2)
        d2 = math.sqrt((px - self.x2) ** 2 + (py - self.y2) ** 2)

        if d1 < threshold:
            return 'start'
        elif d2 < threshold:
            return 'end'
        return None

    def move_endpoint(self, endpoint, dx, dy):
        if endpoint == 'start':
            self.x1 += dx
            self.y1 += dy
        else:
            self.x2 += dx
            self.y2 += dy

    def contains(self, mx, my):
        return self.contains_point(mx, my)


class LayoutCanvas(QWidget):
    """布局画布"""
    selection_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []       # 所有可拖动元素
        self.conveyors = []   # 皮带列表
        self.selected = None  # 当前选中的元素 (item或conveyor)
        self.is_dragging = False
        self.drag_start = QPoint()
        self.drag_mode = None  # 'move', 'resize', 'endpoint'
        self.endpoint = None
        self.resize_handle = None

        self.grid_size = 10
        self.snap_to_grid = True
        self.show_labels = True
        self.show_grid = True

        self.selection_rect_start = None
        self.is_selecting = False

        # 颜色定义
        self.bg_color = QColor('#1a1a2e')
        self.grid_color = QColor('#2a2a3e')
        self.colors = {
            'sensor': QColor('#E74C3C'),
            'feed_point': QColor('#3498DB'),
            'hopper': QColor('#9B59B6'),
            'batching_station': QColor('#E67E22'),
            'high_silo': QColor('#16A085'),
            'conveyor': QColor('#FFFFFF'),
            'selected': QColor('#2ECC71'),
        }

        self.setMinimumSize(1200, 700)
        self.setStyleSheet("border: 2px solid #444; background: #1a1a2e;")
        self.load_from_pos()

    def load_from_pos(self):
        """从pos.py加载所有元素"""
        self.items.clear()
        self.conveyors.clear()

        # 加载传感器
        for sid, s in pos.SENSORS.items():
            self.items.append(SensorItem(sid, s['x'], s['y'], s.get('name', sid)))

        # 加载上料点
        for fid, f in pos.FEED_POINTS.items():
            self.items.append(FeedPointItem(fid, f['x'], f['y'], f.get('name', fid)))

        # 加载中转斗
        for hid, h in pos.TRANSFER_HOPPERS.items():
            self.items.append(HopperItem(
                hid, h['x'], h['y'],
                h.get('width', 45), h.get('height', 30),
                h.get('name', hid)
            ))

        # 加载高位配料站
        bs = pos.BATCHING_STATION
        self.items.append(BatchingStationItem(
            bs['x'], bs['y'], bs['width'], bs['height'], bs.get('name', '高位配料站')
        ))

        # 加载高位储料仓
        sil = pos.HIGH_SILO
        self.items.append(HighSiloItem(
            sil['x'], sil['y'], sil['width'], sil['height'], sil.get('name', '高位储料仓')
        ))

        # 加载皮带
        for cid, c in pos.CONVEYORS.items():
            self.conveyors.append(ConveyorItem(
                cid, c['x1'], c['y1'], c['x2'], c['y2'], c.get('name', cid)
            ))

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), self.bg_color)

        # 绘制网格
        if self.show_grid:
            self._draw_grid(painter)

        # 绘制皮带
        for conv in self.conveyors:
            self._draw_conveyor(painter, conv)

        # 绘制元素
        for item in self.items:
            self._draw_item(painter, item)

        # 绘制选择框
        if self.is_selecting and self.selection_rect_start:
            painter.setPen(QPen(self.colors['selected'], 1, Qt.DashLine))
            painter.setBrush(QBrush(QColor(46, 204, 113, 30)))
            rect = QRect(self.selection_rect_start, self.selection_rect_end).normalized()
            painter.drawRect(rect)

    def _draw_grid(self, painter):
        painter.setPen(QPen(self.grid_color, 1))
        for x in range(0, self.width(), self.grid_size):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), self.grid_size):
            painter.drawLine(0, y, self.width(), y)

    def _draw_conveyor(self, painter, conv):
        color = self.colors['selected'] if conv.selected else self.colors['conveyor']
        pen = QPen(color, 4)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(int(conv.x1), int(conv.y1), int(conv.x2), int(conv.y2))

        # 绘制方向箭头
        self._draw_arrow(painter, conv.x1, conv.y1, conv.x2, conv.y2, color)

        # 绘制标签
        if self.show_labels:
            mid_x = (conv.x1 + conv.x2) / 2
            mid_y = (conv.y1 + conv.y2) / 2
            painter.setPen(QPen(QColor('#00FF00'), 9))
            painter.setFont(QFont('Arial', 8, QFont.Bold))
            painter.drawText(int(mid_x - 12), int(mid_y + 3), conv.name)

        # 选中时绘制端点
        if conv.selected:
            hs = conv.handle_size
            half = hs / 2
            painter.setBrush(QBrush(self.colors['selected']))
            painter.setPen(QPen(QColor('#FFFFFF'), 1))
            painter.drawRect(int(conv.x1 - half), int(conv.y1 - half), hs, hs)
            painter.drawRect(int(conv.x2 - half), int(conv.y2 - half), hs, hs)

    def _draw_arrow(self, painter, x1, y1, x2, y2, color):
        angle = math.atan2(y2 - y1, x2 - x1)
        arrow_len = 12
        arrow_angle = 0.4

        x3 = x2 - arrow_len * math.cos(angle - arrow_angle)
        y3 = y2 - arrow_len * math.sin(angle - arrow_angle)
        x4 = x2 - arrow_len * math.cos(angle + arrow_angle)
        y4 = y2 - arrow_len * math.sin(angle + arrow_angle)

        painter.setPen(QPen(color, 2))
        painter.drawLine(int(x2), int(y2), int(x3), int(y3))
        painter.drawLine(int(x2), int(y2), int(x4), int(y4))

    def _draw_item(self, painter, item):
        color = self.colors['selected'] if item.selected else self.colors.get(item.type, QColor('#FFFFFF'))
        rect = item.get_rect()

        painter.setPen(QPen(color, 2))
        painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 50)))
        painter.drawRect(rect)

        # 绘制调整大小的手柄
        if item.selected:
            hs = 6
            cx, cy = item.x, item.y
            hw, hh = item.width / 2, item.height / 2

            corners = [
                (cx - hw, cy - hh),
                (cx + hw - hs, cy - hh),
                (cx - hw, cy + hh - hs),
                (cx + hw - hs, cy + hh - hs),
            ]
            painter.setBrush(QBrush(self.colors['selected']))
            for x, y in corners:
                painter.drawRect(int(x), int(y), hs, hs)

        # 绘制标签
        if self.show_labels:
            painter.setPen(QPen(color))
            painter.setFont(QFont('Arial', 7))
            painter.drawText(rect.center().x() - len(item.name) * 2, rect.center().y() + 3, item.name)

    def mousePressEvent(self, event):
        mx, my = event.x(), event.y()

        # 先检查是否点击了皮带的端点
        for conv in reversed(self.conveyors):
            if conv.selected:
                ep = conv.get_endpoint(mx, my)
                if ep:
                    self.selected = conv
                    self.is_dragging = True
                    self.drag_mode = 'endpoint'
                    self.endpoint = ep
                    self.drag_start = event.pos()
                    return

        # 检查是否点击了皮带的中间部分
        for conv in reversed(self.conveyors):
            if conv.contains_point(mx, my):
                self._clear_selection()
                conv.selected = True
                self.selected = conv
                self.is_dragging = True
                self.drag_mode = 'endpoint'
                self.endpoint = 'start'
                self.drag_start = event.pos()
                self.update()
                self.selection_changed.emit(f"皮带: {conv.name}")
                return

        # 检查是否点击了元素
        for item in reversed(self.items):
            if item.contains(mx, my):
                self._clear_selection()
                item.selected = True
                self.selected = item
                self.is_dragging = True
                self.drag_mode = 'move'
                self.drag_start = event.pos()
                self.update()
                self.selection_changed.emit(f"{item.type}: {item.name}")
                return

        # 点击空白区域 - 开始框选
        self._clear_selection()
        self.is_selecting = True
        self.selection_rect_start = event.pos()
        self.selection_rect_end = event.pos()

    def mouseMoveEvent(self, event):
        if not self.is_dragging:
            if self.is_selecting:
                self.selection_rect_end = event.pos()
                self.update()
            return

        dx = event.x() - self.drag_start.x()
        dy = event.y() - self.drag_start.y()

        if self.drag_mode == 'endpoint' and isinstance(self.selected, ConveyorItem):
            if self.snap_to_grid:
                dx = self._snap(dx)
                dy = self._snap(dy)
            if dx == 0 and dy == 0:
                return
            self.selected.move_endpoint(self.endpoint, dx, dy)
            self.drag_start = event.pos()
            self.update()

        elif self.drag_mode == 'move' and isinstance(self.selected, DraggableItem):
            if self.snap_to_grid:
                dx = self._snap(dx)
                dy = self._snap(dy)
            if dx == 0 and dy == 0:
                return
            self.selected.move_by(dx, dy)
            self.drag_start = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if self.is_selecting:
            self.is_selecting = False
            rect = QRect(self.selection_rect_start, self.selection_rect_end).normalized()
            for item in self.items:
                if rect.contains(item.get_rect()):
                    item.selected = True
            self.update()
            return

        if self.is_dragging:
            self.is_dragging = False
            self.drag_mode = None

    def _snap(self, value):
        """网格吸附"""
        return (value // self.grid_size) * self.grid_size

    def _clear_selection(self):
        for item in self.items:
            item.selected = False
        for conv in self.conveyors:
            conv.selected = False
        self.selected = None

    def wheelEvent(self, event):
        """滚轮调整大小"""
        if self.selected and isinstance(self.selected, DraggableItem):
            delta = event.angleDelta().y()
            step = 5 if event.modifiers() & Qt.ShiftModifier else 2
            if delta > 0:
                self.selected.width = min(200, self.selected.width + step)
                self.selected.height = min(200, self.selected.height + step)
            else:
                self.selected.width = max(10, self.selected.width - step)
                self.selected.height = max(10, self.selected.height - step)
            self.update()

    def keyPressEvent(self, event):
        """键盘快捷键"""
        if event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace:
            if self.selected:
                if isinstance(self.selected, ConveyorItem):
                    self.conveyors.remove(self.selected)
                else:
                    self.items.remove(self.selected)
                self.selected = None
                self.update()

        elif event.key() == Qt.Key_Escape:
            self._clear_selection()
            self.update()

        elif event.key() == Qt.Key_S and event.modifiers() & Qt.ControlModifier:
            self.parent().parent().save_layout()

        elif event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            step = 10 if event.modifiers() & Qt.ShiftModifier else 1
            if self.selected:
                if isinstance(self.selected, ConveyorItem):
                    if event.key() == Qt.Key_Left:
                        self.selected.x1 -= step
                    elif event.key() == Qt.Key_Right:
                        self.selected.x1 += step
                    elif event.key() == Qt.Key_Up:
                        self.selected.y1 -= step
                    elif event.key() == Qt.Key_Down:
                        self.selected.y1 += step
                else:
                    if event.key() == Qt.Key_Left:
                        self.selected.x -= step
                    elif event.key() == Qt.Key_Right:
                        self.selected.x += step
                    elif event.key() == Qt.Key_Up:
                        self.selected.y -= step
                    elif event.key() == Qt.Key_Down:
                        self.selected.y += step
                self.update()


class LayoutEditorWindow(QWidget):
    """布局编辑器主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("布局编辑器 - 调整位置和大小")
        self.setMinimumSize(1000, 700)

        self.canvas = LayoutCanvas()
        self.canvas.selection_changed.connect(self._on_selection_changed)

        self._init_ui()
        self._create_menu_bar()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        # 工具栏
        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)

        # 保存按钮
        self.save_btn = QPushButton("保存布局")
        self.save_btn.clicked.connect(self.save_layout)
        toolbar_layout.addWidget(self.save_btn)

        # 重新加载按钮
        self.reload_btn = QPushButton("重新加载")
        self.reload_btn.clicked.connect(self._on_reload)
        toolbar_layout.addWidget(self.reload_btn)

        toolbar_layout.addSpacing(20)

        # 网格设置
        toolbar_layout.addWidget(QLabel("网格:"))
        self.grid_spin = QSpinBox()
        self.grid_spin.setRange(5, 50)
        self.grid_spin.setValue(10)
        self.grid_spin.valueChanged.connect(self._on_grid_changed)
        toolbar_layout.addWidget(self.grid_spin)

        # 吸附开关
        self.snap_check = QCheckBox("吸附网格")
        self.snap_check.setChecked(True)
        self.snap_check.toggled.connect(self._on_snap_changed)
        toolbar_layout.addWidget(self.snap_check)

        # 显示标签
        self.label_check = QCheckBox("显示标签")
        self.label_check.setChecked(True)
        self.label_check.toggled.connect(self._on_labels_changed)
        toolbar_layout.addWidget(self.label_check)

        toolbar_layout.addStretch()

        main_layout.addWidget(toolbar)

        # 画布区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setWidget(self.canvas)
        main_layout.addWidget(scroll, 1)

        # 属性面板
        self.prop_panel = QGroupBox("属性")
        self.prop_layout = QVBoxLayout()
        self.prop_text = QTextEdit()
        self.prop_text.setReadOnly(True)
        self.prop_text.setMaximumHeight(120)
        self.prop_layout.addWidget(self.prop_text)
        self.prop_panel.setLayout(self.prop_layout)
        main_layout.addWidget(self.prop_panel)

        # 状态栏
        self.status_bar = QLabel("就绪")
        main_layout.addWidget(self.status_bar)

    def _create_menu_bar(self):
        pass

    def save_layout(self):
        """保存布局到pos.py"""
        try:
            data = self._collect_layout_data()
            self._write_pos_file(data)
            QMessageBox.information(self, "保存成功", "布局已保存到 pos.py")
            self.status_bar.setText("已保存")
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))
            import traceback
            traceback.print_exc()

    def _collect_layout_data(self):
        """收集所有布局数据"""
        data = {
            'BATCHING_STATION': None,
            'HIGH_SILO': None,
            'FEED_POINTS': {},
            'TRANSFER_HOPPERS': {},
            'CONVEYORS': {},
            'SENSORS': {},
        }

        for item in self.canvas.items:
            if item.type == 'batching_station':
                data['BATCHING_STATION'] = {
                    'x': int(item.x),
                    'y': int(item.y),
                    'width': int(item.width),
                    'height': int(item.height),
                }
            elif item.type == 'high_silo':
                data['HIGH_SILO'] = {
                    'x': int(item.x),
                    'y': int(item.y),
                    'width': int(item.width),
                    'height': int(item.height),
                }
            elif item.type == 'feed_point':
                data['FEED_POINTS'][item.id] = {
                    'x': int(item.x),
                    'y': int(item.y),
                    'name': item.name,
                }
            elif item.type == 'hopper':
                data['TRANSFER_HOPPERS'][item.id] = {
                    'x': int(item.x),
                    'y': int(item.y),
                    'width': int(item.width),
                    'height': int(item.height),
                }
            elif item.type == 'sensor':
                data['SENSORS'][item.id] = {
                    'x': int(item.x),
                    'y': int(item.y),
                }

        for conv in self.canvas.conveyors:
            data['CONVEYORS'][conv.id] = {
                'x1': int(conv.x1),
                'y1': int(conv.y1),
                'x2': int(conv.x2),
                'y2': int(conv.y2),
            }

        return data

    def _write_pos_file(self, data):
        """写入pos.py文件"""
        with open('pos.py', 'r', encoding='utf-8') as f:
            content = f.read()

        # 替换BATCHING_STATION部分
        if data['BATCHING_STATION']:
            content = self._replace_single_item(content, 'BATCHING_STATION', data['BATCHING_STATION'], self._format_batching_station)
        # 替换HIGH_SILO部分
        if data['HIGH_SILO']:
            content = self._replace_single_item(content, 'HIGH_SILO', data['HIGH_SILO'], self._format_high_silo)
        # 替换SENSORS部分
        content = self._replace_dict_section(content, 'SENSORS', data['SENSORS'], self._format_sensor)
        # 替换FEED_POINTS部分
        content = self._replace_dict_section(content, 'FEED_POINTS', data['FEED_POINTS'], self._format_feed_point)
        # 替换TRANSFER_HOPPERS部分
        content = self._replace_dict_section(content, 'TRANSFER_HOPPERS', data['TRANSFER_HOPPERS'], self._format_hopper)
        # 替换CONVEYORS部分
        content = self._replace_dict_section(content, 'CONVEYORS', data['CONVEYORS'], self._format_conveyor)

        with open('pos.py', 'w', encoding='utf-8') as f:
            f.write(content)

        # 重新加载
        import importlib
        importlib.reload(pos)

    def _replace_dict_section(self, content, dict_name, new_data, formatter):
        """替换字典中的数据"""
        import re

        # 找到字典的开始位置
        start_pattern = rf"(^{re.escape(dict_name)} = \{{\n)"
        start_match = re.search(start_pattern, content, re.MULTILINE)
        if not start_match:
            return content

        start_pos = start_match.end()

        # 从开始位置往后找匹配的结束括号
        brace_count = 1
        i = start_pos
        while i < len(content) and brace_count > 0:
            if content[i] == '{':
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
            i += 1

        if brace_count != 0:
            return content  # 未找到匹配的结束括号

        # 格式化新数据
        formatted = formatter(new_data)

        # 替换：保留开始 { 和结束 }
        new_content = content[:start_pos] + formatted + content[i-1:]
        return new_content

    def _replace_single_item(self, content, item_name, item_data, formatter):
        """替换单个字典项（如BATCHING_STATION）"""
        import re

        # 匹配字典定义及其内容
        pattern = rf"(^{re.escape(item_name)} = \{{)(.*?)(\}})"
        match = re.search(pattern, content, re.MULTILINE | re.DOTALL)

        if not match:
            return content

        # 格式化新数据
        formatted = formatter(item_data)

        # 替换内容
        new_content = match.group(1) + '\n' + formatted + '    ' + match.group(3)
        return content[:match.start()] + new_content + content[match.end():]

    def _format_batching_station(self, data):
        return f"""    'name': '{pos.BATCHING_STATION.get('name', '高位配料站')}',
    'x': {data['x']},
    'y': {data['y']},
    'width': {data['width']},
    'height': {data['height']},
    'columns': {pos.BATCHING_STATION.get('columns', 4)},
    'rows': {pos.BATCHING_STATION.get('rows', 7)},
    'col_names': {pos.BATCHING_STATION.get('col_names', ['P1', 'P2', 'P3', 'P4'])},
    'row_spacing': {pos.BATCHING_STATION.get('row_spacing', 5.4)},
"""

    def _format_high_silo(self, data):
        return f"""    'name': '{pos.HIGH_SILO.get('name', '高位储料仓')}',
    'x': {data['x']},
    'y': {data['y']},
    'width': {data['width']},
    'height': {data['height']},
    'rows': {pos.HIGH_SILO.get('rows', 2)},
    'columns': {pos.HIGH_SILO.get('columns', 6)},
"""

    def _format_sensor(self, data):
        lines = []
        for sid, sdata in data.items():
            existing = pos.SENSORS.get(sid, {})
            name = existing.get('name', sid)
            conveyor = existing.get('conveyor', '')
            dist = existing.get('distance_from_start', 0.5)
            lines.append(f"    \"{sid}\": {{\"name\": \"{name}\", \"x\": {sdata['x']}, \"y\": {sdata['y']}, \"conveyor\": \"{conveyor}\", \"distance_from_start\": {dist}}}")
        return ',\n'.join(lines) + ',\n'

    def _format_feed_point(self, data):
        lines = []
        for fid, fdata in data.items():
            name = fdata.get('name', f"上料点{fid}")
            lines.append(f"    \"{fid}\": {{\"name\": \"{name}\", \"x\": {fdata['x']}, \"y\": {fdata['y']}, \"output\": None, \"feed_point\": None}}")
        return ',\n'.join(lines) + ',\n'

    def _format_hopper(self, data):
        lines = []
        for hid, hdata in data.items():
            existing = pos.TRANSFER_HOPPERS.get(hid, {})
            name = existing.get('name', f'中转斗{hid}')
            inp = existing.get('input', [])
            out = existing.get('output', None)
            if out is not None and not isinstance(out, str) and not isinstance(out, list):
                out = f'"{out}"'
            elif isinstance(out, str):
                out = f'"{out}"'
            elif isinstance(out, list):
                out = str(out)
            lines.append(f"    \"{hid}\": {{\"name\": \"{name}\", \"x\": {hdata['x']}, \"y\": {hdata['y']}, \"width\": {hdata['width']}, \"height\": {hdata['height']}, \"input\": {inp}, \"output\": {out}}}")
        return ',\n'.join(lines) + ',\n'

    def _format_conveyor(self, data):
        lines = []
        for cid, cdata in data.items():
            existing = pos.CONVEYORS.get(cid, {})
            name = existing.get('name', cid)
            length = existing.get('length', 20)
            ctype = existing.get('type', 'NORMAL')
            lines.append(f"    \"{cid}\": {{\"x1\": {cdata['x1']}, \"y1\": {cdata['y1']}, \"x2\": {cdata['x2']}, \"y2\": {cdata['y2']}, \"name\": \"{name}\", \"length\": {length}, \"type\": \"{ctype}\"}}")
        return ',\n'.join(lines) + ',\n'

    def _on_reload(self):
        self.canvas.load_from_pos()
        self.status_bar.setText("已重新加载")

    def _on_grid_changed(self, value):
        self.canvas.grid_size = value
        self.canvas.update()

    def _on_snap_changed(self, checked):
        self.canvas.snap_to_grid = checked

    def _on_labels_changed(self, checked):
        self.canvas.show_labels = checked
        self.canvas.update()

    def _on_selection_changed(self, info):
        self.status_bar.setText(f"选中: {info}")
        self._update_property_panel()

    def _update_property_panel(self):
        sel = self.canvas.selected
        if sel is None:
            self.prop_text.setPlainText("未选中任何元素")
            return

        if isinstance(sel, ConveyorItem):
            text = f"""皮带: {sel.name}
起点: ({int(sel.x1)}, {int(sel.y1)})
终点: ({int(sel.x2)}, {int(sel.y2)})

拖动端点可调整皮带位置
Delete键删除"""
        elif isinstance(sel, DraggableItem):
            text = f"""名称: {sel.name}
类型: {sel.type}
位置: ({int(sel.x)}, {int(sel.y)})
大小: {int(sel.width)} x {int(sel.height)}

拖动移动位置
滚轮调整大小
Delete键删除"""
        else:
            text = "未知类型"

        self.prop_text.setPlainText(text)


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    window = LayoutEditorWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
