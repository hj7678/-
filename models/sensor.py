"""
传感器模型 — 继承 shared/plc_runtime/models.py Sensor，扩展 HMI 仿真字段
"""
from enum import Enum
from typing import Tuple, Optional
from dataclasses import dataclass, field
import config
from shared.plc_runtime.models import Sensor as BaseSensor


class SensorState(Enum):
    OFF = 0
    ON = 1


@dataclass
class Sensor(BaseSensor):
    """HMI 仿真传感器 — 继承 PLC 运行时基类，扩展触发距离和状态枚举"""

    trigger_distance: int = 30
    state: SensorState = SensorState.OFF
    off_delay_timer: int = 0

    def __post_init__(self):
        if isinstance(self.position, tuple) and len(self.position) == 2:
            if isinstance(self.position[0], float):
                self.position = (int(self.position[0]), int(self.position[1]))

    @property
    def is_active(self) -> bool:
        return self.state == SensorState.ON

    def trigger(self, current_time: int):
        if self.state == SensorState.OFF:
            self.state = SensorState.ON
            self.last_trigger_time = current_time
            self.trigger_count += 1
            self.off_delay_timer = 500
            return True
        else:
            self.off_delay_timer = 500
            return False

    def update(self, delta_time: int):
        if self.state == SensorState.ON:
            self.off_delay_timer -= delta_time
            if self.off_delay_timer <= 0:
                self.state = SensorState.OFF
                self.off_delay_timer = 0

    def reset(self):
        self.state = SensorState.OFF
        self.trigger_count = 0
        self.last_trigger_time = 0
        self.off_delay_timer = 0

    def check_material_in_range(self, material_pos: Tuple[int, int]) -> bool:
        import math
        dx = material_pos[0] - self.position[0]
        dy = material_pos[1] - self.position[1]
        distance = math.sqrt(dx * dx + dy * dy)
        return distance <= self.trigger_distance

    def get_info(self) -> dict:
        return {
            'id': self.sensor_id,
            'name': self.name,
            'state': self.state.name,
            'trigger_count': self.trigger_count,
            'position': self.position,
        }

    @classmethod
    def from_config(cls, sensor_id: str, config_data: dict) -> 'Sensor':
        return cls(
            sensor_id=sensor_id,
            name=config_data['name'],
            position=(config_data['x'], config_data['y']),
            conveyor=config_data['conveyor'],
            trigger_distance=30,
        )


@dataclass
class SensorEvent:
    timestamp: int
    sensor_id: str
    event_type: str
    material_id: Optional[int] = None