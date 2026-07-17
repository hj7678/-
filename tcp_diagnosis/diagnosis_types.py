"""
故障诊断模块 —— 标准数据结构

零仿真依赖。定义诊断引擎的输入/输出数据格式。
仿真侧和真实系统侧各自实现适配器，将自身数据转换为此格式。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class RouteState(Enum):
    IDLE = "idle"
    MOVING_TO_TARGET = "moving_to_target"
    FEEDING = "feeding"
    CLEARING = "clearing"
    WAITING = "waiting"
    STANDBY = "standby"


@dataclass
class ProximitySensorSnapshot:
    sensor_id: str
    state: bool
    conveyor_id: str


@dataclass
class HopperSnapshot:
    hopper_id: str
    switch_open: bool
    weight: float
    input_conveyor_ids: List[str]
    output_conveyor_ids: List[str]


@dataclass
class ConveyorSnapshot:
    conveyor_id: str
    is_running: bool
    speed: int


@dataclass
class CartSnapshot:
    cart_id: str
    position: int
    left_limit: bool
    right_limit: bool
    left_divert: bool
    right_divert: bool
    moving: bool = False


@dataclass
class RouteSnapshot:
    route_id: str
    state: RouteState
    conveyor_ids: List[str]
    hopper_ids: List[str]
    proximity_sensor_ids: List[str]
    clearing_strategy: str = 'reverse'
    feed_point: str = ''                     # 上料点ID
    cart_target_position: int = 0            # 小车目标位置（格号）
    early_moved_from_clearing: bool = False  # 顺序清空共享状态：小车已提前移动，清空+移动同步进行


@dataclass
class SystemSnapshot:
    """诊断引擎的标准化输入——每 tick 一帧"""
    timestamp: float
    active_route_ids: List[str]
    routes: Dict[str, RouteSnapshot]
    proximity_sensors: Dict[str, ProximitySensorSnapshot]
    hoppers: Dict[str, HopperSnapshot]
    conveyors: Dict[str, ConveyorSnapshot]
    carts: Dict[str, CartSnapshot]
    silo_gate_states: Dict[str, bool] = field(default_factory=dict)  # 卸料门实际状态
    active_source_silo: str = ''  # 当前出料的高位仓 (如 "S3")


@dataclass
class DiagnosisResult:
    sensor_id: str
    fault_type: str
    confidence: float
    description: str
    category: str
    related_sensors: List[str] = field(default_factory=list)
