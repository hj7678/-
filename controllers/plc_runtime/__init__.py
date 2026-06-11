"""
PLC运行时模块 — 下位机逻辑的 Python 等价实现

模块结构：
  models.py          — 皮带、传感器、中转斗、小仓数据模型
  actuator.py        — 执行器控制规则 + 安全互锁
  material_tracker.py — 皮带物料位置追踪
  plc_runtime.py     — 主扫描循环 scan(inputs) → outputs

使用方式：
  from controllers.plc_runtime import PlcRuntime, PlcInputs, PlcOutputs

  runtime = PlcRuntime()
  runtime.register_belts({...})
  inputs = PlcInputs(...)
  outputs = runtime.scan(inputs)
"""
from controllers.plc_runtime.models import (
    Conveyor, Sensor, TransferHopper, SmallBin,
    _FallbackSensor, _FALLBACK_SENSOR,
)
from controllers.plc_runtime.actuator import (
    ActuatorAction,
    compute_route_belt_commands,
    compute_hopper_commands,
    compute_cart_target_position,
    compute_emergency_stop_commands,
    check_resource_availability,
)
from controllers.plc_runtime.material_tracker import (
    BeltMaterial,
    BeltState,
    tick_materials,
    add_material_to_belt,
    check_proximity_sensor,
)
from controllers.plc_runtime.plc_runtime import (
    PlcRuntime,
    PlcInputs,
    PlcOutputs,
)
