"""
传感器模型 - Sensor Model
"""

from enum import Enum
from typing import Tuple, Optional
from dataclasses import dataclass, field
import config


class SensorState(Enum):
    """传感器状态"""
    OFF = 0
    ON = 1


@dataclass
class Sensor:
    """接近开关传感器类"""

    sensor_id: str
    name: str
    position: Tuple[int, int]  # 传感器位置
    conveyor: str  # 所属皮带
    trigger_distance: int  # 触发距离

    state: SensorState = SensorState.OFF
    trigger_count: int = 0  # 触发次数
    last_trigger_time: int = 0  # 上次触发时间(ms)
    off_delay_timer: int = 0  # 关闭延迟计时器

    def __post_init__(self):
        # 支持从config字典直接创建
        if isinstance(self.position, tuple) and len(self.position) == 2:
            if isinstance(self.position[0], float):
                self.position = (int(self.position[0]), int(self.position[1]))
        # 兼容旧字段名
        if hasattr(self, 'conveyor_id') and not hasattr(self, 'conveyor'):
            self.conveyor = self.conveyor_id

    @property
    def is_active(self) -> bool:
        return self.state == SensorState.ON

    def trigger(self, current_time: int):
        """触发传感器"""
        if self.state == SensorState.OFF:
            self.state = SensorState.ON
            self.last_trigger_time = current_time
            self.trigger_count += 1
            self.off_delay_timer = 500  # 默认500ms延迟
            return True
        else:
            self.off_delay_timer = 500  # 重新触发时重置延迟
            return False

    def update(self, delta_time: int):
        """更新传感器状态"""
        if self.state == SensorState.ON:
            self.off_delay_timer -= delta_time
            if self.off_delay_timer <= 0:
                self.state = SensorState.OFF
                self.off_delay_timer = 0

    def reset(self):
        """重置传感器"""
        self.state = SensorState.OFF
        self.trigger_count = 0
        self.last_trigger_time = 0
        self.off_delay_timer = 0

    def check_material_in_range(self, material_pos: Tuple[int, int]) -> bool:
        """检查物料是否在传感器范围内"""
        import math
        dx = material_pos[0] - self.position[0]
        dy = material_pos[1] - self.position[1]
        distance = math.sqrt(dx * dx + dy * dy)
        return distance <= self.trigger_distance

    def get_info(self) -> dict:
        """获取传感器信息"""
        return {
            'id': self.sensor_id,
            'name': self.name,
            'state': self.state.name,
            'trigger_count': self.trigger_count,
            'position': self.position,
        }

    @classmethod
    def from_config(cls, sensor_id: str, config_data: dict) -> 'Sensor':
        """从配置创建传感器"""
        return cls(
            sensor_id=sensor_id,
            name=config_data['name'],
            position=(config_data['x'], config_data['y']),
            conveyor=config_data['conveyor'],
            trigger_distance=30,  # 默认触发距离30像素
        )


@dataclass
class SensorEvent:
    """传感器事件"""
    timestamp: int  # 时间戳(ms)
    sensor_id: str
    event_type: str  # 'TRIGGER' or 'RELEASE'
    material_id: Optional[int] = None
