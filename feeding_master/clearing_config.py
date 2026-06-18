"""
FeedingMaster 调度与清空策略配置

每条皮带/策略组合可独立设置。
"""

# ══════════════════════════════════════════════
# 清空策略料位阈值 (%)
# 当目标料仓料位达到此阈值时触发 CLEARING
# ══════════════════════════════════════════════
CLEARING_THRESHOLDS = {
    'D7': {'sequential': 98, 'reverse': 95, 'column_switch': 88},
    'D8': {'sequential': 98, 'reverse': 95, 'column_switch': 88},
    'D9': {'sequential': 98, 'reverse': 94, 'column_switch': 88},  # Cart3特殊
    'D6': {'sequential': 98, 'reverse': 95, 'column_switch': 88},
}

# ══════════════════════════════════════════════
# 调度触发阈值 (%)
# ══════════════════════════════════════════════
# idle: 存在料仓低于此阈值时自动请求调度
# emergency: 存在料仓低于此阈值时紧急触发(boost)
# pre_request: 最后一个料仓达到此阈值时提前请求
SCHEDULING_THRESHOLDS = {
    'D7': {'idle': 70, 'emergency': 10, 'pre_request': 80},
    'D8': {'idle': 70, 'emergency': 10, 'pre_request': 80},
    'D9': {'idle': 70, 'emergency': 10, 'pre_request': 80},
    'D6': {'idle': 70, 'emergency': 10, 'pre_request': 80},
}

# ══════════════════════════════════════════════
# 调度请求冷却时间 (秒)
# 防止连续高频率请求
# ══════════════════════════════════════════════
SCHEDULING_COOLDOWNS = {
    'D7': 120, 'D8': 120, 'D9': 120, 'D6': 120,
}

# ══════════════════════════════════════════════
# 顺序清空小车提前移动等待时间 (秒)
# ══════════════════════════════════════════════
SEQUENTIAL_EARLY_MOVE_DELAY = 3.0

# ══════════════════════════════════════════════
# FEEDING 最小持续时间 (秒)
# 进入FEEDING后N秒内不触发清空判定
# ══════════════════════════════════════════════
MIN_FEEDING_TIME = 3.0


def get_clearing_threshold(belt_id: str, strategy: str) -> int:
    """获取指定皮带+策略的料位阈值"""
    belt_cfg = CLEARING_THRESHOLDS.get(belt_id, {})
    return belt_cfg.get(strategy, 95)


def get_scheduling_threshold(belt_id: str, key: str) -> int:
    """获取调度触发阈值(idle/emergency/pre_request)"""
    return SCHEDULING_THRESHOLDS.get(belt_id, {}).get(key, 70)


def get_scheduling_cooldown(belt_id: str) -> int:
    """获取调度请求冷却时间"""
    return SCHEDULING_COOLDOWNS.get(belt_id, 120)
