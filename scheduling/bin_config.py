"""
各皮带料仓配置 —— 零仿真依赖
"""

# 每条皮带负责的料仓列表（按物理位置排序：上方=小号）
BELT_BINS = {
    'D7': ['P1-1', 'P1-2', 'P1-3', 'P1-4', 'P1-5', 'P1-6', 'P1-7'],
    'D8': [
        'P2-1', 'P2-2', 'P2-3', 'P2-4', 'P2-5', 'P2-6', 'P2-7',
        'P3-1', 'P3-2', 'P3-3', 'P3-4', 'P3-5', 'P3-6', 'P3-7',
    ],
    'D9': ['P4-1', 'P4-2', 'P4-3', 'P4-4', 'P4-5', 'P4-6', 'P4-7'],
    'D6': ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12'],
}

# 每个皮带的列数
BELT_COL_COUNT = {'D7': 1, 'D8': 2, 'D9': 1, 'D6': 1}

# 皮带 → 列前缀
BELT_TO_COL_PREFIX = {'D7': 'P1', 'D8': 'P2', 'D9': 'P4'}

# D8 14仓模式的产线名称映射
LINE_NAMES_D8 = {
    1: "1 石粉", 8: "1 碎石",
    2: "2 石粉", 9: "2 碎石",
    3: "3 石粉", 10: "3 碎石",
    4: "4 石粉", 11: "4 碎石",
    5: "5 石粉", 12: "5 碎石",
    6: "6 石粉", 13: "6 碎石",
    7: "7 石粉", 14: "7 碎石",
}

# D8 14仓模式公司归属
COMPANY_LINES_D8 = {
    'A': [5, 6, 7],
    'B': [3, 4],
    'C': [1, 2],
}


def bin_id_to_wh(bin_id: str) -> int:
    """P1-3 -> 3, P4-7 -> 7（7仓单列模式）"""
    return int(bin_id.split('-')[1])


def d8_bin_id_to_wh(bin_id: str) -> int:
    """P2-1 -> 1, P2-7 -> 7, P3-1 -> 8, P3-7 -> 14"""
    col, row = bin_id.split('-')
    row_num = int(row)
    if col == 'P2':
        return row_num
    else:
        return row_num + 7


def d8_wh_to_bin_id(wh_id: int) -> str:
    """1 -> P2-1, 8 -> P3-1"""
    if wh_id <= 7:
        return f"P2-{wh_id}"
    else:
        return f"P3-{wh_id - 7}"


def make_wh_to_bin_id(prefix: str):
    """返回 wh_id → bin_id 函数（7仓模式），如 prefix='P1' → 'P1-3'"""
    def _convert(wh_id: int) -> str:
        return f"{prefix}-{wh_id}"
    return _convert

