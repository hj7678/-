"""
故障诊断模块 —— 独立诊断引擎

零依赖：不依赖 PyQt5、仿真控制器或任何项目内部模块。
可脱离仿真软件接入实际系统。
"""

from fault_diagnosis.types import (
    RouteState,
    ProximitySensorSnapshot,
    HopperSnapshot,
    ConveyorSnapshot,
    CartSnapshot,
    RouteSnapshot,
    SystemSnapshot,
    DiagnosisResult,
)
from fault_diagnosis.engine import DiagnosisEngine

__all__ = [
    'RouteState',
    'ProximitySensorSnapshot',
    'HopperSnapshot',
    'ConveyorSnapshot',
    'CartSnapshot',
    'RouteSnapshot',
    'SystemSnapshot',
    'DiagnosisResult',
    'DiagnosisEngine',
]
