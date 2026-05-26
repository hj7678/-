"""
物料模型 - Material Model
"""

from dataclasses import dataclass, field
from typing import Tuple, Optional, List
import random
import math


# 骨料类型定义
class MaterialType:
    """骨料类型"""
    STONE_POWDER = 'stone_powder'    # 石粉
    AGGREGATE_10MM = 'aggregate_10mm'  # 10mm碎石
    AGGREGATE_20MM = 'aggregate_20mm'  # 20mm碎石

# 骨料颜色配置
MATERIAL_TYPE_COLORS = {
    MaterialType.STONE_POWDER: '#E8E8E8',    # 浅灰色 - 石粉
    MaterialType.AGGREGATE_10MM: '#A0522D',   # 赭石色 - 10mm碎石
    MaterialType.AGGREGATE_20MM: '#8B4513',   # 深褐色 - 20mm碎石
}

# 骨料名称（中文）
MATERIAL_TYPE_NAMES = {
    MaterialType.STONE_POWDER: '石粉',
    MaterialType.AGGREGATE_10MM: '10mm碎石',
    MaterialType.AGGREGATE_20MM: '20mm碎石',
}

# 骨料尺寸
MATERIAL_TYPE_SIZES = {
    MaterialType.STONE_POWDER: 6,      # 石粉较小
    MaterialType.AGGREGATE_10MM: 10,   # 10mm碎石
    MaterialType.AGGREGATE_20MM: 14,   # 20mm碎石较大
}


@dataclass
class Material:
    """物料类"""

    material_id: int
    position: Tuple[float, float]
    size: int = 10
    color: str = '#F39C12'
    current_conveyor: Optional[str] = None
    speed: float = 100  # 像素/秒
    distance_on_conveyor: float = 0  # 在当前皮带上的移动距离
    total_distance: float = 0  # 总移动距离
    is_in_hopper: bool = False
    is_in_silo: bool = False
    is_active: bool = True
    waiting_at_station: bool = False  # 是否在站台等待放料
    discharge_timer: float = 0  # 放料计时器
    animation_offset: float = 0  # 动画偏移量（用于堆状效果）

    # 物料特性
    material_type: str = 'stone_powder'  # 默认石粉
    material_name: str = '石粉'
    weight: float = 0.1

    def __post_init__(self):
        if isinstance(self.position[0], int):
            self.position = (float(self.position[0]), float(self.position[1]))

    def update_position(self, new_pos: Tuple[float, float]):
        """更新位置"""
        self.position = new_pos

    def move(self, dx: float, dy: float):
        """移动物料"""
        x, y = self.position
        self.position = (x + dx, y + dy)
        self.total_distance += abs(dx) + abs(dy)

    def move_to(self, x: float, y: float):
        """移动到指定位置"""
        dx = x - self.position[0]
        dy = y - self.position[1]
        self.position = (x, y)
        self.total_distance += abs(dx) + abs(dy)

    def enter_conveyor(self, conveyor_id: str, start_distance: float = 0):
        """进入皮带"""
        self.current_conveyor = conveyor_id
        self.distance_on_conveyor = start_distance
        self.is_in_hopper = False
        self.is_in_silo = False
        self.is_active = True

    def exit_conveyor(self):
        """离开皮带"""
        self.current_conveyor = None
        self.distance_on_conveyor = 0

    def enter_hopper(self):
        """进入中转斗"""
        self.is_in_hopper = True
        self.is_active = False
        self.current_conveyor = None

    def exit_hopper(self):
        """离开中转斗"""
        self.is_in_hopper = False
        self.is_in_silo = True
        self.is_active = True

    def enter_silo(self):
        """进入储料仓"""
        self.is_in_silo = True
        self.is_in_hopper = False
        self.is_active = False

    def get_info(self) -> dict:
        """获取物料信息"""
        return {
            'id': self.material_id,
            'position': self.position,
            'current_conveyor': self.current_conveyor,
            'is_in_hopper': self.is_in_hopper,
            'is_in_silo': self.is_in_silo,
            'is_active': self.is_active,
        }


class MaterialFactory:
    """物料工厂"""

    _next_id = 1

    @classmethod
    def create_material(cls, position: Tuple[float, float],
                       material_type: str = None) -> Material:
        """创建新物料"""
        if material_type is None:
            material_type = MaterialType.STONE_POWDER

        size = MATERIAL_TYPE_SIZES.get(material_type, 10)
        color = MATERIAL_TYPE_COLORS.get(material_type, '#F39C12')
        name = MATERIAL_TYPE_NAMES.get(material_type, '未知')

        material = Material(
            material_id=cls._next_id,
            position=position,
            size=size,
            color=color,
            material_type=material_type,
            material_name=name,
            weight=0.1,
            animation_offset=random.uniform(0, 2 * math.pi),  # 随机动画偏移
        )
        cls._next_id += 1
        return material

    @classmethod
    def create_stone_powder(cls, position: Tuple[float, float]) -> Material:
        """创建石粉物料"""
        return cls.create_material(position, MaterialType.STONE_POWDER)

    @classmethod
    def create_aggregate_10mm(cls, position: Tuple[float, float]) -> Material:
        """创建10mm碎石物料"""
        return cls.create_material(position, MaterialType.AGGREGATE_10MM)

    @classmethod
    def create_aggregate_20mm(cls, position: Tuple[float, float]) -> Material:
        """创建20mm碎石物料"""
        return cls.create_material(position, MaterialType.AGGREGATE_20MM)

    @classmethod
    def reset_id_counter(cls):
        """重置ID计数器"""
        cls._next_id = 1


@dataclass
class MaterialBatch:
    """物料批次"""
    batch_id: int
    materials: List[Material] = field(default_factory=list)
    spawn_time: int = 0  # 生成时间

    def add_material(self, material: Material):
        self.materials.append(material)

    def remove_material(self, material_id: int):
        self.materials = [m for m in self.materials if m.material_id != material_id]

    def get_count(self) -> int:
        return len(self.materials)

    def get_total_weight(self) -> float:
        return sum(m.weight for m in self.materials)
