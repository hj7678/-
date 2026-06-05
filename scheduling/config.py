"""
调度模块配置 —— 物理常数 + TCP 端口
"""
# 物理常数
VC = 0.3          # 小车移动速度 (m/s)
D = 5.4           # 相邻仓中心点间距 (m)
VB = 2.5          # 皮带传输速度 (m/s)
E = 0.195         # 皮带上料效率 (t/s)
MAX_CAP = 110.0   # 料仓最大容量 (t)
CAR_START_WH = 8   # 小车起始仓位（D8 14仓模式，P3-7 → wh_id=8）

# 反向等料距离（每条皮带不同）
BASE_DIST_CONSTANT = {
    'D7': 22.1,
    'D8': 17.4,
    'D9': 12.1,
}
LONG_DIST_CONSTANT = 124.9    # 换料等料距离（仅D8 14仓跨列使用）

# 库存阈值
SAFE_DURATION_THRESHOLD = 1200     # 库存告急状态阈值 (s)
STOCK_REFILL_BELOW = 90.0        # 补料条件A：库存 < 90t
STOCK_REFILL_LINE_ORDER = 100.0  # 补料条件B：库存 < 100t 且产线有未来订单
STOCK_TRIGGER_BELOW = 70.0       # 触发一轮调度：存在库存 < 70t 的仓
STOCK_REFILL_BELOW_BOOST = 80.0  # Boost 模式补料阈值
STOCK_TRIGGER_BELOW_BOOST = 80.0  # Boost 模式触发阈值
STOCK_CRITICAL = 5.0            # 料位 ≤ 1t 的料仓置顶优先补料（~1% 容量）

# D6 高位储料仓调度参数
SILO_MAX_CAP = 420.0             # 高位储料仓料仓最大容量 (t)
SILO_TRIGGER_PCT = 95.0          # 触发补料的料位百分比

# 惩罚系数（14仓公司连续性约束使用）
URGENCY_PENALTY_FACTOR = 100000
COMPANY_STARVATION_PENALTY = 1e12
LINE_STOP_PENALTY = 1e6
PENALTY_BASE = 1e6

# TCP 端口
TCP_HOST = '0.0.0.0'
SCHEDULER_PORTS = {
    'D7': 8891,
    'D8': 8892,
    'D9': 8893,
    'D6': 8894,
}
