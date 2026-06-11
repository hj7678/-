"""
PLC物料追踪 —— 皮带上的物料位置追踪逻辑

纯函数设计，零外部依赖。可直接翻译为 PLC 计数器/定时器逻辑。

真实 PLC 中等价实现：
- 皮带位置 → 高速计数器（编码器脉冲累加）
- 传感器触发 → 比较指令（当前位置 >= 传感器位置）
- 到达检测 → 比较指令（当前位置 >= 皮带长度）
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class BeltMaterial:
    """皮带上的一个物料"""
    material_id: str
    distance_traveled: float = 0.0      # 已行进距离（米）
    weight_tons: float = 0.1            # 物料重量（吨）
    arrival_time: float = 0.0           # 到达该皮带的时间戳


@dataclass
class BeltState:
    """单条皮带的追踪状态"""
    belt_id: str
    length_m: float                     # 皮带长度（米）
    speed_mps: float = 0.0              # 当前速度（米/秒）
    is_running: bool = False
    materials: List[BeltMaterial] = field(default_factory=list)


def tick_materials(
    belts: Dict[str, BeltState],
    delta_seconds: float,
) -> Dict[str, List[BeltMaterial]]:
    """更新所有皮带上物料的位置（一个扫描周期）

    Args:
        belts: {belt_id: BeltState}
        delta_seconds: 本次扫描的时间步长（秒）

    Returns:
        {belt_id: [已到达皮带终点的物料列表]}
    """
    arrived: Dict[str, List[BeltMaterial]] = {}

    for belt_id, belt in belts.items():
        if not belt.is_running or belt.speed_mps <= 0:
            continue

        step_distance = belt.speed_mps * delta_seconds
        arrived_materials: List[BeltMaterial] = []

        for mat in list(belt.materials):
            mat.distance_traveled += step_distance
            if mat.distance_traveled >= belt.length_m:
                arrived_materials.append(mat)
                belt.materials.remove(mat)

        if arrived_materials:
            arrived[belt_id] = arrived_materials

    return arrived


def add_material_to_belt(
    belts: Dict[str, BeltState],
    belt_id: str,
    material_id: str,
    weight_tons: float = 0.1,
    current_time: float = 0.0,
) -> bool:
    """将新物料放到皮带起点

    Args:
        belts: 皮带状态字典
        belt_id: 目标皮带
        material_id: 物料标识
        weight_tons: 重量（吨）
        current_time: 当前时间戳

    Returns:
        是否成功添加
    """
    if belt_id not in belts:
        return False

    belt = belts[belt_id]
    belt.materials.append(BeltMaterial(
        material_id=material_id,
        distance_traveled=0.0,
        weight_tons=weight_tons,
        arrival_time=current_time,
    ))
    return True


def check_proximity_sensor(
    belt: BeltState,
    sensor_distance_from_start: float,
    sensor_hold_distance: float = 0.5,
) -> Tuple[bool, List[str]]:
    """检测是否有物料经过接近开关位置

    PLC 等价：
    - 比较指令：物料位置 >= 传感器位置
    - 上升沿检测：物料位置 - 上周期位置 < 传感器位置（穿越检测）

    Args:
        belt: 皮带状态
        sensor_distance_from_start: 传感器距皮带起点的距离（米）
        sensor_hold_distance: 传感器检测保持距离（米）

    Returns:
        (传感器是否被触发, [触发该传感器的物料ID列表])
    """
    triggered = False
    triggered_ids: List[str] = []

    for mat in belt.materials:
        d = mat.distance_traveled
        # 物料在传感器范围内
        if sensor_distance_from_start <= d <= sensor_distance_from_start + sensor_hold_distance:
            triggered = True
            triggered_ids.append(mat.material_id)

    return triggered, triggered_ids


def check_material_at_end(
    belt: BeltState,
) -> Tuple[bool, List[BeltMaterial]]:
    """检测是否有物料到达皮带终点

    Returns:
        (有物料到达?, [已到达的物料列表])
    """
    arrived = [m for m in belt.materials if m.distance_traveled >= belt.length_m]
    return len(arrived) > 0, arrived


def remove_arrived_materials(
    belt: BeltState,
) -> List[BeltMaterial]:
    """移出已到达皮带终点的物料"""
    arrived = [m for m in belt.materials if m.distance_traveled >= belt.length_m]
    for mat in arrived:
        belt.materials.remove(mat)
    return arrived


def get_material_count_on_belt(belt: BeltState) -> int:
    """皮带上的物料数量"""
    return len(belt.materials)


def get_total_weight_on_belt(belt: BeltState) -> float:
    """皮带上的物料总重量（吨）"""
    return sum(m.weight_tons for m in belt.materials)


def compute_remaining_distance(
    belt: BeltState,
    material_id: str,
) -> Optional[float]:
    """计算物料距离皮带终点的剩余距离（米）"""
    for mat in belt.materials:
        if mat.material_id == material_id:
            return max(0.0, belt.length_m - mat.distance_traveled)
    return None


def estimate_time_to_sensor(
    belt: BeltState,
    sensor_distance: float,
) -> Optional[float]:
    """估算下一个物料到达传感器所需时间（秒）

    用于 PLC 定时器预设值计算

    Args:
        belt: 皮带状态
        sensor_distance: 传感器距起点的距离（米）

    Returns:
        预计到达时间（秒），无物料时返回 None
    """
    if not belt.materials or belt.speed_mps <= 0:
        return None

    # 找到离传感器最近但尚未到达的物料
    closest_distance = float('inf')
    for mat in belt.materials:
        remaining = sensor_distance - mat.distance_traveled
        if 0 < remaining < closest_distance:
            closest_distance = remaining

    if closest_distance == float('inf'):
        return None

    return closest_distance / belt.speed_mps
