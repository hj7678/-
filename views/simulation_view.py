"""
仿真动画视图 - Simulation Animation View
根据示意图布局绘制完整的搅拌站上料系统

包含:
- 5个上料点
- 19条皮带 (E1, E2, E4, E5, E6, E7, E8, E9, E10, D1-D9, D13)
- 18个接近开关传感器
- 7个中转斗
- 高位配料站 (28个小仓)
- 高位储料仓
"""

import math
from typing import Dict, List, Optional
from PyQt5.QtWidgets import QWidget, QSizePolicy, QMessageBox
from PyQt5.QtCore import Qt, QTimer, QPointF, QPoint, QRectF, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QPolygon, QRadialGradient, QLinearGradient
import config


class SimulationView(QWidget):
    """仿真动画视图组件"""

    # 信号：点击选择上料路线
    bin_clicked = pyqtSignal(str)  # bin_id

    def __init__(self, parent=None):
        super().__init__(parent)

        # 尺寸设置
        self.setMinimumSize(config.SIMULATION_WIDTH, config.SIMULATION_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 引用仿真系统
        self.conveyors: Dict = {}
        self.sensors: Dict = {}
        self.hoppers: Dict = {}
        self.feed_points: Dict = {}
        self.materials: List = []
        self.active_routes: List = []

        # 分料小车状态
        self.cart_positions: Dict[str, dict] = {}  # route_id -> {target_bin, current_x, target_x, moving}

        # 高位储料仓小仓状态（S1-S12）
        self.silo_compartments: Dict = {}
        for i in range(1, 13):
            bin_id = f'S{i}'
            capacity = config.HIGH_SILO_BIN_CAPACITY  # 110吨
            self.silo_compartments[bin_id] = {
                'capacity': capacity,
                'current_level': capacity * 0.85,  # 初始85%（93.5吨）
                'is_target': False
            }

        # 动画时间
        self.animation_time = 0
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._advance_animation)
        self.animation_timer.start(500)  # 每500ms更新（支持闪烁动画）

        # 颜色
        self.bg_color = QColor(config.COLORS['background'])

        # 脏标记：只在数据变化时重绘
        self._needs_repaint = False

    def set_simulator(self, simulator):
        """设置仿真系统引用"""
        self.simulator = simulator
        self.controller = simulator  # 保存controller引用用于小车4控制
        self.conveyors = simulator.conveyors
        self.sensors = simulator.sensors
        self.hoppers = simulator.hoppers
        self.small_bins = simulator.small_bins
        self.route_to_bin = simulator.route_to_bin
        self.feed_points = simulator.feed_points
        self.materials = simulator.materials
        self.active_routes = simulator.active_routes

        # 仿真启动时初始化所有分料小车在各自皮带的默认位置
        self._init_all_carts()

    def _advance_animation(self):
        """推进动画"""
        self.animation_time += 500
        delta_time = 0.5
        self._update_cart_positions(delta_time)
        self._update_cart4_position()
        if self._needs_repaint:
            self._needs_repaint = False
            self.update()

    def mark_needs_repaint(self):
        """标记需要重绘"""
        self._needs_repaint = True

    def mousePressEvent(self, event):
        """处理鼠标点击事件"""
        if event.button() == Qt.LeftButton:
            pos = event.pos()
            bin_id = self._hit_test_bin(pos)
            if bin_id:
                self.bin_clicked.emit(bin_id)
        super().mousePressEvent(event)

    def _hit_test_bin(self, pos: QPoint) -> Optional[str]:
        """检测点击位置是否在某个小仓上

        Args:
            pos: 点击位置（像素坐标）

        Returns:
            小仓ID (如 'P1-1', 'S5')，如果不在任何小仓上则返回None
        """
        x, y = pos.x(), pos.y()

        # 首先检查高位配料站的小仓 (P1-1 到 P4-7)
        bin_id = self._hit_test_batching_bin(x, y)
        if bin_id:
            return bin_id

        # 然后检查高位储料仓的小仓 (S1-S12)
        bin_id = self._hit_test_silo_bin(x, y)
        if bin_id:
            return bin_id

        return None

    def _hit_test_batching_bin(self, x: float, y: float) -> Optional[str]:
        """检测点击是否在高位配料站的小仓上

        Args:
            x, y: 点击位置（像素坐标）

        Returns:
            小仓ID (如 'P1-1')，如果不在任何小仓上则返回None
        """
        bs = config.BATCHING_STATION
        bs_x, bs_y = bs['position']
        w, h = bs['width'], bs['height']

        # 检查是否在配料站区域内
        if not (bs_x <= x <= bs_x + w and bs_y <= y <= bs_y + h):
            return None

        # 计算每个小仓的尺寸
        col_count = bs['columns']  # 4列
        row_count = bs['rows']     # 7行
        comp_w = (w - 20) / col_count
        comp_h = (h - 30) / row_count

        # 计算点击位置对应的小仓
        rel_x = x - bs_x - 10
        rel_y = y - bs_y - 20

        if rel_x < 0 or rel_y < 0:
            return None

        col = int(rel_x / comp_w)
        row = int(rel_y / comp_h)

        if col < 0 or col >= col_count or row < 0 or row >= row_count:
            return None

        # 返回小仓ID
        return f"{bs['column_names'][col]}-{row + 1}"

    def _hit_test_silo_bin(self, x: float, y: float) -> Optional[str]:
        """检测点击是否在高位储料仓的小仓上

        Args:
            x, y: 点击位置（像素坐标）

        Returns:
            小仓ID (如 'S1'),如果不在任何小仓上则返回None
        """
        sil = config.HIGH_SILO
        sil_x, sil_y = sil['position']
        sil_width = sil['width']
        sil_height = sil['height']

        # 检查是否在储料仓区域内
        if not (sil_x <= x <= sil_x + sil_width and sil_y <= y <= sil_y + sil_height):
            return None

        # 计算每个小仓的尺寸
        col_count = sil['columns']  # 6列
        row_count = sil['rows']     # 2行
        comp_w = (sil_width - 10) / col_count
        comp_h = (sil_height - 30) / row_count

        # 计算点击位置对应的小仓
        rel_x = x - sil_x - 5
        rel_y = y - sil_y - 18

        if rel_x < 0 or rel_y < 0:
            return None

        col = int(rel_x / comp_w)
        row = int(rel_y / comp_h)

        if col < 0 or col >= col_count or row < 0 or row >= row_count:
            return None

        # 计算小仓编号 S1-S12
        # 第一行: S1-S6 (col 0-5)
        # 第二行: S7-S12 (col 0-5)
        silo_num = row * 6 + col + 1

        if silo_num < 1 or silo_num > 12:
            return None

        return f"S{silo_num}"

    def _init_all_carts(self):
        """仿真启动时初始化所有分料小车在各自皮带的默认位置

        D7皮带上：服务于路线①②③，默认停在第1行小仓 P1-1（行1）
        D8皮带上：服务于路线⑦⑨，默认停在第1行小仓 P2-1（行1）
        D9皮带上：服务于路线④⑥⑧，默认停在第1行小仓 P4-1（行1）

        这些小车在仿真启动时就在画布上显示，不依赖路线是否激活。
        标记 _persistent=True，防止被 _update_cart_positions 的清理逻辑误删。
        """
        conveyor_bins = {
            'D7': 'P1-1',  # 路线①②③
            'D8': 'P2-1',  # 路线⑥⑧
            'D9': 'P4-1',  # 路线④⑦
        }
        conveyor_routes = {
            'D7': '_persistent_D7',
            'D8': '_persistent_D8',
            'D9': '_persistent_D9',
        }

        for conveyor_id, default_bin in conveyor_bins.items():
            route_id = conveyor_routes[conveyor_id]
            pos = self._get_cart_target_on_conveyor(conveyor_id, default_bin)
            self.cart_positions[route_id] = {
                'target_bin': default_bin,
                'conveyor_id': conveyor_id,
                'current_x': pos[0],
                'current_y': pos[1],
                'target_x': pos[0],
                'target_y': pos[1],
                'moving': False,
                '_persistent': True,
            }

    def _update_cart_positions(self, delta_seconds: float):
        """更新分料小车位置 - 每秒移动固定像素

        移动规则：
        - 皮带上相邻小仓间距为24像素
        - 小车移动一格需要18秒
        - 每秒移动 24/18 = 1.333 像素
        """
        if not hasattr(self, 'route_to_bin'):
            return

        PIXELS_PER_SECOND = 24.0 / 18.0  # 1.333 px/s

        # 获取当前目标小仓
        new_targets = set(self.route_to_bin.items())

        # 停止不存在的路线的小车，但保存给同cart_id的新路线继承
        orphan_carts = {}  # cart_id → saved cart data
        for route_id in list(getattr(self, 'cart_positions', {}).keys()):
            if route_id not in self.route_to_bin:
                cart = self.cart_positions.get(route_id, {})
                if cart.get('_persistent'):
                    continue
                # 保存 cart 数据供新路线继承
                cart_id = self._get_cart_for_route(route_id)
                if cart_id and cart_id not in orphan_carts:
                    orphan_carts[cart_id] = dict(cart)
                del self.cart_positions[route_id]
                if hasattr(self, '_cart_anim_state') and route_id in self._cart_anim_state:
                    del self._cart_anim_state[route_id]

        # 初始化动画状态跟踪
        if not hasattr(self, '_cart_anim_state'):
            self._cart_anim_state = {}

        # 为新路线初始化小车 / 更新已有路线
        # 注意：route5使用Cart4（水平移动在D6皮带上），由_draw_cart4单独处理
        for route_id, target_bin in new_targets:
            if route_id == 'route5':
                continue
            conveyor_id = self._get_conveyor_for_route(route_id)
            target_pos = self._get_cart_target_on_conveyor(conveyor_id, target_bin)
            target_grid = self._get_bin_row(target_bin)

            if route_id not in self.cart_positions:
                # 新路线：优先继承同一 cart_id 孤儿小车的位置，避免视觉跳跃
                cart_id = self._get_cart_for_route(route_id)
                orphan = orphan_carts.get(cart_id) if cart_id else None
                current_row = 1
                if orphan:
                    current_row = self._get_bin_row(orphan.get('target_bin', '')) or 1
                elif hasattr(self, 'controller') and self.controller and cart_id:
                    current_row = self.controller.cart_positions.get(cart_id, 1)
                initial_bin = self._row_to_cart_pixel(conveyor_id, current_row)
                self.cart_positions[route_id] = {
                    'target_bin': target_bin,
                    'conveyor_id': conveyor_id,
                    'current_x': initial_bin[0],
                    'current_y': initial_bin[1],
                    'target_x': target_pos[0],
                    'target_y': target_pos[1],
                    'moving': True
                }
                self._cart_anim_state[route_id] = {
                    'elapsed': 0.0,
                    'from_x': initial_bin[0],
                    'from_y': initial_bin[1],
                    'to_x': target_pos[0],
                    'to_y': target_pos[1],
                }
            else:
                cart = self.cart_positions[route_id]
                # 路线激活时移除 _persistent 标记，使小车在 _draw_distribution_carts 中被绘制
                cart.pop('_persistent', None)
                if cart['target_bin'] != target_bin:
                    old_grid = self._get_bin_row(cart['target_bin'])
                    new_grid = self._get_bin_row(target_bin)
                    grid_distance = abs(new_grid - old_grid)
                    self._cart_anim_state[route_id] = {
                        'elapsed': 0.0,
                        'from_x': cart['current_x'],
                        'from_y': cart['current_y'],
                        'to_x': target_pos[0],
                        'to_y': target_pos[1],
                    }
                    cart['target_bin'] = target_bin
                    cart['target_x'] = target_pos[0]
                    cart['target_y'] = target_pos[1]
                elif route_id not in self._cart_anim_state:
                    self._cart_anim_state[route_id] = {
                        'elapsed': 0.0,
                        'from_x': cart['current_x'],
                        'from_y': cart['current_y'],
                        'to_x': target_pos[0],
                        'to_y': target_pos[1],
                    }

                # 更新 moving 状态
                ctx = None
                if hasattr(self, 'controller') and self.controller:
                    ctx = self.controller.route_state_manager.get_route_context(route_id)
                moving = ctx and ctx.cart_moving and ctx.state.value == 'moving_to_target'
                cart['moving'] = moving

                # 每秒移动1.333像素
                if route_id in self._cart_anim_state:
                    anim = self._cart_anim_state[route_id]
                    from_x, from_y = anim['from_x'], anim['from_y']
                    to_x, to_y = anim['to_x'], anim['to_y']
                    dx = to_x - from_x
                    dy = to_y - from_y
                    total_dist = math.sqrt(dx * dx + dy * dy)
                    if total_dist > 0:
                        move_pixels = PIXELS_PER_SECOND * delta_seconds
                        elapsed_dist = math.sqrt((cart['current_x'] - from_x) ** 2 + (cart['current_y'] - from_y) ** 2)
                        remaining_dist = total_dist - elapsed_dist
                        if remaining_dist > 0:
                            step = min(move_pixels, remaining_dist)
                            ratio = step / total_dist
                            cart['current_x'] += dx * ratio
                            cart['current_y'] += dy * ratio

    def _get_conveyor_for_route(self, route_id: str) -> str:
        """获取路线对应的皮带ID（8路线系统）"""
        if route_id in ('route1', 'route2', 'route3'):
            return 'D7'    # Cart1 → P1
        elif route_id in ('route4', 'route7'):
            return 'D9'    # Cart3 → P4
        elif route_id in ('route6', 'route8'):
            return 'D8'    # Cart2 → P2/P3
        elif route_id == 'route5':
            return 'D6'    # Cart4 → silo
        return 'D7'

    def _get_cart_for_route(self, route_id: str) -> str:
        """获取路线对应的小车ID"""
        if route_id in ('route1', 'route2', 'route3'):
            return 'Cart1'
        elif route_id in ('route4', 'route7'):
            return 'Cart3'
        elif route_id in ('route6', 'route8'):
            return 'Cart2'
        elif route_id == 'route5':
            return 'Cart4'
        return 'Cart1'

    def _get_bin_row(self, bin_id: str) -> int:
        """从 bin_id 提取行号（P1-3 -> 3）"""
        if '-' in bin_id:
            try:
                return int(bin_id.split('-')[1])
            except ValueError:
                return 1
        return 1

    def _row_to_cart_pixel(self, conveyor_id: str, row: int) -> tuple:
        """根据行号(1-7)和小仓列计算小车像素坐标"""
        col_name = self._get_conveyor_column(conveyor_id)
        bin_id = f"{col_name}-{row}"
        return self._get_cart_target_on_conveyor(conveyor_id, bin_id)

    def _get_conveyor_line_position(self, conveyor_id: str) -> tuple:
        """获取皮带的起点和终点坐标"""
        if conveyor_id not in self.conveyors:
            return (0, 0), (0, 0)

        conveyor = self.conveyors[conveyor_id]
        start = conveyor.start_pos
        end = conveyor.end_pos
        return start, end

    def _get_conveyor_column(self, conveyor_id: str) -> str:
        """获取皮带对应的小仓列名"""
        column_mapping = {
            'D7': 'P1',
            'D8': 'P2',
            'D9': 'P4',
        }
        return column_mapping.get(conveyor_id, 'P1')

    def _update_cart4_position(self):
        """从小车4控制器获取位置，平滑插值动画"""
        if not hasattr(self, 'controller') or not self.controller:
            return
        # 获取目标位置（控制器中的离散整数位置）
        target_pos = int(getattr(self.controller, 'cart4_position', 1))
        target_target = int(getattr(self.controller, 'cart4_target_position', 1))
        is_moving = getattr(self.controller, 'cart4_is_moving', False)

        # 计算D6皮带上的像素范围
        if 'D6' not in self.conveyors:
            return
        conv = self.conveyors['D6']
        x1, y1 = conv.start_pos
        x2, y2 = conv.end_pos
        belt_len = abs(x2 - x1)

        # 初始化动画状态
        if not hasattr(self, '_cart4_anim'):
            self._cart4_anim = {
                'display_pos': float(target_pos),
                'from_grid': target_pos,
                'to_grid': target_pos,
                'elapsed': 0.0,
                'total_time': 18.0,
            }
        anim = self._cart4_anim

        # 检测目标变化：控制器目标变了，启动新动画
        if is_moving and target_target != anim['to_grid']:
            anim['from_grid'] = anim['display_pos']
            anim['to_grid'] = float(target_target)
            anim['elapsed'] = 0.0
            anim['total_time'] = 18.0 * abs(anim['to_grid'] - anim['from_grid'])

        # 推进动画：线性插值
        if is_moving and abs(anim['display_pos'] - anim['to_grid']) > 0.01:
            anim['elapsed'] += 0.5  # 500ms步进
            if anim['elapsed'] >= anim['total_time']:
                anim['display_pos'] = anim['to_grid']
            else:
                t = anim['elapsed'] / anim['total_time']
                anim['display_pos'] = anim['from_grid'] + (anim['to_grid'] - anim['from_grid']) * t
        elif not is_moving:
            # 小车已到达，使用控制器精确位置
            anim['display_pos'] = float(target_pos)
            anim['from_grid'] = float(target_pos)
            anim['to_grid'] = float(target_pos)
            anim['elapsed'] = 0.0

        # 更新视图位置为平滑后的像素值
        self.cart4_position = anim['display_pos']

    def _get_cart_target_on_conveyor(self, conveyor_id: str, bin_id: str) -> tuple:
        """根据目标小仓计算小车在皮带上的目标位置"""
        if conveyor_id not in self.conveyors:
            return (0, 0)

        conveyor = self.conveyors[conveyor_id]
        end_x, end_y = conveyor.end_pos

        # 获取小仓的Y坐标
        _, bin_y = self._get_small_bin_position(bin_id)

        # 小车X与皮带对齐，Y与小仓对齐（同一水平线）
        cart_x = end_x
        cart_y = bin_y

        # print(f"Cart target: bin={bin_id}, conveyor_x={end_x}, bin_y={bin_y:.1f}")

        return (cart_x, cart_y)

    def paintEvent(self, event):
        """绘制事件"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 填充背景
        painter.fillRect(self.rect(), self.bg_color)

        # 绘制网格背景
        self._draw_grid_background(painter)

        # 绘制组件
        self._draw_legend(painter)           # 图例
        self._draw_feed_points(painter)    # 上料点
        self._draw_laser_sensors(painter)  # 激光测距仪

        # 高位储料仓上半部分（第1行小仓）
        self._draw_high_silo_top(painter)

        # 绘制高位储料仓出料箭头（路线⑧⑨）
        self._draw_silo_discharge_arrow(painter)

        # 皮带分层绘制
        # 普通皮带（D6/D7/D8/D9 以外）
        for conv_id, conveyor in self.conveyors.items():
            if conv_id not in ('D6', 'D7', 'D8', 'D9'):
                self._draw_single_conveyor(painter, conveyor)

        # 高位储料仓下半部分（第2行小仓和边框）
        self._draw_high_silo_bottom(painter)

        # D6 皮带（在储料仓上方）
        if 'D6' in self.conveyors:
            self._draw_single_conveyor(painter, self.conveyors['D6'])

        # 小车4（在D6皮带上水平移动）
        self._draw_cart4(painter)

        # 高位配料站（在D7/D8/D9皮带下方）
        self._draw_batching_station(painter)

        # D7, D8, D9 皮带（在配料站上方，仅次于小车）
        for conv_id in ('D7', 'D8', 'D9'):
            if conv_id in self.conveyors:
                self._draw_single_conveyor(painter, self.conveyors[conv_id])

        self._draw_hoppers(painter)        # 中转斗（在皮带之上）
        self._draw_sensors(painter)         # 接近开关
        self._draw_materials(painter)       # 物料

        # 分料小车（在最顶层）
        self._draw_distribution_carts(painter)

    def _draw_grid_background(self, painter: QPainter):
        """绘制网格背景"""
        painter.setPen(QPen(QColor('#21262d'), 1))
        grid_size = 50
        width = self.width()
        height = self.height()

        for x in range(0, width, grid_size):
            painter.drawLine(x, 0, x, height)
        for y in range(0, height, grid_size):
            painter.drawLine(0, y, width, y)

    def _draw_legend(self, painter: QPainter):
        """绘制图例"""
        # 放在左上角
        legend_x = 15
        legend_y = 15

        # 背景
        painter.setBrush(QBrush(QColor(26, 26, 46, 230)))
        painter.setPen(QPen(QColor('#30363d'), 1))
        painter.drawRoundedRect(legend_x, legend_y, 140, 95, 6, 6)

        # 标题
        painter.setPen(QPen(QColor('#E6EDF3')))
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(legend_x + 10, legend_y + 18, "骨料类型")

        # 石粉 - 灰白色粉末堆
        painter.save()
        painter.setPen(Qt.NoPen)
        base_color = QColor('#B8C4CE')
        # 绘制小堆
        for i in range(5):
            angle_offset = (i / 5) * 2 * math.pi
            spread = 4 - i
            px = legend_x + 20 + int(spread * 1.2 * math.cos(angle_offset))
            py = legend_y + 40 + int(spread * 0.8 * math.sin(angle_offset) * 0.6)
            size = 4 - i * 0.5
            color = QColor(base_color)
            color.setRed(int(color.red() * (0.7 + i * 0.06)))
            color.setGreen(int(color.green() * (0.7 + i * 0.06)))
            color.setBlue(int(color.blue() * (0.7 + i * 0.06)))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(int(px - size/2), int(py - size/2), int(size), int(size))
        painter.restore()

        painter.setPen(QPen(QColor('#8B949E')))
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(legend_x + 50, legend_y + 42, "石粉")

        # 10mm碎石 - 灰黄色颗粒堆
        painter.save()
        painter.setPen(Qt.NoPen)
        base_color = QColor('#C4A35A')
        for i in range(4):
            angle_offset = (i / 4) * 2 * math.pi + 0.5
            spread = 3.5 - i * 0.5
            px = legend_x + 20 + int(spread * 1.5 * math.cos(angle_offset))
            py = legend_y + 62 + int(spread * 0.8 * math.sin(angle_offset) * 0.6)
            size = 5 - i * 0.8
            color = QColor(base_color)
            color.setRed(int(color.red() * (0.7 + i * 0.1)))
            color.setGreen(int(color.green() * (0.7 + i * 0.1)))
            color.setBlue(int(color.blue() * (0.7 + i * 0.1)))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(int(px - size/2), int(py - size/2), int(size), int(size))
        painter.restore()

        painter.setPen(QPen(QColor('#8B949E')))
        painter.drawText(legend_x + 50, legend_y + 64, "10mm碎石")

        # 20mm碎石 - 深灰蓝色大颗粒堆
        painter.save()
        painter.setPen(Qt.NoPen)
        base_color = QColor('#4A6572')
        for i in range(3):
            angle_offset = (i / 3) * 2 * math.pi + 1.0
            spread = 3 - i * 0.6
            px = legend_x + 20 + int(spread * 1.8 * math.cos(angle_offset))
            py = legend_y + 84 + int(spread * 0.8 * math.sin(angle_offset) * 0.6)
            size = 6 - i * 1.2
            color = QColor(base_color)
            color.setRed(int(color.red() * (0.7 + i * 0.15)))
            color.setGreen(int(color.green() * (0.7 + i * 0.15)))
            color.setBlue(int(color.blue() * (0.7 + i * 0.15)))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(int(px - size/2), int(py - size/2), int(size), int(size))
        painter.restore()

        painter.setPen(QPen(QColor('#8B949E')))
        painter.drawText(legend_x + 50, legend_y + 86, "20mm碎石")

    def _draw_title(self, painter: QPainter):
        pass  # 标题已移除

    def _draw_feed_points(self, painter: QPainter):
        """绘制所有上料点"""
        for fp_id, fp_config in config.FEED_POINTS.items():
            self._draw_single_feed_point(painter, fp_config)

    def _draw_single_feed_point(self, painter: QPainter, feed_point: dict):
        """绘制单个上料点"""
        x, y = feed_point['position']
        name = feed_point['name']
        is_active = self._is_feed_point_active(feed_point)

        # 绘制料仓形状
        color = QColor(config.COLORS['feed_point']) if is_active else QColor('#2C3E50')
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(QColor('#1A252F'), 2))

        w, h = 40, 30
        # 梯形料仓
        path = QPainterPath()
        path.moveTo(int(x - w/2 + 5), int(y - h/2))
        path.lineTo(int(x + w/2 - 5), int(y - h/2))
        path.lineTo(int(x + w/2), int(y + h/2))
        path.lineTo(int(x - w/2), int(y + h/2))
        path.closeSubpath()
        painter.drawPath(path)

        # 绘制标签
        painter.setPen(QPen(QColor(config.COLORS['text'])))
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)

        # 名称标签绘制在组件正上方
        short_name = name.replace('上料点', '点').replace('中转斗', '斗')
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(short_name)
        painter.drawText(int(x - tw/2), int(y - h/2 - 6), short_name)

    def _draw_laser_sensors(self, painter: QPainter):
        """绘制所有激光测距仪传感器"""
        for laser_id, laser_config in config.LASER_SENSORS.items():
            self._draw_single_laser_sensor(painter, laser_id, laser_config)

    def _draw_single_laser_sensor(self, painter: QPainter, laser_id: str, laser_config: dict):
        """绘制单个激光测距仪传感器"""
        x, y = laser_config['position']

        # 获取激光传感器状态（有料=True，无料=False）
        has_material = False
        if hasattr(self, 'simulator') and self.simulator:
            has_material = self.simulator.get_laser_sensor_state(laser_id)

        # 传感器颜色：有料=绿色，无料=红色
        if has_material:
            main_color = QColor('#2ECC71')  # 绿色 - 有料
            glow_color = QColor('#2ECC71')
        else:
            main_color = QColor('#E74C3C')  # 红色 - 无料
            glow_color = QColor('#E74C3C')

        glow_color.setAlpha(80)

        # 绘制发光效果
        glow_radius = 12
        painter.setBrush(QBrush(glow_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(int(x - glow_radius), int(y - glow_radius), glow_radius * 2, glow_radius * 2)

        # 绘制传感器主体（矩形激光器形状）
        painter.setBrush(QBrush(main_color))
        painter.setPen(QPen(QColor('#1A252F'), 2))

        w, h = 20, 14
        painter.drawRect(int(x - w/2), int(y - h/2), w, h)

        # 绘制激光发射点（中心小圆）
        center_color = QColor('#FFFFFF') if has_material else QColor('#30363d')
        painter.setBrush(QBrush(center_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(int(x - 3), int(y - 3), 6, 6)

        # 绘制激光传感器ID标签
        painter.setPen(QPen(QColor(config.COLORS['text_secondary'])))
        font = QFont()
        font.setPointSize(7)
        painter.setFont(font)
        name = laser_config.get('name', laser_id)
        painter.drawText(int(x + 4), int(y - 6), name)

    def _is_feed_point_active(self, feed_point: dict) -> bool:
        """检查上料点是否活跃"""
        conv_id = feed_point.get('output_conveyor')
        if conv_id and conv_id in self.conveyors:
            return self.conveyors[conv_id].is_running
        return False

    def _draw_conveyors(self, painter: QPainter):
        """绘制所有皮带"""
        for conv_id, conveyor in self.conveyors.items():
            self._draw_single_conveyor(painter, conveyor)

    def _draw_single_conveyor(self, painter: QPainter, conveyor):
        """绘制单条皮带"""
        conv_id = conveyor.id

        # 检查皮带是否在运行路线上
        is_on_route = self._is_conveyor_on_active_route(conv_id)

        # 根据状态设置颜色
        if is_on_route and conveyor.is_running:
            main_color = QColor(config.COLORS['conveyor_running'])
            border_color = QColor('#00AA00')
        elif conveyor.is_running:
            main_color = QColor(config.COLORS['conveyor_running'])
            border_color = QColor('#00AA00')
        else:
            main_color = QColor(config.COLORS['conveyor_stopped'])
            border_color = QColor('#30363d')

        # 绘制皮带主体（宽线）
        painter.setPen(QPen(border_color, 16))
        painter.drawLine(int(conveyor.start_pos[0]), int(conveyor.start_pos[1]), int(conveyor.end_pos[0]), int(conveyor.end_pos[1]))

        # 绘制皮带中心线
        painter.setPen(QPen(main_color, 8))
        painter.drawLine(int(conveyor.start_pos[0]), int(conveyor.start_pos[1]), int(conveyor.end_pos[0]), int(conveyor.end_pos[1]))

        # 绘制滚筒
        self._draw_rollers(painter, conveyor)

        # 绘制皮带编号
        self._draw_conveyor_label(painter, conveyor)

        # 绘制移动箭头（如果皮带在运行）
        if conveyor.is_running:
            self._draw_conveyor_arrows(painter, conveyor)

    def _is_conveyor_on_active_route(self, conv_id: str) -> bool:
        """检查皮带是否在活跃路线上"""
        if not hasattr(self, 'simulator') or not self.simulator:
            return False
        return self.simulator.is_conveyor_on_route(conv_id)

    def _draw_rollers(self, painter: QPainter, conveyor):
        """绘制滚筒"""
        roller_color = QColor('#6E7681')
        painter.setBrush(QBrush(roller_color))
        painter.setPen(QPen(QColor('#484F58'), 2))

        radius = 10
        # 头部滚筒
        painter.drawEllipse( int(conveyor.start_pos[0] - radius), int(conveyor.start_pos[1] - radius), radius * 2, radius * 2 )
        painter.drawEllipse( int(conveyor.end_pos[0] - radius), int(conveyor.end_pos[1] - radius), radius * 2, radius * 2 )
    def _draw_conveyor_label(self, painter: QPainter, conveyor):
        """绘制皮带标签"""
        painter.setPen(QPen(QColor(config.COLORS['text_secondary'])))
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)

        center_x = (conveyor.start_pos[0] + conveyor.end_pos[0]) / 2
        center_y = (conveyor.start_pos[1] + conveyor.end_pos[1]) / 2

        name = conveyor.name
        # 根据皮带方向调整标签位置
        dx = conveyor.end_pos[0] - conveyor.start_pos[0]
        dy = conveyor.end_pos[1] - conveyor.start_pos[1]

        if abs(dx) > abs(dy):  # 水平皮带
            label_x = int(center_x - 10)
            label_y = int(conveyor.start_pos[1] + 20)
        else:  # 垂直皮带
            label_x = int(conveyor.start_pos[0] + 15)
            label_y = int(center_y)

        # 特定皮带标签微调
        if conveyor.id == 'D7':
            label_y -= 30  # 上移
        elif conveyor.id == 'D8':
            label_y -= 30  # 上移
        elif conveyor.id == 'D4':
            label_x -= 40  # 左移

        painter.drawText(label_x, label_y, name)

    def _draw_conveyor_arrows(self, painter: QPainter, conveyor):
        """绘制皮带上的移动箭头"""
        offset = int(self.animation_time / 20) % 30
        arrow_color = QColor('#FFFFFF')
        arrow_color.setAlpha(150)
        painter.setPen(QPen(arrow_color, 2))

        start_x = conveyor.start_pos[0]
        start_y = conveyor.start_pos[1]
        end_x = conveyor.end_pos[0]
        end_y = conveyor.end_pos[1]

        dx = end_x - start_x
        dy = end_y - start_y
        length = math.sqrt(dx*dx + dy*dy)

        if length == 0:
            return

        # 特殊处理D6皮带（路线⑤）：箭头只显示到小车4当前位置
        effective_end_x = end_x
        effective_end_y = end_y
        effective_length = length
        if conveyor.id == 'D6' and hasattr(self, 'controller') and self.controller:
            # 计算小车4当前位置对应的像素距离
            cart4_pos = self.controller.cart4_position
            cart4_is_moving = self.controller.cart4_is_moving

            # 路线⑤激活时，箭头显示到小车4当前位置
            if 'route5' in self.active_routes:
                # 计算小车4当前位置的比例
                cart4_ratio = cart4_pos / 6.0
                effective_end_x = start_x + dx * cart4_ratio
                effective_end_y = start_y + dy * cart4_ratio
                effective_length = length * cart4_ratio

        # 单位方向向量
        ux = dx / length
        uy = dy / length

        # 绘制几个箭头
        for i in range(3):
            base_t = ((offset + i * 50) % int(effective_length)) / effective_length if effective_length > 0 else 0
            arrow_x = start_x + dx * base_t
            arrow_y = start_y + dy * base_t

            if 0.1 < base_t < 0.9:
                # 绘制小箭头
                arrow_size = 6
                if abs(dx) > abs(dy):  # 水平
                    painter.drawLine(int(arrow_x), int(arrow_y), int(arrow_x + 8), int(arrow_y))
                    painter.drawLine(int(arrow_x + 5), int(arrow_y - 3), int(arrow_x + 8), int(arrow_y))
                    painter.drawLine(int(arrow_x + 5), int(arrow_y + 3), int(arrow_x + 8), int(arrow_y))
                else:  # 垂直
                    direction = -1 if dy < 0 else 1  # 向上为负
                    painter.drawLine(int(arrow_x), int(arrow_y), int(arrow_x), int(arrow_y + 8 * direction))
                    painter.drawLine(int(arrow_x - 3), int(arrow_y + 5 * direction), int(arrow_x), int(arrow_y + 8 * direction))
                    painter.drawLine(int(arrow_x + 3), int(arrow_y + 5 * direction), int(arrow_x), int(arrow_y + 8 * direction))

    def _draw_hoppers(self, painter: QPainter):
        """绘制所有中转斗"""
        for hp_id, hp_config in config.TRANSFER_HOPPERS.items():
            self._draw_single_hopper(painter, hp_config, hp_id)

    def _draw_single_hopper(self, painter: QPainter, hopper: dict, hopper_id: str):
        """绘制单个中转斗（工业写实风格 - 更精细）"""
        x, y = hopper['position']
        w, h = hopper['width'], hopper['height']
        name = hopper['name']

        # 检查中转斗是否活跃
        is_active = self._is_hopper_active(hopper_id)

        # 获取物料填充等级
        fill_level = 0.0
        if hasattr(self, 'simulator') and self.simulator:
            hopper_obj = self.simulator.hoppers.get(hopper_id)
            if hopper_obj:
                fill_level = hopper_obj.level_percent

        # ========== 基础设置 ==========
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # ========== 1. 外阴影（多层投影更真实） ==========
        # 主阴影
        for i in range(3):
            shadow_alpha = 40 - i * 10
            shadow_offset = 5 + i * 2
            painter.setPen(Qt.NoPen)
            shadow_color = QColor(0, 0, 0, shadow_alpha)
            painter.setBrush(QBrush(shadow_color))
            shadow_rect = QPainterPath()
            shadow_rect.addRoundedRect(int(x + shadow_offset), int(y + shadow_offset + i), int(w), int(h + 2), 8, 8)
            painter.drawPath(shadow_rect)

        # ========== 2. 斗体基础结构（3D效果） ==========
        # 确定主色调 - 金属灰蓝色
        metal_base = QColor('#4A5568') if not is_active else QColor('#2D5A6B')
        metal_light = QColor('#718096') if not is_active else QColor('#4299A5')
        metal_dark = QColor('#2D3748') if not is_active else QColor('#1A365D')

        # 绘制斗体主体渐变
        body_gradient = QLinearGradient(int(x), int(y), int(x + w), int(y + h))
        body_gradient.setColorAt(0, metal_light)
        body_gradient.setColorAt(0.3, metal_base)
        body_gradient.setColorAt(0.7, metal_base)
        body_gradient.setColorAt(1, metal_dark)

        painter.setBrush(QBrush(body_gradient))
        painter.setPen(Qt.NoPen)

        # 梯形斗体
        body_path = QPainterPath()
        body_path.moveTo(int(x + 12), int(y))
        body_path.lineTo(int(x + w - 12), int(y))
        body_path.lineTo(int(x + w), int(y + h))
        body_path.lineTo(int(x), int(y + h))
        body_path.closeSubpath()
        painter.drawPath(body_path)

        # ========== 3. 内部渐变（增加深度感） ==========
        inner_gradient = QRadialGradient(int(x + w/2), int(y + h * 0.4), max(w, h) * 0.7)
        inner_gradient.setColorAt(0, QColor(255, 255, 255, 15))
        inner_gradient.setColorAt(0.5, QColor(0, 0, 0, 0))
        inner_gradient.setColorAt(1, QColor(0, 0, 0, 40))

        painter.setBrush(QBrush(inner_gradient))
        painter.setPen(Qt.NoPen)
        painter.drawPath(body_path)

        # ========== 4. 物料填充效果（更精细） ==========
        if fill_level > 0:
            # 物料基础颜色
            material_base = QColor('#6B4423') if is_active else QColor('#4A3728')
            material_light = QColor('#8B6914') if is_active else QColor('#6B5344')
            material_dark = QColor('#3D2817')

            # 物料渐变
            material_gradient = QLinearGradient(int(x), int(y + h - h * fill_level/100), int(x), int(y + h))
            material_gradient.setColorAt(0, material_light)
            material_gradient.setColorAt(0.3, material_base)
            material_gradient.setColorAt(1, material_dark)

            painter.setBrush(QBrush(material_gradient))

            # 计算物料区域
            material_h = h * min(fill_level / 100, 1.0)
            material_top = y + h - material_h

            # 梯形物料
            slope = 12 / h
            material_left_x = x + slope * material_h
            material_right_x = x + w - slope * material_h

            material_path = QPainterPath()
            # 物料顶部弧形（模拟堆积）
            material_path.moveTo(int(material_left_x), int(material_top))
            material_path.lineTo(int(material_right_x), int(material_top))
            material_path.lineTo(int(x + w), int(y + h))
            material_path.lineTo(int(x), int(y + h))
            material_path.closeSubpath()
            painter.drawPath(material_path)

            # 物料纹理线
            painter.setPen(QPen(QColor(255, 255, 255, 10), 1))
            for i in range(int(material_h / 8)):
                line_y = int(material_top + i * 8 + 4)
                line_left = x + slope * (line_y - y - h + material_h)
                line_right = x + w - slope * (line_y - y - h + material_h)
                painter.drawLine(int(line_left), line_y, int(line_right), line_y)

        # ========== 5. 加强筋（工业细节） ==========
        painter.setPen(Qt.NoPen)
        rib_gradient = QLinearGradient(int(x), int(y), int(x), int(y + h))
        rib_gradient.setColorAt(0, QColor(255, 255, 255, 40))
        rib_gradient.setColorAt(0.5, QColor(0, 0, 0, 30))
        rib_gradient.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(rib_gradient))

        # 左侧加强筋
        for i in range(3):
            rib_x = int(x + 15 + i * 4)
            rib_path = QPainterPath()
            rib_path.moveTo(rib_x, int(y + 5))
            rib_path.lineTo(rib_x + 2, int(y + 5))
            rib_path.lineTo(rib_x + 2, int(y + h - 5))
            rib_path.lineTo(rib_x, int(y + h - 5))
            rib_path.closeSubpath()
            painter.drawPath(rib_path)

        # 右侧加强筋
        for i in range(3):
            rib_x = int(x + w - 17 - i * 4)
            rib_path = QPainterPath()
            rib_path.moveTo(rib_x, int(y + 5))
            rib_path.lineTo(rib_x + 2, int(y + 5))
            rib_path.lineTo(rib_x + 2, int(y + h - 5))
            rib_path.lineTo(rib_x, int(y + h - 5))
            rib_path.closeSubpath()
            painter.drawPath(rib_path)

        # ========== 6. 顶部法兰（进料口） ==========
        flange_color = QColor('#5A6A7A') if not is_active else QColor('#3A7A8A')
        flange_light = QColor('#8A9AAA')
        flange_dark = QColor('#2A3A4A')

        # 法兰主体
        flange_path = QPainterPath()
        flange_path.moveTo(int(x + 5), int(y))
        flange_path.lineTo(int(x + w - 5), int(y))
        flange_path.lineTo(int(x + w - 3), int(y - 6))
        flange_path.lineTo(int(x + 3), int(y - 6))
        flange_path.closeSubpath()

        flange_gradient = QLinearGradient(int(x), int(y - 6), int(x), int(y))
        flange_gradient.setColorAt(0, flange_light)
        flange_gradient.setColorAt(0.5, flange_color)
        flange_gradient.setColorAt(1, flange_dark)
        painter.setBrush(QBrush(flange_gradient))
        painter.setPen(Qt.NoPen)
        painter.drawPath(flange_path)

        # 法兰连接螺栓孔
        painter.setBrush(QBrush(QColor('#1A202C')))
        bolt_positions = [int(x + 20), int(x + w/2), int(x + w - 20)]
        for bx in bolt_positions:
            painter.drawEllipse(int(bx - 2), int(y - 4), 4, 4)

        # ========== 7. 底部出料口（可调节闸门） ==========
        gate_color = QColor('#3D4852')
        gate_light = QColor('#606B7A')

        # 出料口形状
        gate_h = 12
        gate_path = QPainterPath()
        gate_path.moveTo(int(x + 15), int(y + h))
        gate_path.lineTo(int(x + w - 15), int(y + h))
        gate_path.lineTo(int(x + w - 10), int(y + h + gate_h))
        gate_path.lineTo(int(x + 10), int(y + h + gate_h))
        gate_path.closeSubpath()

        gate_gradient = QLinearGradient(int(x), int(y + h), int(x), int(y + h + gate_h))
        gate_gradient.setColorAt(0, gate_light)
        gate_gradient.setColorAt(1, gate_color)
        painter.setBrush(QBrush(gate_gradient))
        painter.setPen(Qt.NoPen)
        painter.drawPath(gate_path)

        # 闸门指示器（显示开关状态）
        switch_state = False
        if hasattr(self, 'simulator') and self.simulator:
            switch_state = self.simulator.get_hopper_switch_state(hopper_id)

        switch_color = QColor('#48BB78') if switch_state else QColor('#E53E3E')
        painter.setBrush(QBrush(switch_color))
        painter.drawEllipse(int(x + w/2 - 4), int(y + h + 3), 8, 6)

        # ========== 8. 观察窗 ==========
        window_x = int(x + w/2 - 15)
        window_y = int(y + h * 0.35)
        window_w = 30
        window_h = 20

        # 观察窗边框
        window_frame = QPainterPath()
        window_frame.addRoundedRect(window_x, window_y, window_w, window_h, 3, 3)
        painter.setPen(QPen(QColor('#1A202C'), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(window_frame)

        # 观察窗玻璃效果
        glass_gradient = QRadialGradient(int(window_x + window_w * 0.3), int(window_y + window_h * 0.3), window_w * 0.8)
        glass_gradient.setColorAt(0, QColor(255, 255, 255, 60))
        glass_gradient.setColorAt(0.5, QColor(150, 200, 255, 30))
        glass_gradient.setColorAt(1, QColor(50, 80, 120, 50))
        painter.setBrush(QBrush(glass_gradient))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(window_x + 1, window_y + 1, window_w - 2, window_h - 2, 2, 2)

        # 玻璃反光
        painter.setPen(QPen(QColor(255, 255, 255, 80), 1))
        painter.drawLine(int(window_x + 3), int(window_y + 4), int(window_x + 8), int(window_y + 4))

        # ========== 9. 边缘高光线 ==========
        if is_active:
            edge_color = QColor('#00FF88')
            edge_width = 2
        else:
            edge_color = QColor('#4A5568')
            edge_width = 1.5

        painter.setPen(QPen(edge_color, edge_width))
        edge_path = QPainterPath()
        edge_path.moveTo(int(x + 12), int(y))
        edge_path.lineTo(int(x + w - 12), int(y))
        edge_path.lineTo(int(x + w), int(y + h))
        edge_path.lineTo(int(x), int(y + h))
        edge_path.closeSubpath()
        painter.drawPath(edge_path)

        # 顶部高光线
        painter.setPen(QPen(QColor(255, 255, 255, 80), 1.5))
        painter.drawLine(int(x + 12), int(y), int(x + w - 12), int(y))

        # ========== 10. 料位指示器（右侧刻度） ==========
        scale_x = int(x + w + 5)
        scale_y = int(y)
        scale_h = int(h)

        # 刻度背景
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(30, 35, 45)))
        painter.drawRect(scale_x, scale_y, 6, scale_h)

        # 刻度线和百分比
        painter.setPen(QPen(QColor('#A0AEC0'), 1))
        font = QFont()
        font.setPointSize(6)
        painter.setFont(font)

        for i in range(5):
            tick_y = scale_y + int(scale_h * i / 4)
            painter.drawLine(int(scale_x), tick_y, int(scale_x + 4), tick_y)

        # 当前料位指示
        if fill_level > 0:
            level_y = int(scale_y + scale_h * (1 - fill_level / 100))
            painter.setBrush(QBrush(QColor('#48BB78')))
            painter.setPen(Qt.NoPen)
            painter.drawRect(int(scale_x + 1), level_y, 4, 3)

        # ========== 11. 标签和名称 ==========
        painter.setPen(QPen(QColor(config.COLORS['text'])))
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)

        # 标签（hopper4/5/6绘制在下方，其余在上方）
        text_width = painter.fontMetrics().horizontalAdvance(name)
        if hopper_id in ('hopper4', 'hopper5', 'hopper6'):
            label_y = int(y + h + 22)
            painter.setPen(QPen(QColor('#FFFFFF')))
            painter.drawText(int(x + w/2 - text_width/2), label_y, name)
        else:
            label_bg_rect = QRectF(int(x + w/2 - text_width/2 - 4), int(y - 22), text_width + 8, 15)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
            painter.drawRoundedRect(label_bg_rect, 4, 4)
            painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
            painter.drawRoundedRect(label_bg_rect, 4, 4)
            painter.setPen(QPen(QColor('#FFFFFF')))
            painter.drawText(int(x + w/2 - text_width/2), int(y - 11), name)

        # ========== 12. 状态指示灯 ==========
        status_x = int(x + w - 8)
        status_y = int(y + 8)

        # 状态灯底座
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor('#1A202C')))
        painter.drawEllipse(status_x - 4, status_y - 4, 10, 10)

        # 状态灯
        if is_active:
            led_color = QColor('#48BB78')
            led_glow = QColor(72, 187, 120, 80)
        elif fill_level > 0:
            led_color = QColor('#ECC94B')
            led_glow = QColor(236, 201, 75, 80)
        else:
            led_color = QColor('#718096')
            led_glow = QColor(113, 127, 150, 40)

        # 发光效果
        painter.setBrush(QBrush(led_glow))
        painter.drawEllipse(status_x - 6, status_y - 6, 14, 14)

        # 状态灯主体
        led_gradient = QRadialGradient(status_x + 1, status_y, 5)
        led_gradient.setColorAt(0, QColor(255, 255, 255, 150))
        led_gradient.setColorAt(0.3, led_color)
        led_gradient.setColorAt(1, QColor(0, 0, 0, 100))
        painter.setBrush(QBrush(led_gradient))
        painter.drawEllipse(status_x - 3, status_y - 3, 8, 8)

    def _is_hopper_active(self, hopper_id: str) -> bool:
        """检查中转斗是否活跃（有物料流经）"""
        if not hasattr(self, 'simulator') or not self.simulator:
            return False
        return self.simulator.is_hopper_active(hopper_id)

    def _draw_batching_station(self, painter: QPainter):
        """绘制高位配料站（28个小仓）"""
        bs = config.BATCHING_STATION
        x, y = bs['position']
        w, h = bs['width'], bs['height']

        # 绘制边框
        painter.setPen(QPen(QColor('#A04000'), 2))
        painter.setBrush(QBrush(QColor('#1a1a2e')))
        painter.drawRect(int(x), int(y), int(w), int(h))

        # 计算每个小仓的尺寸
        col_count = bs['columns']  # 4列
        row_count = bs['rows']     # 7行
        comp_w = (w - 20) / col_count
        comp_h = (h - 30) / row_count

        # 列标签
        painter.setPen(QPen(QColor(config.COLORS['text_secondary'])))
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)

        for col in range(col_count):
            col_x = x + 10 + col * comp_w + comp_w / 2
            painter.drawText(int(col_x - 10), int(y + 15), bs['column_names'][col])

        # 绘制小仓
        for row in range(row_count):
            for col in range(col_count):
                # 使用P1, P2, P3, P4格式以与pos.py一致
                comp_id = f"{bs['column_names'][col]}-{row + 1}"
                comp_x = x + 10 + col * comp_w
                comp_y = y + 20 + row * comp_h

                # 从simulator获取小仓料位
                level = 0
                if hasattr(self, 'small_bins') and comp_id in self.small_bins:
                    level = self.small_bins[comp_id].current_level / self.small_bins[comp_id].capacity
                elif comp_id in bs['compartments']:
                    level = bs['compartments'][comp_id].get('current_level', 0) / bs['compartments'][comp_id].get('capacity', 100)

                # 调试信息：打印小仓ID
                # print(f"Drawing bin: {comp_id}, level: {level}")

                # 绘制料仓背景（空仓状态）
                painter.setBrush(QBrush(QColor(config.COLORS['batching_compartment'])))
                painter.setPen(QPen(QColor('#A04000'), 1))
                painter.drawRect(int(comp_x + 1), int(comp_y + 1), int(comp_w - 2), int(comp_h - 2))

                # 根据料位计算填充高度和颜色
                if level > 0:
                    # 颜色渐变：根据料位从红色到绿色
                    if level > 0.8:
                        fill_color = QColor('#27AE60')  # 满 - 绿色
                    elif level > 0.6:
                        fill_color = QColor('#2ECC71')  # 高 - 浅绿色
                    elif level > 0.4:
                        fill_color = QColor('#F39C12')  # 中高 - 橙黄色
                    elif level > 0.2:
                        fill_color = QColor('#E67E22')  # 中低 - 橙色
                    else:
                        fill_color = QColor('#E74C3C')  # 低 - 红色

                    # 计算填充高度（从底部开始）
                    fill_height = max(2, int((comp_h - 2) * level))
                    fill_y = comp_y + comp_h - 1 - fill_height

                    # 绘制料位填充
                    painter.setBrush(QBrush(fill_color))
                    painter.setPen(QPen(fill_color, 0))
                    painter.drawRect(int(comp_x + 2), int(fill_y), int(comp_w - 4), int(fill_height))

                # 仓编号（显示在料仓内右侧）
                painter.setPen(QPen(QColor(config.COLORS['text'])))
                font.setPointSize(6)
                painter.setFont(font)
                painter.drawText(int(comp_x + comp_w/2 + 4), int(comp_y + comp_h/2 + 3), comp_id)

                # 料位百分比（显示在料仓内左侧）
                level_percent = int(level * 100)
                text_color = '#FFFFFF' if level > 0.3 else '#888888'
                painter.setPen(QPen(QColor(text_color)))
                font.setPointSize(7)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(int(comp_x + 20), int(comp_y + comp_h/2 + 3), f"{level_percent}%")

        # 绘制标题
        painter.setPen(QPen(QColor(config.COLORS['text'])))
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(int(x + w/2 - 40), int(y - 8), bs['name'])

    def _get_small_bin_position(self, bin_id: str) -> tuple:
        """获取小仓在视图上的位置（中心点）

        支持两种格式：
        - P1-3, P2-5 等（高位配料站小仓）
        - S1, S5, S12 等（高位储料仓小仓）
        """
        # 检查是否是高位储料仓的料仓（S1-S12）
        if bin_id.startswith('S') and bin_id[1:].isdigit():
            return self._get_high_silo_bin_position(bin_id)

        bs = config.BATCHING_STATION
        x, y = bs['position']
        w, h = bs['width'], bs['height']

        col_count = bs['columns']
        row_count = bs['rows']
        comp_w = (w - 20) / col_count
        comp_h = (h - 30) / row_count

        # 解析 bin_id (如 "P1-3" -> column=0, row=2)
        parts = bin_id.split('-')
        if len(parts) == 2:
            col_name = parts[0]  # P1, P2, P3, P4
            row_num = int(parts[1]) - 1  # 1-7 -> 0-6

            # 根据列名确定列索引
            col_names = bs['column_names']  # ['P1', 'P2', 'P3', 'P4']
            if col_name in col_names:
                col = col_names.index(col_name)
            else:
                col = 0

            comp_x = x + 10 + col * comp_w + comp_w / 2
            comp_y = y + 20 + row_num * comp_h + comp_h / 2
            return (comp_x, comp_y)

        return (0, 0)

    def _get_high_silo_bin_position(self, bin_id: str) -> tuple:
        """获取高位储料仓小仓的位置（中心点）

        Args:
            bin_id: 如 'S1', 'S5', 'S12'
        Returns:
            (x, y) 中心点坐标
        """
        sil = config.HIGH_SILO
        sil_x, sil_y = sil['position']
        sil_width = sil['width']
        sil_height = sil['height']

        # 解析料仓编号 S1-S12
        silo_num = int(bin_id[1:])  # 1-12

        # 计算行列位置
        # S1-S6在第1行（上半部分），S7-S12在第2行（下半部分）
        row = 0 if silo_num <= 6 else 1
        col = (silo_num - 1) % 6  # 0-5

        # 计算每个小仓的尺寸
        col_count = sil['columns']  # 6列
        row_count = sil['rows']     # 2行
        comp_w = (sil_width - 10) / col_count
        comp_h = (sil_height - 30) / row_count

        # 计算小仓中心位置
        comp_x = sil_x + 5 + col * comp_w + comp_w / 2
        comp_y = sil_y + 18 + row * comp_h + comp_h / 2

        return (comp_x, comp_y)

    def _draw_distribution_carts(self, painter: QPainter):
        """绘制精美的工业分料小车"""
        if not hasattr(self, 'cart_positions'):
            return

        # 为每条活跃路线绘制小车（跳过预初始化小车的绘制，启动路线时新建）
        # 注意：route5使用Cart4（水平移动在D6皮带上），由_draw_cart4单独处理
        for route_id, cart in self.cart_positions.items():
            if cart.get('_persistent') or route_id == 'route5':
                continue
            cart_x = cart['current_x']
            cart_y = cart['current_y']

            conveyor_id = cart.get('conveyor_id', 'D7')
            target_bin = cart['target_bin']

            # 获取目标小仓位置
            bin_x, bin_y = self._get_small_bin_position(target_bin)

            # 计算小车朝向（朝向目标小仓）
            dx = bin_x - cart_x
            dy = bin_y - cart_y
            dist = math.sqrt(dx * dx + dy * dy)
            facing_right = dx >= 0  # 朝右还是朝左

            # 小车尺寸
            cart_width = 40
            cart_height = 28

            # 保存画笔状态
            painter.save()

            # =============================================
            # 1. 绘制阴影
            # =============================================
            shadow_offset = 4
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(0, 0, 0, 60)))
            shadow_path = QPainterPath()
            shadow_path.addRoundedRect( int(cart_x - cart_width/2 + shadow_offset), int(cart_y - cart_height/2 + shadow_offset + 4), cart_width, cart_height - 4, 4, 4 )

            # =============================================
            # 2. 绘制车轮
            # =============================================
            wheel_radius = 7
            wheel_color = QColor('#2C3E50')
            wheel_inner = QColor('#5D6D7E')
            rim_color = QColor('#85929E')

            # 左轮
            left_wheel_x = cart_x - cart_width/3
            right_wheel_x = cart_x + cart_width/3
            wheel_y = cart_y + cart_height/2 - 2

            # 绘制左轮
            painter.setBrush(QBrush(wheel_color))
            painter.setPen(QPen(QColor('#1C2833'), 1))
            painter.drawEllipse(int(left_wheel_x - wheel_radius), int(wheel_y - wheel_radius), wheel_radius*2, wheel_radius*2)
            # 轮毂
            painter.setBrush(QBrush(rim_color))
            painter.drawEllipse(int(left_wheel_x - 3), int(wheel_y - 3), 6, 6)

            # 绘制右轮
            painter.setBrush(QBrush(wheel_color))
            painter.setPen(QPen(QColor('#1C2833'), 1))
            painter.drawEllipse(int(right_wheel_x - wheel_radius), int(wheel_y - wheel_radius), wheel_radius*2, wheel_radius*2)
            painter.setBrush(QBrush(rim_color))
            painter.drawEllipse(int(right_wheel_x - 3), int(wheel_y - 3), 6, 6)

            # =============================================
            # 3. 绘制车体主体
            # =============================================
            # 车体渐变色
            body_gradient = QRadialGradient(cart_x, cart_y - cart_height/3, cart_width)
            if cart['moving']:
                body_gradient.setColorAt(0, QColor('#F5B041'))
                body_gradient.setColorAt(1, QColor('#D68910'))
            else:
                body_gradient.setColorAt(0, QColor('#5DADE2'))
                body_gradient.setColorAt(1, QColor('#2E86C1'))

            # 主体箱体
            body_rect = QRectF(cart_x - cart_width/2, cart_y - cart_height/2, cart_width, cart_height - 6)
            painter.setBrush(QBrush(body_gradient))
            painter.setPen(QPen(QColor('#1A5276') if not cart['moving'] else QColor('#9A7D0A'), 2))
            painter.drawRoundedRect(body_rect, 5, 5)

            # =============================================
            # 4. 绘制车体细节条纹
            # =============================================
            # 警示条纹
            stripe_color = QColor('#FFFFFF') if not cart['moving'] else QColor('#1C2833')
            stripe_alpha = 100
            painter.setPen(Qt.NoPen)
            for i in range(3):
                stripe_y = cart_y - cart_height/2 + 4 + i * 4
                painter.setBrush(QBrush(QColor(stripe_color.red(), stripe_color.green(), stripe_color.blue(), stripe_alpha)))
                painter.drawRect(int(cart_x - cart_width/2 + 3), int(stripe_y), cart_width - 6, 2)

            # =============================================
            # 5. 绘制落料斗/导管
            # =============================================
            # 落料斗在车体下方中央
            funnel_width = 16
            funnel_height = 12
            funnel_y = cart_y + cart_height/2 - 8

            # 斗体
            funnel_gradient = QRadialGradient(cart_x, funnel_y, funnel_width)
            funnel_gradient.setColorAt(0, QColor('#7F8C8D'))
            funnel_gradient.setColorAt(1, QColor('#566573'))

            painter.setBrush(QBrush(funnel_gradient))
            painter.setPen(QPen(QColor('#2C3E50'), 1.5))

            # 梯形落料斗
            funnel_path = QPainterPath()
            funnel_path.moveTo(int(cart_x - funnel_width/2), int(funnel_y))
            funnel_path.lineTo(int(cart_x + funnel_width/2), int(funnel_y))
            funnel_path.lineTo(int(cart_x + funnel_width/4), int(funnel_y + funnel_height))
            funnel_path.lineTo(int(cart_x - funnel_width/4), int(funnel_y + funnel_height))
            funnel_path.closeSubpath()
            painter.drawPath(funnel_path)

            # =============================================
            # 6. 绘制电机/驱动装置
            # =============================================
            motor_width = 10
            motor_height = 8
            motor_x = cart_x + cart_width/2 - 2
            motor_y = cart_y - 2

            # 电机主体
            motor_color = QColor('#566573')
            # painter.setBrush(QBrush(motor_color))
            # painter.setPen(QPen(QColor('#2C3E50'), 1))
            # painter.drawRect(int(motor_x), int(motor_y), motor_width, motor_height)

            # 电机散热片
            for i in range(3):
                painter.setPen(QPen(QColor('#7F8C8D'), 1))
                painter.drawLine(int(motor_x + 2), int(motor_y + 1 + i * 2),
                                 int(motor_x + motor_width - 2), int(motor_y + 1 + i * 2))

            # =============================================
            # 7. 绘制护栏
            # =============================================
            rail_color = QColor('#AED6F1') if not cart['moving'] else QColor('#F9E79F')
            painter.setPen(QPen(rail_color, 2))
            # 上护栏
            painter.drawLine(int(cart_x - cart_width/2 + 2), int(cart_y - cart_height/2 + 2),
                           int(cart_x + cart_width/2 - 2), int(cart_y - cart_height/2 + 2))
            # 支撑柱
            painter.drawLine(int(cart_x - cart_width/2 + 2), int(cart_y - cart_height/2),
                           int(cart_x - cart_width/2 + 2), int(cart_y - cart_height/2 + 6))
            painter.drawLine(int(cart_x + cart_width/2 - 2), int(cart_y - cart_height/2),
                           int(cart_x + cart_width/2 - 2), int(cart_y - cart_height/2 + 6))

            # =============================================
            # 8. 绘制状态指示灯（车体正中间）
            # =============================================
            led_radius = 4
            led_center_x = cart_x
            led_center_y = cart_y - 2
            if cart['moving']:
                led_color = QColor('#2ECC71')  # 绿色 - 运行中
            else:
                led_color = QColor('#E74C3C')  # 红色 - 停止

            painter.setBrush(QBrush(led_color))
            painter.setPen(QPen(QColor('#1C2833'), 1))
            painter.drawEllipse(int(led_center_x - led_radius), int(led_center_y - led_radius),
                              led_radius*2, led_radius*2)

            # LED 发光效果
            glow_color = QColor(led_color.red(), led_color.green(), led_color.blue(), 80)
            painter.setBrush(QBrush(glow_color))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(int(led_center_x - led_radius - 2), int(led_center_y - led_radius - 2),
                              led_radius*2 + 4, led_radius*2 + 4)

            # =============================================
            # 9. 绘制连接线/电缆
            # =============================================
            # cable_color = QColor('#2C3E50')
            # painter.setPen(QPen(cable_color, 2))
            # # 从电机延伸出的电缆（根据朝向决定方向）
            # if facing_right:
            #     painter.drawLine(int(cart_x + cart_width/2 + motor_width - 2), int(cart_y),
            #                    int(cart_x + cart_width/2 + 6), int(cart_y))
            # else:
            #     painter.drawLine(int(cart_x - cart_width/2 - 4), int(cart_y),
            #                    int(cart_x - cart_width/2 - motor_width + 2), int(cart_y))

            # =============================================
            # 10. 绘制分料箭头（仅FEEDING时紫黄闪烁）
            # =============================================
            is_feeding = False
            ctx = self.controller.route_state_manager.get_route_context(route_id) if hasattr(self, 'controller') and self.controller else None
            if ctx and ctx.state.value == 'feeding':
                is_feeding = True
            flash = (self.animation_time % 1000) < 500
            arrow_color = QColor('#F1C40F') if (flash and is_feeding) else QColor('#9B59B6')
            painter.setBrush(QBrush(arrow_color))
            painter.setPen(QPen(arrow_color, 2))

            arrow_size = 10

            if dist > 0:
                nx = dx / dist
                ny = dy / dist

                tip_x = bin_x
                tip_y = bin_y

                perp_x = -ny
                perp_y = nx

                base_x = tip_x - nx * arrow_size
                base_y = tip_y - ny * arrow_size

                wing_x1 = base_x + perp_x * (arrow_size * 0.6)
                wing_y1 = base_y + perp_y * (arrow_size * 0.6)
                wing_x2 = base_x - perp_x * (arrow_size * 0.6)
                wing_y2 = base_y - perp_y * (arrow_size * 0.6)

                points = [
                    QPoint(int(tip_x), int(tip_y)),
                    QPoint(int(wing_x1), int(wing_y1)),
                    QPoint(int(wing_x2), int(wing_y2)),
                ]
                painter.drawPolygon(points)

                # 箭头发光效果
                glow_points = [
                    QPoint(int(tip_x - nx * 3), int(tip_y - ny * 3)),
                    QPoint(int(wing_x1 - nx * 2), int(wing_y1 - ny * 2)),
                    QPoint(int(wing_x2 - nx * 2), int(wing_y2 - ny * 2)),
                ]
                glow_color = QColor(107, 45, 139, 100)  # 深紫色发光
                painter.setBrush(QBrush(glow_color))
                painter.setPen(Qt.NoPen)
                painter.drawPolygon(glow_points)

            # 恢复画笔状态
            painter.restore()

            # =============================================
            # 11. 绘制小车标签
            # =============================================
            painter.setPen(QPen(QColor(config.COLORS['text'])))
            font = QFont()
            font.setPointSize(7)
            font.setBold(False)
            painter.setFont(font)
            label = conveyor_id
            painter.drawText(int(cart_x - 12), int(cart_y - cart_height/2 - 8), label)

    def _draw_cart4(self, painter: QPainter):
        """绘制小车4 - 高位储料仓补料小车（水平移动在D6皮带上）
        
        小车4在D6皮带上水平移动：
        - 左分料：为S1-S6补料
        - 右分料：为S7-S12补料
        - 位置传感器：1-6表示位于6个列的中间位置
        - 左极限：皮带最左侧
        - 右极限：皮带最右侧

        绘制风格与其他小车(Cart1-3)一致，朝向上方放料。
        """
        # 获取D6皮带信息
        if 'D6' not in self.conveyors:
            return

        conv = self.conveyors['D6']
        x1, y1 = conv.start_pos
        x2, y2 = conv.end_pos

        # D6是水平皮带
        belt_length = abs(x2 - x1)

        # 从控制器读取Cart4实际位置（非视图本地副本）
        cart4_pos = getattr(self, 'cart4_position', 1)
        position_ratio = cart4_pos / 6.0
        cart_x = int(x1 + belt_length * position_ratio)
        cart_y = int(y1)

        # 小车尺寸（D6小车缩小）
        cart_width = 28
        cart_height = 20

        # 获取小车是否在移动
        cart_moving = False
        route5_active = False
        has_material_on_belt = False
        if hasattr(self, 'controller') and self.controller:
            cart_moving = self.controller.cart4_is_moving
            cart4_target = self.controller.cart4_target_position
            cart4_current = self.controller.cart4_position
            # 判断是否停止在目标位置（显示补料箭头的前提条件）
            cart_stopped_at_target = (not cart_moving and cart4_current == cart4_target)
            # 检查路线⑤是否激活
            route5_active = 'route5' in self.active_routes
            # 检查D6皮带上是否有物料
            if 'D6' in self.controller.conveyors:
                d6_conv = self.controller.conveyors['D6']
                has_material_on_belt = any(
                    m.current_conveyor == 'D6' and m.is_active and m.route_id == 'route5'
                    for m in self.controller.materials
                )

        # 保存画笔状态
        painter.save()

        # 1. 绘制阴影
        shadow_offset = 4
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 60)))
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(
            int(cart_x - cart_width/2 + shadow_offset),
            int(cart_y - cart_height/2 + shadow_offset + 4),
            cart_width, cart_height - 4, 4, 4
        )
        painter.drawPath(shadow_path)

        # 2. 绘制车轮
        wheel_radius = 7
        wheel_color = QColor('#2C3E50')
        rim_color = QColor('#85929E')

        left_wheel_x = cart_x - cart_width/3
        right_wheel_x = cart_x + cart_width/3
        wheel_y = cart_y + cart_height/2 - 2

        painter.setBrush(QBrush(wheel_color))
        painter.setPen(QPen(QColor('#1C2833'), 1))
        painter.drawEllipse(int(left_wheel_x - wheel_radius), int(wheel_y - wheel_radius),
                          wheel_radius*2, wheel_radius*2)
        painter.setBrush(QBrush(rim_color))
        painter.drawEllipse(int(left_wheel_x - 3), int(wheel_y - 3), 6, 6)

        painter.setBrush(QBrush(wheel_color))
        painter.setPen(QPen(QColor('#1C2833'), 1))
        painter.drawEllipse(int(right_wheel_x - wheel_radius), int(wheel_y - wheel_radius),
                          wheel_radius*2, wheel_radius*2)
        painter.setBrush(QBrush(rim_color))
        painter.drawEllipse(int(right_wheel_x - 3), int(wheel_y - 3), 6, 6)

        # 3. 绘制车体主体
        body_gradient = QRadialGradient(cart_x, cart_y - cart_height/3, cart_width)
        # 补料状态：有料流动且小车停止在目标位置时变成橙色
        is_discharging = has_material_on_belt and cart_stopped_at_target
        if is_discharging or cart_moving:
            body_gradient.setColorAt(0, QColor('#F5B041'))
            body_gradient.setColorAt(1, QColor('#D68910'))
        else:
            body_gradient.setColorAt(0, QColor('#5DADE2'))
            body_gradient.setColorAt(1, QColor('#2E86C1'))

        body_rect = QRectF(cart_x - cart_width/2, cart_y - cart_height/2,
                          cart_width, cart_height - 6)
        painter.setBrush(QBrush(body_gradient))
        painter.setPen(QPen(QColor('#1A5276') if not is_discharging and not cart_moving else QColor('#9A7D0A'), 2))
        painter.drawRoundedRect(body_rect, 5, 5)

        # 4. 绘制车体细节条纹
        stripe_color = QColor('#FFFFFF') if not is_discharging and not cart_moving else QColor('#1C2833')
        stripe_alpha = 100
        painter.setPen(Qt.NoPen)
        for i in range(3):
            stripe_y = cart_y - cart_height/2 + 4 + i * 4
            painter.setBrush(QBrush(QColor(stripe_color.red(), stripe_color.green(),
                                           stripe_color.blue(), stripe_alpha)))
            painter.drawRect(int(cart_x - cart_width/2 + 3), int(stripe_y), cart_width - 6, 2)

        # 5. 绘制落料斗（朝上）
        funnel_width = 16
        funnel_height = 12
        funnel_y = cart_y - cart_height/2 - 4

        funnel_gradient = QRadialGradient(cart_x, funnel_y, funnel_width)
        funnel_gradient.setColorAt(0, QColor('#7F8C8D'))
        funnel_gradient.setColorAt(1, QColor('#566573'))

        painter.setBrush(QBrush(funnel_gradient))
        painter.setPen(QPen(QColor('#2C3E50'), 1.5))

        funnel_path = QPainterPath()
        funnel_path.moveTo(int(cart_x - funnel_width/4), int(funnel_y))
        funnel_path.lineTo(int(cart_x + funnel_width/4), int(funnel_y))
        funnel_path.lineTo(int(cart_x + funnel_width/2), int(funnel_y - funnel_height))
        funnel_path.lineTo(int(cart_x - funnel_width/2), int(funnel_y - funnel_height))
        funnel_path.closeSubpath()
        painter.drawPath(funnel_path)

        # 6. 绘制电机
        motor_width = 10
        motor_height = 8
        motor_x = cart_x + cart_width/2 - 2
        motor_y = cart_y - 2

        motor_color = QColor('#566573')
        painter.setBrush(QBrush(motor_color))
        painter.setPen(QPen(QColor('#2C3E50'), 1))
        painter.drawRect(int(motor_x), int(motor_y), motor_width, motor_height)

        motor_led = QColor('#2ECC71') if cart_moving else QColor('#E74C3C')
        # 补料时LED变橙色
        if has_material_on_belt and cart_stopped_at_target:
            motor_led = QColor('#F5B041')
        painter.setBrush(QBrush(motor_led))
        painter.drawEllipse(int(motor_x + 3), int(motor_y + 2), 4, 4)

        # 7. 绘制护栏
        rail_color = QColor('#AED6F1') if not cart_moving else QColor('#F9E79F')
        painter.setPen(QPen(rail_color, 2))
        painter.drawLine(int(cart_x - cart_width/2 + 2), int(cart_y - cart_height/2 + 2),
                       int(cart_x + cart_width/2 - 2), int(cart_y - cart_height/2 + 2))
        painter.drawLine(int(cart_x - cart_width/2 + 2), int(cart_y - cart_height/2),
                       int(cart_x - cart_width/2 + 2), int(cart_y - cart_height/2 + 6))
        painter.drawLine(int(cart_x + cart_width/2 - 2), int(cart_y - cart_height/2),
                       int(cart_x + cart_width/2 - 2), int(cart_y - cart_height/2 + 6))

        # 8. 绘制状态指示灯
        led_radius = 4
        led_center_x = cart_x
        led_center_y = cart_y - 2
        led_color = QColor('#2ECC71') if cart_moving else QColor('#E74C3C')

        painter.setBrush(QBrush(led_color))
        painter.setPen(QPen(QColor('#1C2833'), 1))
        painter.drawEllipse(int(led_center_x - led_radius), int(led_center_y - led_radius),
                          led_radius*2, led_radius*2)

        glow_color = QColor(led_color.red(), led_color.green(), led_color.blue(), 80)
        painter.setBrush(QBrush(glow_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(int(led_center_x - led_radius - 2), int(led_center_y - led_radius - 2),
                          led_radius*2 + 4, led_radius*2 + 4)

        # 9. 小车对称设计，无右侧延伸线（已去除右侧灰色小方块）

        # 10. 绘制分料箭头 - 仅在路线⑤激活、有物料流动、小车停止于目标位置时显示
        # 补料时箭头和车体变橙色
        show_material_arrow = route5_active and has_material_on_belt and cart_stopped_at_target

        if show_material_arrow:
            target_bin_id = None
            if hasattr(self.controller, 'route_to_bin'):
                target_bin_id = self.controller.route_to_bin.get('route5')

            if target_bin_id and hasattr(self, '_get_high_silo_bin_position'):
                bin_x, bin_y = self._get_high_silo_bin_position(target_bin_id)

                # 计算小车到料仓的方向
                dx = bin_x - cart_x
                dy = bin_y - cart_y
                dist = math.sqrt(dx * dx + dy * dy)

                if dist > 0:
                    # 紫色/黄色交替闪烁 (0.5s)
                    flash = (self.animation_time % 1000) < 500
                    arrow_color = QColor('#F1C40F') if flash else QColor('#9B59B6')
                    painter.setBrush(QBrush(arrow_color))
                    painter.setPen(QPen(arrow_color, 2))

                    arrow_size = 12
                    nx = dx / dist
                    ny = dy / dist

                    tip_x = bin_x
                    tip_y = bin_y

                    # 计算垂直于方向的点
                    perp_x = -ny
                    perp_y = nx

                    base_x = tip_x - nx * arrow_size
                    base_y = tip_y - ny * arrow_size

                    wing_x1 = base_x + perp_x * (arrow_size * 0.6)
                    wing_y1 = base_y + perp_y * (arrow_size * 0.6)
                    wing_x2 = base_x - perp_x * (arrow_size * 0.6)
                    wing_y2 = base_y - perp_y * (arrow_size * 0.6)

                    points = [
                        QPoint(int(tip_x), int(tip_y)),
                        QPoint(int(wing_x1), int(wing_y1)),
                        QPoint(int(wing_x2), int(wing_y2)),
                    ]
                    painter.drawPolygon(points)

                    # 箭头发光效果（绿色）
                    glow_points = [
                        QPoint(int(tip_x - nx * 3), int(tip_y - ny * 3)),
                        QPoint(int(wing_x1 - nx * 2), int(wing_y1 - ny * 2)),
                        QPoint(int(wing_x2 - nx * 2), int(wing_y2 - ny * 2)),
                    ]
                    glow_color = QColor(155, 89, 182, 100)  # 紫色发光
                    painter.setBrush(QBrush(glow_color))
                    painter.setPen(Qt.NoPen)
                    painter.drawPolygon(glow_points)

        # 11. 绘制位置标签（不带Cart4名称）
        painter.setPen(QPen(QColor(config.COLORS['text'])))
        font = QFont()
        font.setPointSize(7)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(int(cart_x - 6), int(cart_y - cart_height/2 - 8), f"{cart4_pos:.0f}")

        # 恢复画笔状态
        painter.restore()

    def _draw_high_silo_top(self, painter: QPainter):
        """绘制高位储料仓上半部分（第1行小仓和边框上半部分）"""
        sil = config.HIGH_SILO
        x, y = sil['position']
        h = sil['height']
        full_w = sil['width']

        # 计算每个小仓的尺寸（满铺大矩形框）
        col_count = sil['columns']  # 6列
        row_count = sil['rows']     # 2行
        margin = 2
        spacing = 1
        comp_w = (full_w - margin * 2 - (col_count - 1) * spacing) / col_count
        comp_h = (h - margin * 2) / row_count  # 两行均分整个高度

        # 检查是否正在补料（路线⑤激活 + 有物料 + 小车停止在目标位置）
        is_discharging = False
        target_bin_id = None
        if hasattr(self, 'controller') and self.controller:
            route5_active = 'route5' in self.active_routes
            has_material_on_belt = any(
                m.current_conveyor == 'D6' and m.is_active and m.route_id == 'route5'
                for m in self.controller.materials
            ) if hasattr(self.controller, 'materials') else False
            cart_moving = self.controller.cart4_is_moving
            cart4_target = self.controller.cart4_target_position
            cart4_current = self.controller.cart4_position
            cart_stopped = (not cart_moving and cart4_current == cart4_target)
            is_discharging = route5_active and has_material_on_belt and cart_stopped
            if is_discharging:
                target_bin_id = self.controller.route_to_bin.get('route5')

        # 绘制大矩形边框
        painter.setPen(QPen(QColor('#1A5276'), 2))
        painter.setBrush(QBrush(QColor('#1a2e3a')))
        painter.drawRect(int(x), int(y), int(full_w), int(h))

        # 绘制上半部分小仓（第1行，贴近顶部）
        painter.setPen(QPen(QColor(config.COLORS['text_secondary'])))
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)

        # 绘制第1行小仓
        row = 0
        for col in range(col_count):
            comp_id = sil['column_names'][col]
            comp_x = x + margin + col * (comp_w + spacing)
            comp_y = y + margin

            # 获取料仓ID（高位储料仓格式 S{1-12} 对应 S1-S12）
            comp_idx = row * col_count + col
            actual_id = f"S{comp_idx + 1}"
            # 获取料位
            level = 0.0
            if hasattr(self, 'silo_compartments') and actual_id in self.silo_compartments:
                comp = self.silo_compartments[actual_id]
                level = comp['current_level'] / comp['capacity'] if comp['capacity'] > 0 else 0

            # 检查是否正在补料
            is_target = (target_bin_id == actual_id)

            # 绘制料仓背景（与配料站一致：先画背景框）
            bg_color = QColor('#F5B041') if is_target else QColor(config.COLORS['batching_compartment'])
            painter.setBrush(QBrush(bg_color))
            painter.setPen(QPen(QColor('#1A5276'), 1))
            painter.drawRect(int(comp_x + 1), int(comp_y + 1), int(comp_w - 2), int(comp_h - 2))

            # 料位填充（与配料站颜色方案完全一致）
            if level > 0:
                if level > 0.8:
                    fill_color = QColor('#27AE60')   # 绿色 - 满
                elif level > 0.6:
                    fill_color = QColor('#2ECC71')   # 浅绿 - 高
                elif level > 0.4:
                    fill_color = QColor('#F39C12')   # 橙黄 - 中高
                elif level > 0.2:
                    fill_color = QColor('#E67E22')   # 橙色 - 中低
                else:
                    fill_color = QColor('#E74C3C')   # 红色 - 低

                fill_height = max(2, int((comp_h - 2) * level))
                fill_y = comp_y + comp_h - 1 - fill_height
                painter.setBrush(QBrush(fill_color))
                painter.setPen(QPen(fill_color, 0))
                painter.drawRect(int(comp_x + 2), int(fill_y), int(comp_w - 4), int(fill_height))

            # 料位百分比
            level_pct = int(level * 100)
            text_c = '#FFFFFF' if level > 0.3 else '#888888'
            painter.setPen(QPen(QColor(text_c)))
            f = QFont()
            f.setPointSize(7)
            f.setBold(True)
            painter.setFont(f)
            painter.drawText(int(comp_x + 3), int(comp_y + comp_h/2 + 3), f"{level_pct}%")

            # 仓编号
            painter.setPen(QPen(QColor(config.COLORS['text'])))
            f.setPointSize(6)
            f.setBold(False)
            painter.setFont(f)
            painter.drawText(int(comp_x + comp_w - 22), int(comp_y + comp_h/2 + 3), actual_id)

        # 绘制标题
        painter.setPen(QPen(QColor(config.COLORS['text'])))
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(int(x + full_w/2 - 40), int(y - 8), sil['name'])

    def _draw_high_silo_bottom(self, painter: QPainter):
        """绘制高位储料仓下半部分（第2行小仓，贴近底部）"""
        sil = config.HIGH_SILO
        x, y = sil['position']
        h = sil['height']
        full_w = sil['width']

        # 与大矩形框统一计算
        col_count = sil['columns']
        row_count = sil['rows']
        margin = 2
        spacing = 1
        comp_w = (full_w - margin * 2 - (col_count - 1) * spacing) / col_count
        comp_h = (h - margin * 2) / row_count

        # 检查是否正在补料
        is_discharging = False
        target_bin_id = None
        if hasattr(self, 'controller') and self.controller:
            route5_active = 'route5' in self.active_routes
            has_material_on_belt = any(
                m.current_conveyor == 'D6' and m.is_active and m.route_id == 'route5'
                for m in self.controller.materials
            ) if hasattr(self.controller, 'materials') else False
            cart_moving = self.controller.cart4_is_moving
            cart4_target = self.controller.cart4_target_position
            cart4_current = self.controller.cart4_position
            cart_stopped = (not cart_moving and cart4_current == cart4_target)
            is_discharging = route5_active and has_material_on_belt and cart_stopped
            if is_discharging:
                target_bin_id = self.controller.route_to_bin.get('route5')

        # 第2行起始位置（紧贴第1行下方，底部贴近大框底部）
        bottom_start_y = y + margin + comp_h

        font = QFont()
        font.setPointSize(7)
        painter.setFont(font)

        row = 1
        for col in range(col_count):
            comp_x = x + margin + col * (comp_w + spacing)
            comp_y = bottom_start_y

            # 从simulator获取小仓料位
            level = 0
            comp_idx = row * col_count + col
            actual_id = f"S{comp_idx + 1}"
            if hasattr(self, 'silo_compartments') and actual_id in self.silo_compartments:
                comp = self.silo_compartments[actual_id]
                level = comp['current_level'] / comp['capacity'] if comp['capacity'] > 0 else 0

            # 检查是否正在补料到这个料仓
            is_target = (target_bin_id == actual_id)

            # 小仓颜色（根据填充状态和补料状态）
            # 背景
            bg_c = QColor('#F5B041') if is_target else QColor(config.COLORS['batching_compartment'])
            painter.setBrush(QBrush(bg_c))
            painter.setPen(QPen(QColor('#1A5276'), 1))
            painter.drawRect(int(comp_x + 1), int(comp_y + 1), int(comp_w - 2), int(comp_h - 2))

            # 料位填充（与配料站一致）
            if level > 0:
                if level > 0.8: fc = QColor('#27AE60')
                elif level > 0.6: fc = QColor('#2ECC71')
                elif level > 0.4: fc = QColor('#F39C12')
                elif level > 0.2: fc = QColor('#E67E22')
                else: fc = QColor('#E74C3C')
                fh = max(2, int((comp_h - 2) * level))
                fy = comp_y + comp_h - 1 - fh
                painter.setBrush(QBrush(fc))
                painter.setPen(QPen(fc, 0))
                painter.drawRect(int(comp_x + 2), int(fy), int(comp_w - 4), int(fh))

            # 百分比 + 编号
            lp = int(level * 100)
            tc = '#FFF' if level > 0.3 else '#888'
            painter.setPen(QPen(QColor(tc)))
            ff = QFont(); ff.setPointSize(7); ff.setBold(True); painter.setFont(ff)
            painter.drawText(int(comp_x + 3), int(comp_y + comp_h/2 + 3), f'{lp}%')
            painter.setPen(QPen(QColor(config.COLORS['text'])))
            ff.setPointSize(6); ff.setBold(False); painter.setFont(ff)
            painter.drawText(int(comp_x + comp_w - 22), int(comp_y + comp_h/2 + 3), actual_id)

    def _draw_sensors(self, painter: QPainter):
        """绘制所有接近开关传感器"""
        for sensor_id, sensor_config in config.SENSORS.items():
            self._draw_single_sensor(painter, sensor_config, sensor_id)

    def _draw_single_sensor(self, painter: QPainter, sensor: dict, sensor_id: str):
        """绘制单个接近开关传感器"""
        x, y = sensor['position']

        # 检查传感器是否激活
        is_active = self._is_sensor_active(sensor_id)

        # 传感器颜色
        if is_active:
            main_color = QColor(config.COLORS['sensor_active'])  # 绿色点亮
            glow_color = QColor('#00FF00')
            glow_color.setAlpha(60)
        else:
            main_color = QColor(config.COLORS['sensor_inactive'])  # 灰色
            glow_color = QColor('#30363d')
            glow_color.setAlpha(40)

        # 绘制发光效果
        glow_radius = 15
        painter.setBrush(QBrush(glow_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(int(x - glow_radius), int(y - glow_radius),
                          glow_radius * 2, glow_radius * 2)

        # 绘制传感器本体（开关形状）
        painter.setBrush(QBrush(main_color))
        painter.setPen(QPen(QColor('#21262d'), 2))

        # 矩形开关形状
        w, h = 16, 12
        painter.drawRect(int(x - w/2), int(y - h/2), w, h)

        # 中心点（表示感应区域）
        inner_color = QColor('#FFFFFF') if is_active else QColor('#30363d')
        painter.setBrush(QBrush(inner_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(int(x - 3), int(y - 3), 6, 6)

        # 绘制传感器ID标签
        painter.setPen(QPen(QColor(config.COLORS['text_secondary'])))
        font = QFont()
        font.setPointSize(7)
        painter.setFont(font)
        # 传感器ID贴紧右上方
        painter.drawText(int(x + 6), int(y - 4), sensor_id)

    def _is_sensor_active(self, sensor_id: str) -> bool:
        """检查传感器是否激活"""
        if not hasattr(self, 'simulator') or not self.simulator:
            return False
        return self.simulator.get_sensor_state(sensor_id)

    def _draw_materials(self, painter: QPainter):
        """绘制物料"""
        if not hasattr(self, 'materials'):
            return

        for material in self.materials:
            if not getattr(material, 'is_active', False):
                continue
            self._draw_single_material(painter, material)

    def _draw_single_material(self, painter: QPainter, material):
        """绘制单个物料（堆状效果）"""
        x, y = material.position
        material_type = getattr(material, 'material_type', 'stone_powder')

        # 获取皮带方向来调整横向宽度
        conveyor_id = getattr(material, 'current_conveyor', None)
        is_vertical = False
        if conveyor_id and conveyor_id in config.CONVEYORS:
            is_vertical = config.CONVEYORS[conveyor_id].get('vertical', False)

        # 根据物料类型设置颜色和尺寸
        if material_type == 'stone_powder':
            base_color = QColor('#B8C4CE')  # 灰白色
            particle_count = 8
            base_size = 3
            stack_height = 6

        elif material_type == 'aggregate_10mm':
            base_color = QColor('#C4A35A')  # 灰黄色
            particle_count = 6
            base_size = 5
            stack_height = 8

        elif material_type == 'aggregate_20mm':
            base_color = QColor('#4A6572')  # 深灰蓝色
            particle_count = 4
            base_size = 7
            stack_height = 10

        else:
            base_color = QColor('#F39C12')
            particle_count = 6
            base_size = 5
            stack_height = 8

        # 根据皮带方向调整spread（横向扩散）
        lateral_factor = 0.6 if is_vertical else 1.0

        painter.setPen(Qt.NoPen)

        # 底部颗粒
        for i in range(particle_count):
            angle_offset = (i / particle_count) * 2 * math.pi + material.animation_offset
            spread = particle_count - i + 1
            px = x + int(spread * 1.2 * lateral_factor * math.cos(angle_offset))
            py = y + int(spread * 0.6 * math.sin(angle_offset) * 0.5)

            size_factor = 1.0 - (i / particle_count) * 0.4
            particle_size = base_size * size_factor

            color = QColor(base_color)
            color_factor = 0.7 + (i / particle_count) * 0.3
            color.setRed(int(color.red() * color_factor))
            color.setGreen(int(color.green() * color_factor))
            color.setBlue(int(color.blue() * color_factor))

            painter.setBrush(QBrush(color))
            painter.drawEllipse(int(px - particle_size/2), int(py - particle_size/2),
                              int(particle_size), int(particle_size))

        # 顶部小颗粒（粉末效果）
        top_particles = particle_count // 2
        for i in range(top_particles):
            angle_offset = (i / top_particles) * 2 * math.pi + material.animation_offset * 1.5
            spread = 1.2 * lateral_factor
            px = x + int(spread * math.cos(angle_offset))
            py = y - stack_height + int(spread * 0.4 * math.sin(angle_offset) * 0.5)

            particle_size = base_size * 0.6
            color = QColor('#D8DDE3')
            painter.setBrush(QBrush(color))
            painter.drawEllipse(int(px - particle_size/2), int(py - particle_size/2),
                              int(particle_size), int(particle_size))

    def _draw_hexagon(self, painter: QPainter, cx: int, cy: int, size: int):
        """绘制六边形（用于碎石）"""
        points = []
        for i in range(6):
            angle = math.pi / 3 * i - math.pi / 6
            px = cx + int(size / 2 * math.cos(angle))
            py = cy + int(size / 2 * math.sin(angle))
            points.append(QPoint(px, py))
        path = QPainterPath()
        path.moveTo(points[0])
        for pt in points[1:]:
            path.lineTo(pt)
        path.closeSubpath()
        painter.drawPath(path)

    def _draw_diamond(self, painter: QPainter, cx: int, cy: int, size: int):
        """绘制菱形（用于大碎石）"""
        points = [
            QPoint(cx, cy - size),       # 上
            QPoint(cx + size, cy),        # 右
            QPoint(cx, cy + size),        # 下
            QPoint(cx - size, cy),        # 左
        ]
        path = QPainterPath()
        path.moveTo(points[0])
        for pt in points[1:]:
            path.lineTo(pt)
        path.closeSubpath()
        painter.drawPath(path)

    def _draw_silo_discharge_arrow(self, painter: QPainter):
        """绘制高位储料仓出料箭头（路线⑧⑨）

        从选定的起点料仓（S仓）垂直向下绘制箭头，表示物料从料仓流入皮带。
        """
        # 检查路线⑧或⑨是否激活且有物料在皮带上
        if not hasattr(self, 'controller') or not self.controller:
            return

        route7_active = 'route7' in self.active_routes
        route8_active = 'route8' in self.active_routes

        if not (route7_active or route8_active):
            return

        # 获取起点仓（路线⑦⑧的S仓来自 route_silo_bin）
        start_bin_7 = self.controller.route_silo_bin.get('route7')
        start_bin_8 = self.controller.route_silo_bin.get('route8')

        def draw_single_arrow(route_id, start_bin):
            """绘制单个出料箭头"""
            if not start_bin or not start_bin.startswith('S'):
                return

            # 获取料仓位置
            bin_x, bin_y = self._get_high_silo_bin_position(start_bin)

            # 检查皮带上是否有物料
            conveyors_to_check = ['D1', 'D2']
            has_material = any(
                m.current_conveyor in conveyors_to_check and m.is_active and m.route_id == route_id
                for m in self.controller.materials
            )

            if not has_material:
                return

            # D1皮带起点 (更新为缩短后的位置)
            # D2皮带起点
            d1_x, d1_y = 1048, 522
            d2_x, d2_y = 1157, 542

            # 箭头终点
            if route_id == 'route7':
                arrow_end_x, arrow_end_y = d1_x, d1_y
            else:
                arrow_end_x, arrow_end_y = d2_x, d2_y

            painter.save()

            # 出料仓红色高亮框
            hl_margin = 6
            painter.setPen(QPen(QColor('#E74C3C'), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(int(bin_x - hl_margin), int(bin_y - hl_margin),
                           int(hl_margin * 2), int(hl_margin * 2))

            # 箭头颜色：绿色闪烁
            flash = (self.animation_time % 1000) < 500
            arrow_color = QColor('#2ECC71') if flash else QColor('#27AE60')
            painter.setPen(QPen(arrow_color, 3))
            painter.setBrush(QBrush(arrow_color))

            # 绘制箭头线段
            painter.drawLine(int(bin_x), int(bin_y), int(arrow_end_x), int(arrow_end_y))

            # 绘制箭头头部
            arrow_size = 10
            # 计算箭头方向（从料仓指向皮带）
            dx = arrow_end_x - bin_x
            dy = arrow_end_y - bin_y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > 0:
                nx = dx / dist
                ny = dy / dist

                # 箭头三角形
                tip_x = arrow_end_x
                tip_y = arrow_end_y
                wing_size = arrow_size * 0.6

                wing1_x = tip_x - wing_size * nx - wing_size * ny
                wing1_y = tip_y - wing_size * ny + wing_size * nx
                wing2_x = tip_x - wing_size * nx + wing_size * ny
                wing2_y = tip_y - wing_size * ny - wing_size * nx

                arrow_points = [
                    QPoint(int(tip_x), int(tip_y)),
                    QPoint(int(wing1_x), int(wing1_y)),
                    QPoint(int(wing2_x), int(wing2_y))
                ]
                painter.drawPolygon(QPolygon(arrow_points))

            painter.restore()

        # 绘制路线⑦和⑧的出料箭头
        draw_single_arrow('route7', start_bin_7)
        draw_single_arrow('route8', start_bin_8)

    def resizeEvent(self, event):
        """窗口大小改变事件"""
        super().resizeEvent(event)
