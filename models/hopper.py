"""
中转斗模型 - Transfer Hopper Model
"""

from dataclasses import dataclass
from typing import List, Tuple
import config


@dataclass
class TransferHopper:
    """中转斗类"""

    hopper_id: str = ''  # 中转斗ID，用于匹配route_hoppers配置
    name: str = '中转斗'
    position: Tuple[int, int] = (420, 320)
    width: int = 160
    height: int = 80
    max_capacity: int = 20

    current_level: int = 0  # 当前物料数量
    total_received: int = 0  # 累计接收物料数
    total_sent: int = 0  # 累计发送物料数

    is_full: bool = False
    is_overflow: bool = False

    def __post_init__(self):
        if isinstance(self.position, tuple) and len(self.position) == 2:
            if isinstance(self.position[0], float):
                self.position = (int(self.position[0]), int(self.position[1]))

    @property
    def level_percent(self) -> float:
        """料位百分比"""
        return (self.current_level / self.max_capacity) * 100

    @property
    def fill_percent(self) -> float:
        """填充百分比"""
        return self.level_percent

    def receive_material(self, count: int = 1) -> bool:
        """接收物料"""
        if self.current_level + count > self.max_capacity:
            self.is_overflow = True
            # 仍然接收，但不增加更多
            return False

        self.current_level += count
        self.total_received += count

        if self.current_level >= self.max_capacity:
            self.is_full = True

        return True

    def send_material(self, count: int = 1) -> bool:
        """发送物料"""
        if self.current_level < count:
            return False

        self.current_level -= count
        self.total_sent += count
        self.is_full = False
        self.is_overflow = False
        return True

    def can_receive(self) -> bool:
        """是否可以接收物料"""
        return self.current_level < self.max_capacity

    def should_drain(self) -> bool:
        """是否应该排空"""
        return self.current_level >= self.max_capacity * 0.8

    def reset(self):
        """重置中转斗"""
        self.current_level = 0
        self.total_received = 0
        self.total_sent = 0
        self.is_full = False
        self.is_overflow = False

    def get_level_position(self) -> Tuple[int, int]:
        """获取料位显示位置"""
        x = self.position[0] + self.width // 2
        # 料位从底部向上增加
        level_height = int((self.height - 10) * self.level_percent / 100)
        y = self.position[1] + self.height - 5 - level_height
        return (x, y)

    def get_center_position(self) -> Tuple[int, int]:
        """获取中心位置"""
        return (
            self.position[0] + self.width // 2,
            self.position[1] + self.height // 2
        )

    def is_point_inside(self, pos: Tuple[int, int]) -> bool:
        """检查点是否在斗内"""
        x, y = pos
        px, py = self.position
        return (px <= x <= px + self.width and
                py <= y <= py + self.height)

    def get_info(self) -> dict:
        """获取信息"""
        return {
            'name': self.name,
            'level': self.current_level,
            'max_capacity': self.max_capacity,
            'level_percent': self.level_percent,
            'total_received': self.total_received,
            'total_sent': self.total_sent,
            'is_full': self.is_full,
            'is_overflow': self.is_overflow,
        }

    @classmethod
    def from_config(cls, hopper_id: str = None) -> 'TransferHopper':
        """从配置创建"""
        cfg = config.TRANSFER_HOPPERS.get(hopper_id, {})
        return cls(
            hopper_id=hopper_id,
            name=cfg.get('name', '中转斗'),
            position=cfg.get('position', (420, 320)),
            width=cfg.get('width', 50),
            height=cfg.get('height', 35),
            max_capacity=cfg.get('capacity', 20),
        )

    def calculate_residual_weight(self, conveyors: dict, route_hoppers: list, route_conveyors: list, route_id: str = None) -> float:
        """计算该中转斗在CLEARING状态下的余料称重

        Args:
            conveyors: 皮带字典 {conv_id: Conveyor对象}
            route_hoppers: 路线的所有中转斗列表，如 [None, 'hopper1', 'hopper3', 'hopper4', None]
            route_conveyors: 路线的所有皮带列表，如 ['E5', 'E8', 'E10', 'D7']
            route_id: 路线ID，用于从 CLEARING_ROUTE_CONVEYORS 获取皮带对应关系

        Returns:
            余料重量（吨）

        规则：
        - 如果 CLEARING_ROUTE_CONVEYORS 中有该(中转斗,路线)组合的配置，累加所有皮带
        - 否则使用原来的逻辑：只计算当前中转斗对应的一段皮带
        """
        import pos
        hopper_id = self.hopper_id

        # 尝试从 CLEARING_ROUTE_CONVEYORS 获取多皮带配置（仅清空余料模式）
        if route_id:
            key = (hopper_id, route_id)
            conveyor_ids = pos.CLEARING_ROUTE_CONVEYORS.get(key)
            if conveyor_ids:
                total_weight = 0.0
                for conv_id in conveyor_ids:
                    conv = conveyors.get(conv_id)
                    if conv and hasattr(conv, 'length'):
                        # 计算余料物料数量：皮带长度 / 2.5 × 2（每秒2个物料）
                        material_count = (conv.length / 2.5) * 2
                        total_weight += material_count * 0.1
                return total_weight

        # 回退：使用原来的单皮带逻辑
        if hopper_id not in route_hoppers:
            return 0.0

        hopper_idx = route_hoppers.index(hopper_id)

        if hopper_idx < len(route_conveyors):
            conv_id = route_conveyors[hopper_idx]
            conv = conveyors.get(conv_id)
            if conv and hasattr(conv, 'length'):
                total_length = conv.length
                # 计算余料物料数量：皮带长度 / 2.5 × 2（每秒2个物料）
                material_count = (total_length / 2.5) * 2
                # 每个物料0.1吨
                return material_count * 0.1

        return 0.0
