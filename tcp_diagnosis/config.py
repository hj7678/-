"""
TCP 诊断服务配置 —— 独立于仿真侧，零 PyQt5 依赖
"""

# TCP 服务端绑定地址
TCP_HOST = '0.0.0.0'
TCP_PORT = 8890  # 诊断服务独立端口，不与仿真 TCP 端口冲突

# 转速传感器 → 皮带 ID 映射
SPEED_SENSOR_TO_CONVEYOR = {
    'S-CV-E1': 'E1', 'S-CV-E2': 'E2', 'S-CV-E4': 'E4', 'S-CV-E5': 'E5',
    'S-CV-E6': 'E6', 'S-CV-E7': 'E7', 'S-CV-E8': 'E8', 'S-CV-E9': 'E9', 'S-CV-E10': 'E10',
    'S-CV-D1': 'D1', 'S-CV-D2': 'D2', 'S-CV-D3': 'D3', 'S-CV-D4': 'D4',
    'S-CV-D5': 'D5', 'S-CV-D6': 'D6', 'S-CV-D7': 'D7', 'S-CV-D8': 'D8', 'S-CV-D9': 'D9', 'S-CV-D13': 'D13',
}
CONVEYOR_TO_SPEED_SENSOR = {v: k for k, v in SPEED_SENSOR_TO_CONVEYOR.items()}

# 中转斗 → 输入/输出皮带
TRANSFER_HOPPER_IO = {
    'hopper1': {'input': ['E4', 'E5', 'E8'], 'output': ['E8', 'E10']},
    'hopper2': {'input': ['E7'], 'output': ['E9']},
    'hopper3': {'input': ['E8'], 'output': ['E10']},
    'hopper4': {'input': ['E10'], 'output': ['D7']},
    'hopper5': {'input': ['D4'], 'output': ['D8']},
    'hopper6': {'input': ['E9'], 'output': ['D9', 'D5']},
    'hopper7': {'input': ['D5'], 'output': ['D6']},
}

# 上料信号 → 路线
FEED_SIGNAL_TO_ROUTES = {
    'feed1_1': ['route1'],
    'feed1_2': ['route2'],
    'feed2_1': ['route3'],
    'feed2_2': ['route4', 'route5'],
    'feed3': ['route6', 'route7'],
    'silo_out': ['route8', 'route9'],
}

# 路线定义（从 pos.py 复制，零仿真依赖）
# 每条路线: conveyors(按物料流向排序), hoppers(与conveyor穿插), proximity_sensors(按conveyor顺序)
FEED_ROUTES = {
    'route1': {
        'conveyors': ['E1', 'E4', 'E8', 'E10', 'D7'],
        'hoppers': [None, 'hopper1', 'hopper3', 'hopper4', None],
        'proximity_sensors': ['S-E1', 'S-E4', 'S-E8', 'S-E10', 'S-D7'],
    },
    'route2': {
        'conveyors': ['E2', 'E4', 'E8', 'E10', 'D7'],
        'hoppers': [None, 'hopper1', 'hopper3', 'hopper4', None],
        'proximity_sensors': ['S-E2', 'S-E4', 'S-E8', 'S-E10', 'S-D7'],
    },
    'route3': {
        'conveyors': ['E5', 'E8', 'E10', 'D7'],
        'hoppers': ['hopper1', 'hopper3', 'hopper4', None],
        'proximity_sensors': ['S-E5', 'S-E8', 'S-E10', 'S-D7'],
    },
    'route4': {
        'conveyors': ['E6', 'E7', 'E9', 'D9'],
        'hoppers': [None, 'hopper2', 'hopper6', None],
        'proximity_sensors': ['S-E6', 'S-E7', 'S-E9', 'S-D9'],
    },
    'route5': {
        'conveyors': ['E6', 'E7', 'E9', 'D5', 'D6'],
        'hoppers': [None, 'hopper2', 'hopper6', 'hopper7', None],
        'proximity_sensors': ['S-E6', 'S-E7', 'S-E9', 'S-D5', 'S-D6'],
    },
    'route6': {
        'conveyors': ['D13', 'D1', 'D3', 'D9'],
        'hoppers': [None, None, None, None],
        'proximity_sensors': ['S-D13', 'S-D1', 'S-D3', 'S-D9'],
    },
    'route7': {
        'conveyors': ['D13', 'D2', 'D4', 'D8'],
        'hoppers': [None, None, 'hopper5', None],
        'proximity_sensors': ['S-D13', 'S-D2', 'S-D4', 'S-D8'],
    },
    'route8': {
        'conveyors': ['D1', 'D3', 'D9'],
        'hoppers': [None, None, None],
        'proximity_sensors': ['S-D1', 'S-D3', 'S-D9'],
    },
    'route9': {
        'conveyors': ['D2', 'D4', 'D8'],
        'hoppers': [None, 'hopper5', None],
        'proximity_sensors': ['S-D2', 'S-D4', 'S-D8'],
    },
}
