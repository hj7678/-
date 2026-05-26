"""
调度模块数据类型 —— 零仿真依赖
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class BinState:
    bin_id: str
    stock: float
    consumption_rate: float
    maintenance: bool = False
    has_future_order: bool = False


@dataclass
class StepDetail:
    seq: int
    bin_id: str
    line_name: str
    mode: str
    remain_stock: float
    survival_time: float
    stock_status: str
    move_time: float
    wait_time: float
    fill_time: float
    stop_time: float
    total_time: float


@dataclass
class ScheduleResult:
    belt_id: str
    sequence: List[str] = field(default_factory=list)
    steps: List[StepDetail] = field(default_factory=list)
    total_move: float = 0.0
    total_wait: float = 0.0
    total_fill: float = 0.0
    total_stop: float = 0.0
    is_feasible: bool = True
