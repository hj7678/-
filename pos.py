"""
pos.py - 布局位置数据文件
自动生成 by Layout Editor
"""

# =============================================================================
# 画布尺寸
# =============================================================================
CANVAS_WIDTH = 1200
CANVAS_HEIGHT = 700

# =============================================================================
# 高位配料站
# =============================================================================
BATCHING_STATION = {
    'name': '高位配料站',
    'x': 555,
    'y': 90,
    'width': 350,
    'height': 216,
    'columns': 4,
    'rows': 7,
    'col_names': ['P1', 'P2', 'P3', 'P4'],
    'row_spacing': 5.4,  # 产线间距（米）
    }

# =============================================================================
# 小车移动参数
# =============================================================================
# 小车移动速度：0.3 m/s
CART_MOVE_SPEED = 0.3  # 米/秒
# 产线间距：5.4 m/位
LINE_SPACING = 5.4  # 米/位
# 站内部皮带长度：32.4 m（7条产线的总长度）
STATION_BELT_LENGTH = 32.4  # 米
# 从起点移动到产线1的距离：站内部皮带长度（32.4m）+ 一个产线间距（5.4m/2）
# 实际上小车停在产线1位置时，皮带上该位置距离皮带起点为32.4m
BASE_POSITION_DISTANCE = STATION_BELT_LENGTH  # 米

# 计算移动一位需要的时间
MOVE_ONE_POSITION_TIME = LINE_SPACING / CART_MOVE_SPEED  # = 5.4 / 0.3 = 18秒

# =============================================================================
# 皮带终点到小仓的映射
# =============================================================================
CONVEYOR_TO_BINS = {
    'D6': [f'S{i}' for i in range(1, 13)],   # 高位储料仓 S1-S12
    'D7': [f'P1-{i}' for i in range(1, 8)],   # P1配料仓
    'D8': [f'P2-{i}' for i in range(1, 8)] + [f'P3-{i}' for i in range(1, 8)],  # P2和P3配料仓
    'D9': [f'P4-{i}' for i in range(1, 8)],   # P4配料仓
}

# =============================================================================
# 高位储料仓
# =============================================================================
HIGH_SILO = {
    'name': '高位储料仓',
    'x': 989,
    'y': 417,
    'width': 150,
    'height': 80,
    'rows': 2,
    'columns': 6,
    'col_names': ['S1', 'S2', 'S3', 'S4', 'S5', 'S6'],
    }

# =============================================================================
# 上料点
# =============================================================================
FEED_POINTS = {
    "feed1_1": {"name": "上料点1-1", "x": 60, "y": 315, "output": None, "feed_point": None},
    "feed1_2": {"name": "上料点1-2", "x": 45, "y": 500, "output": None, "feed_point": None},
    "feed2_1": {"name": "上料点2-1", "x": 195, "y": 192, "output": None, "feed_point": None},
    "feed2_2": {"name": "上料点2-2", "x": 256, "y": 204, "output": None, "feed_point": None},
    "feed3": {"name": "上料点3", "x": 1156, "y": 370, "output": None, "feed_point": None},
    "silo_out": {"name": "储料仓出料", "x": 1030, "y": 490, "output": None, "feed_point": None},
}

# =============================================================================
# 中转斗
# =============================================================================
TRANSFER_HOPPERS = {
    "hopper1": {"name": "中转斗1", "x": 170, "y": 399, "width": 45, "height": 30, "input": ['E1', 'E2', 'E5'], "output": "E8"},
    "hopper2": {"name": "中转斗2", "x": 381, "y": 267, "width": 45, "height": 30, "input": ['E7'], "output": "E9"},
    "hopper3": {"name": "中转斗3", "x": 393, "y": 344, "width": 45, "height": 30, "input": ['E8'], "output": "E10"},
    "hopper4": {"name": "中转斗4", "x": 609, "y": 417, "width": 46, "height": 30, "input": ['E10'], "output": "D7"},
    "hopper5": {"name": "中转斗5", "x": 711, "y": 400, "width": 43, "height": 34, "input": ['D4'], "output": "D8"},
    "hopper6": {"name": "中转斗6", "x": 800, "y": 410, "width": 45, "height": 30, "input": ['E9'], "output": ['D9', 'D5']},
    "hopper7": {"name": "中转斗7", "x": 920, "y": 449, "width": 45, "height": 30, "input": ['D5'], "output": "D6"},
}

# =============================================================================
# 激光测距仪传感器（检测上料点有无原料）
# =============================================================================
# 激光传感器配置：检测上料点是否有原料
# 有料=True（传感器被遮挡），无料=False（传感器未遮挡）
# 注意：激光测距仪只存在于上料点位置，用于检测该上料点是否有原料
FEED_POINT_LASER_SENSORS = {
    'feed1_1': {'name': 'S-feed1_1', 'x': 60, 'y': 315, 'feed_point': 'feed1_1'},
    'feed1_2': {'name': 'S-feed1_2', 'x': 45, 'y': 500, 'feed_point': 'feed1_2'},
    'feed2_1': {'name': 'S-feed2_1', 'x': 195, 'y': 193, 'feed_point': 'feed2_1'},
    # feed2_2: 三种物料分别检测
    'feed2_2_stone': {'name': 'S-feed2_2(石粉)', 'x': 246, 'y': 196, 'feed_point': 'feed2_2', 'material': 'stone_powder'},
    'feed2_2_10mm': {'name': 'S-feed2_2(10mm)', 'x': 256, 'y': 201, 'feed_point': 'feed2_2', 'material': 'aggregate_10mm'},
    'feed2_2_20mm': {'name': 'S-feed2_2(20mm)', 'x': 266, 'y': 206, 'feed_point': 'feed2_2', 'material': 'aggregate_20mm'},
    # feed3: 两种物料分别检测
    'feed3_stone': {'name': 'S-feed3(石粉)', 'x': 1151, 'y': 353, 'feed_point': 'feed3', 'material': 'stone_powder'},
    'feed3_10mm': {'name': 'S-feed3(10mm)', 'x': 1161, 'y': 358, 'feed_point': 'feed3', 'material': 'aggregate_10mm'},
}

# =============================================================================
# 传感器
# =============================================================================
SENSORS = {
    # E系列传感器（路线①-④）- 传感器位于皮带起点附近
    "S-E1": {"name": "S-E1", "x": 70, "y": 345, "conveyor": "E1", "distance_from_start": 0.05},   # 皮带起点5%处
    "S-E2": {"name": "S-E2", "x": 75, "y": 460, "conveyor": "E2", "distance_from_start": 0.05},   # 皮带起点5%处
    "S-E4": {"name": "S-E4", "x": 100, "y": 412, "conveyor": "E4", "distance_from_start": 0.05},   # 皮带起点5%处
    "S-E5": {"name": "S-E5", "x": 197, "y": 225, "conveyor": "E5", "distance_from_start": 0.05},  # 皮带起点5%处
    "S-E6": {"name": "S-E6", "x": 257, "y": 235, "conveyor": "E6", "distance_from_start": 0.05},  # 皮带起点5%处
    "S-E7": {"name": "S-E7", "x": 280, "y": 330, "conveyor": "E7", "distance_from_start": 0.05},  # 皮带起点5%处
    "S-E8": {"name": "S-E8", "x": 230, "y": 405, "conveyor": "E8", "distance_from_start": 0.05},  # 皮带起点5%处
    "S-E9": {"name": "S-E9", "x": 440, "y": 280, "conveyor": "E9", "distance_from_start": 0.05},  # 皮带起点5%处
    "S-E10": {"name": "S-E10", "x": 430, "y": 355, "conveyor": "E10", "distance_from_start": 0.05}, # 皮带起点5%处
    # D系列传感器（路线⑤-⑨）
    "S-D1": {"name": "S-D1", "x": 1043, "y": 520, "conveyor": "D1", "distance_from_start": 0.05}, # D1起点5%处
    "S-D2": {"name": "S-D2", "x": 1130, "y": 540, "conveyor": "D2", "distance_from_start": 0.05}, # 皮带起点5%处
    "S-D2-2": {"name": "S-D2-2", "x": 880, "y": 542, "conveyor": "D2", "distance_from_start": 0.8}, # 皮带80%处
    "S-D3": {"name": "S-D3", "x": 920, "y": 480, "conveyor": "D3", "distance_from_start": 0.05}, # 皮带起点5%处
    "S-D4": {"name": "S-D4", "x": 790, "y": 520, "conveyor": "D4", "distance_from_start": 0.05}, # 皮带起点5%处
    "S-D5": {"name": "S-D5", "x": 835, "y": 415, "conveyor": "D5", "distance_from_start": 0.05}, # 皮带起点5%处
    "S-D6": {"name": "S-D6", "x": 980, "y": 462, "conveyor": "D6", "distance_from_start": 0.05}, # 皮带起点5%处
    "S-D7": {"name": "S-D7", "x": 640, "y": 400, "conveyor": "D7", "distance_from_start": 0.05}, # 皮带起点5%处
    "S-D8": {"name": "S-D8", "x": 730, "y": 390, "conveyor": "D8", "distance_from_start": 0.05}, # 皮带起点5%处
    "S-D9": {"name": "S-D9", "x": 820, "y": 380, "conveyor": "D9", "distance_from_start": 0.05}, # 皮带起点5%处
    "S-D13": {"name": "S-D13", "x": 1157, "y": 410, "conveyor": "D13", "distance_from_start": 0.05}, # 皮带起点5%处
}

# =============================================================================
# 皮带配置
# =============================================================================
CONVEYORS = {
    "E1": {"x1": 70, "y1": 340, "x2": 70, "y2": 410, "name": "E1", "length": 16.8, "type": "NORMAL"},
    "E2": {"x1": 65, "y1": 495, "x2": 90, "y2": 420, "name": "E2", "length": 20, "type": "NORMAL"},
    "E4": {"x1": 67, "y1": 412, "x2": 167, "y2": 412, "name": "E4", "length": 85.2, "type": "NORMAL"},
    "E5": {"x1": 197, "y1": 212, "x2": 197, "y2": 402, "name": "E5", "length": 27.2, "type": "NORMAL"},
    "E6": {"x1": 257, "y1": 222, "x2": 257, "y2": 352, "name": "E6", "length": 22.5, "type": "NORMAL"},
    "E7": {"x1": 257, "y1": 352, "x2": 387, "y2": 282, "name": "E7", "length": 56, "type": "NORMAL"},
    "E8": {"x1": 217, "y1": 412, "x2": 397, "y2": 352, "name": "E8", "length": 59.7, "type": "NORMAL"},
    "E9": {"x1": 425, "y1": 272, "x2": 795, "y2": 390, "name": "E9", "length": 48, "type": "NORMAL"},
    "E10": {"x1": 410, "y1": 350, "x2": 608, "y2": 428, "name": "E10", "length": 35, "type": "NORMAL"},
    "D1": {"x1": 1048, "y1": 522, "x2": 940, "y2": 520, "name": "D1", "length": 65.8, "type": "NORMAL"},
    "D13": {"x1": 1157, "y1": 392, "x2": 1157, "y2": 542, "name": "D13", "length": 15.8, "type": "NORMAL"},
    "D2": {"x1": 1157, "y1": 542, "x2": 807, "y2": 542, "name": "D2", "length": 65.8, "type": "NORMAL"},
    "D3": {"x1": 940, "y1": 520, "x2": 820, "y2": 360, "name": "D3", "length": 36.6, "type": "NORMAL"},
    "D4": {"x1": 807, "y1": 542, "x2": 740, "y2": 420, "name": "D4", "length": 20, "type": "NORMAL"},
    "D5": {"x1": 820, "y1": 410, "x2": 920, "y2": 450, "name": "D5", "length": 27.2, "type": "NORMAL"},
    "D6": {"x1": 967, "y1": 462, "x2": 1127, "y2": 462, "name": "D6", "length": 30, "type": "NORMAL"},
    "D7": {"x1": 640, "y1": 410, "x2": 640, "y2": 90, "name": "D7", "length": 27.5 + 32.4, "type": "NORMAL"},  # 59.9m: 27.5m站外 + 32.4m站内部
    "D8": {"x1": 730, "y1": 400, "x2": 730, "y2": 90, "name": "D8", "length": 22.8 + 32.4, "type": "NORMAL"},  # 55.2m: 22.8m站外 + 32.4m站内部
    "D9": {"x1": 820, "y1": 390, "x2": 820, "y2": 90, "name": "D9", "length": 17.5 + 32.4, "type": "NORMAL"},  # 49.9m: 17.5m站外 + 32.4m站内部
}

# =============================================================================
# 上料路线配置（生产模式使用）
# =============================================================================
FEED_ROUTES = {
    # 路线①: feed1_1 → E1 → E4 → hopper1 → E8 → hopper3 → E10 → hopper4 → D7 → P1
    'route1': {
        'name': '路线①', 'conveyors': ['E1', 'E4', 'E8', 'E10', 'D7'],
        'hoppers': [None, 'hopper1', 'hopper3', 'hopper4', None],
        'destination': 'P1', 'material_types': ['stone_powder'],
        'feed_point': 'feed1_1'
    },
    # 路线②: feed1_2 → E2 → E4 → hopper1 → E8 → hopper3 → E10 → hopper4 → D7 → P1
    'route2': {
        'name': '路线②', 'conveyors': ['E2', 'E4', 'E8', 'E10', 'D7'],
        'hoppers': [None, 'hopper1', 'hopper3', 'hopper4', None],
        'destination': 'P1', 'material_types': ['stone_powder'],
        'feed_point': 'feed1_2'
    },
    # 路线③: feed2_1 → E5 → hopper1 → E8 → hopper3 → E10 → hopper4 → D7 → P1
    'route3': {
        'name': '路线③', 'conveyors': ['E5', 'E8', 'E10', 'D7'],
        'hoppers': ['hopper1', 'hopper3', 'hopper4', None],
        'destination': 'P1', 'material_types': ['stone_powder'],
        'feed_point': 'feed2_1'
    },
    # 路线④: feed2_2 → E6 → E7 → hopper2 → E9 → hopper6 → D9 → P4
    'route4': {
        'name': '路线④', 'conveyors': ['E6', 'E7', 'E9', 'D9'],
        'hoppers': [None, 'hopper2', 'hopper6', None],
        'destination': 'P4', 'material_types': ['aggregate_20mm'],
        'feed_point': 'feed2_2'
    },
    # 路线⑤: feed2_2 → E6 → E7 → hopper2 → E9 → hopper6 → D5 → hopper7 → D6 → silo
    'route5': {
        'name': '路线⑤', 'conveyors': ['E6', 'E7', 'E9', 'D5', 'D6'],
        'hoppers': [None, 'hopper2', 'hopper6', 'hopper7', None],
        'destination': '高位仓', 'material_types': None,
        'feed_point': 'feed2_2'
    },
    # 路线⑥: feed3 → D13 → D2 → D4 → hopper5 → D8 → P2/P3
    'route6': {
        'name': '路线⑥', 'conveyors': ['D13', 'D2', 'D4', 'D8'],
        'hoppers': [None, None, 'hopper5', None],
        'destination': 'P2/P3', 'material_types': None,
        'feed_point': 'feed3'
    },
    # 路线⑦: silo_out → D1 → D3 → D9 → P4 (无中转斗)
    'route7': {
        'name': '路线⑦', 'conveyors': ['D1', 'D3', 'D9'],
        'hoppers': [None, None, None],
        'destination': 'P4', 'material_types': ['aggregate_20mm'],
        'feed_point': 'silo_out'
    },
    # 路线⑧: silo_out → D2 → D4 → hopper5 → D8 → P2/P3
    'route8': {
        'name': '路线⑧', 'conveyors': ['D2', 'D4', 'D8'],
        'hoppers': [None, 'hopper5', None],
        'destination': 'P2/P3', 'material_types': None,
        'feed_point': 'silo_out'
    },
}

# =============================================================================
# 清空余料皮带配置（仅清空余料模式使用，与 FEED_ROUTES 完全独立）
# =============================================================================
# 格式：{(中转斗ID, 路线ID): [皮带ID列表]}，按物料流向顺序排列
#
# 【与 FEED_ROUTES 的区别】
# - FEED_ROUTES：生产模式下物料流向，用于正常生产调度
# - CLEARING_ROUTE_CONVEYORS：清空余料模式下各中转斗实际需要清空的皮带
#
# 【清空余料规则】
# - 能接收物料的运输节点（中转斗或料仓），接收的是"上一个运输节点之后、到自己为止"的所有皮带上的物料
# - 如果路线有中转斗，料仓只接收最后一个中转斗的输出皮带开始的余料
# - 如果路线无中转斗，料仓接收整条路线所有皮带的余料
# - 路线①②③的终点皮带 D7/D9/D8 余料受产线位置影响（产线1完整，产线7最短）
# =============================================================================
CLEARING_ROUTE_CONVEYORS = {
    # 路线①: 上料点1-1 → feed1_1 → E1 → E4 → hopper1 → E8 → hopper3 → E10 → hopper4 → D7 → P1
    ('hopper1', 'route1'): ['E1', 'E4'],
    ('hopper3', 'route1'): ['E8'],
    ('hopper4', 'route1'): ['E10'],

    # 路线②: 上料点1-2 → feed1_2 → E2 → E4 → hopper1 → E8 → hopper3 → E10 → hopper4 → D7 → P1
    ('hopper1', 'route2'): ['E2', 'E4'],
    ('hopper3', 'route2'): ['E8'],
    ('hopper4', 'route2'): ['E10'],

    # 路线③: 上料点2-1 → feed2_1 → E5 → hopper1 → E8 → hopper3 → E10 → hopper4 → D7 → P1
    ('hopper1', 'route3'): ['E5'],
    ('hopper3', 'route3'): ['E8'],
    ('hopper4', 'route3'): ['E10'],

    # 路线④: 上料点2-2 → feed2_2 → E6 → E7 → hopper2 → E9 → hopper6 → D9 → P4
    ('hopper2', 'route4'): ['E6', 'E7'],
    ('hopper6', 'route4'): ['E9'],

    # 路线⑤: 上料点2-2 → feed2_2 → E6 → E7 → hopper2 → E9 → hopper6 → D5 → hopper7 → D6 → 高位仓
    ('hopper2', 'route5'): ['E6', 'E7'],
    ('hopper6', 'route5'): ['E9'],
    ('hopper7', 'route5'): ['D5'],

    # 路线⑥: feed3 → D13 → D2 → D4 → hopper5 → D8 → P2/P3
    ('hopper5', 'route6'): ['D13', 'D2', 'D4'],

    # 路线⑦: silo_out → D1 → D3 → D9 → P4（无中转斗）

    # 路线⑧: silo_out → D2 → D4 → hopper5 → D8 → P2/P3
    ('hopper5', 'route8'): ['D2', 'D4'],
}

# =============================================================================
# 运料小车传感器配置
# =============================================================================
# 每个小车包含5个传感器：
# 1. 位置传感器 (position): byte类型，值1-7表示垂直方向7条产线位置
# 2. 左极限位置传感器 (left_limit): bool类型，true=处于左极限位置
# 3. 右极限位置传感器 (right_limit): bool类型，true=处于右极限位置
# 4. 左分料传感器 (left_divert): bool类型，true=左分料
# 5. 右分料传感器 (right_divert): bool类型，true=右分料
#
# 小车与皮带的对应关系：
# - 小车1 (Cart1) -> D7皮带 -> P1配料站（石粉）
# - 小车2 (Cart2) -> D8皮带 -> P2/P3配料站
# - 小车3 (Cart3) -> D9皮带 -> P4配料站（碎石）
#
# 极限位置说明：
# - D7小车：左极限=P1-7最下边，右极限=P1-1最上边
# - D8小车：左极限=P2-7/P3-7最下边，右极限=P2-1/P3-1最上边
# - D9小车：左极限=P4-7最下边，右极限=P4-1最上边
CART_SENSORS = {
    'Cart1': {
        'name': 'D7运料小车',
        'conveyor': 'D7',
        'destination': 'P1',
        'position_sensor': 'Cart1-Position',
        'left_limit_sensor': 'Cart1-LeftLimit',
        'right_limit_sensor': 'Cart1-RightLimit',
        'left_divert_sensor': 'Cart1-LeftDivert',
        'right_divert_sensor': 'Cart1-RightDivert',
    },
    'Cart2': {
        'name': 'D8运料小车',
        'conveyor': 'D8',
        'destination': 'P2/P3',
        'position_sensor': 'Cart2-Position',
        'left_limit_sensor': 'Cart2-LeftLimit',
        'right_limit_sensor': 'Cart2-RightLimit',
        'left_divert_sensor': 'Cart2-LeftDivert',
        'right_divert_sensor': 'Cart2-RightDivert',
    },
    'Cart3': {
        'name': 'D9运料小车',
        'conveyor': 'D9',
        'destination': 'P4',
        'position_sensor': 'Cart3-Position',
        'left_limit_sensor': 'Cart3-LeftLimit',
        'right_limit_sensor': 'Cart3-RightLimit',
        'left_divert_sensor': 'Cart3-LeftDivert',
        'right_divert_sensor': 'Cart3-RightDivert',
    },
    'Cart4': {
        'name': 'D6运料小车',
        'conveyor': 'D6',
        'destination': 'S1-S12',
        'position_sensor': 'Cart4-Position',
        'left_limit_sensor': 'Cart4-LeftLimit',
        'right_limit_sensor': 'Cart4-RightLimit',
        'left_divert_sensor': 'Cart4-LeftDivert',
        'right_divert_sensor': 'Cart4-RightDivert',
    },
    
}

# =============================================================================
# 辅助函数
# =============================================================================

SILO_BIN_MATERIALS = {
    'S1': 'aggregate_20mm', 'S2': 'aggregate_20mm', 'S3': 'aggregate_20mm',
    'S4': 'aggregate_20mm', 'S5': 'aggregate_20mm', 'S6': 'aggregate_20mm',
    'S7': 'stone_powder', 'S8': 'stone_powder',
    'S9': 'aggregate_10mm', 'S10': 'aggregate_10mm', 'S11': 'aggregate_10mm', 'S12': 'aggregate_10mm',
}

def get_all_conveyors():
    result = {}
    for cid, c in CONVEYORS.items():
        result[cid] = {
            'name': c.get('name', cid),
            'start_pos': (c['x1'], c['y1']),
            'end_pos': (c['x2'], c['y2']),
            'length': c.get('length', 20),
            'type': 'NORMAL',
        }
    return result

def get_conveyor_by_id(conv_id):
    return get_all_conveyors().get(conv_id)

def print_layout_summary():
    print("=" * 60)
    print("布局已更新")
    print("=" * 60)
    print(f"画布尺寸: {CANVAS_WIDTH} x {CANVAS_HEIGHT}")
    print(f"皮带数量: {len(CONVEYORS)}")
    print(f"传感器数量: {len(SENSORS)}")
    print(f"中转斗数量: {len(TRANSFER_HOPPERS)}")
    print("=" * 60)
