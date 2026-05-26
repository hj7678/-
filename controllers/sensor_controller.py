"""
传感器控制器 - Sensor Controller
管理传感器检测逻辑和事件
"""

from typing import Dict, List, Callable, Optional
from dataclasses import dataclass
import config
from models.sensor import Sensor, SensorEvent, SensorState


@dataclass
class SensorEventHandler:
    """传感器事件处理器"""
    on_trigger: Optional[Callable] = None
    on_release: Optional[Callable] = None


class SensorController:
    """传感器控制器"""

    def __init__(self):
        self.sensors: Dict[str, Sensor] = {}
        self.event_handlers: Dict[str, SensorEventHandler] = {}
        self.event_history: List[SensorEvent] = []
        self._init_sensors()

    def _init_sensors(self):
        """初始化传感器"""
        for sensor_id, sensor_config in config.SENSORS.items():
            sensor = Sensor.from_config(sensor_id, sensor_config)
            self.sensors[sensor_id] = sensor
            self.event_handlers[sensor_id] = SensorEventHandler()

    def register_trigger_handler(self, sensor_id: str, handler: Callable):
        """注册传感器触发处理器"""
        if sensor_id in self.event_handlers:
            self.event_handlers[sensor_id].on_trigger = handler

    def register_release_handler(self, sensor_id: str, handler: Callable):
        """注册传感器释放处理器"""
        if sensor_id in self.event_handlers:
            self.event_handlers[sensor_id].on_release = handler

    def check_material_proximity(self, material, current_time: int):
        """检查物料是否接近传感器"""
        for sensor_id, sensor in self.sensors.items():
            if sensor.check_material_in_range((material.position[0], material.position[1])):
                # 物料进入传感器范围
                was_active = sensor.is_active
                sensor.trigger(current_time)

                # 如果是从非激活变为激活，触发事件
                if not was_active and sensor.is_active:
                    self._handle_trigger_event(sensor_id, current_time, material)

    def _handle_trigger_event(self, sensor_id: str, current_time: int, material):
        """处理传感器触发事件"""
        # 创建事件记录
        event = SensorEvent(
            timestamp=current_time,
            sensor_id=sensor_id,
            event_type='TRIGGER',
            material_id=material.material_id if material else None
        )
        self.event_history.append(event)

        # 调用处理器
        handler = self.event_handlers.get(sensor_id)
        if handler and handler.on_trigger:
            handler.on_trigger(sensor_id, material)

    def update(self, delta_time: int):
        """更新所有传感器状态"""
        for sensor in self.sensors.values():
            sensor.update(delta_time)

    def reset(self):
        """重置所有传感器"""
        for sensor in self.sensors.values():
            sensor.reset()
        self.event_history.clear()

    def get_sensor(self, sensor_id: str) -> Sensor:
        """获取传感器"""
        return self.sensors.get(sensor_id)

    def get_all_events(self) -> List[SensorEvent]:
        """获取所有事件"""
        return self.event_history

    def get_recent_events(self, count: int = 10) -> List[SensorEvent]:
        """获取最近的事件"""
        return self.event_history[-count:]

    def get_total_trigger_count(self) -> int:
        """获取总触发次数"""
        return sum(s.count for s in self.sensors.values())

    def get_sensor_status(self) -> Dict:
        """获取传感器状态摘要"""
        return {
            sensor_id: {
                'state': sensor.state.name,
                'trigger_count': sensor.trigger_count,
                'is_active': sensor.is_active
            }
            for sensor_id, sensor in self.sensors.items()
        }
