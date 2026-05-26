"""
高位储料仓模型 - High Silo Model
"""

from dataclasses import dataclass
from typing import Tuple
import config


@dataclass
class HighSilo:
    """高位储料仓类"""

    name: str = '高位储料仓'
    position: Tuple[int, int] = (420, 450)
    width: int = 160
    height: int = 100
    max_capacity: float = config.HIGH_SILO_BIN_CAPACITY  # 110吨

    current_level: float = 0.0  # 当前料位（吨）
    total_received: float = 0.0  # 累计接收（吨）

    is_full: bool = False
    is_overflow: bool = False

    # 报警状态
    warning_level: int = 80  # 警告料位(%)
    critical_level: int = 95  # 临界料位(%)

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

    @property
    def is_warning(self) -> bool:
        """是否处于警告状态"""
        return self.level_percent >= self.warning_level

    @property
    def is_critical(self) -> bool:
        """是否处于临界状态"""
        return self.level_percent >= self.critical_level

    def receive_material(self, count: int = 1) -> bool:
        """接收物料"""
        if self.current_level + count > self.max_capacity:
            self.is_overflow = True
            return False

        self.current_level += count
        self.total_received += count

        if self.current_level >= self.max_capacity:
            self.is_full = True

        return True

    def remove_material(self, count: int = 1) -> bool:
        """移除物料（模拟取料）"""
        if self.current_level < count:
            return False
        self.current_level -= count
        self.is_full = False
        self.is_overflow = False
        return True

    def can_receive(self) -> bool:
        """是否可以接收物料"""
        return self.current_level < self.max_capacity

    def reset(self):
        """重置储料仓"""
        self.current_level = 0
        self.total_received = 0
        self.is_full = False
        self.is_overflow = False

    def get_level_position(self) -> Tuple[int, int]:
        """获取料位显示位置"""
        x = self.position[0] + self.width // 2
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
        """检查点是否在仓内"""
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
            'is_full': self.is_full,
            'is_overflow': self.is_overflow,
            'is_warning': self.is_warning,
            'is_critical': self.is_critical,
        }

    @classmethod
    def from_config(cls) -> 'HighSilo':
        """从配置创建"""
        cfg = config.HIGH_SILO
        return cls(
            name=cfg['name'],
            position=tuple(cfg['position']),
            width=cfg['width'],
            height=cfg['height'],
            max_capacity=cfg['max_capacity'],
        )
