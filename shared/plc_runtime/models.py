"""
PLC运行时模型 —— 皮带、传感器、中转斗、小仓的数据模型

零依赖设计：不依赖 PyQt5、config、pos 或任何上位机模块。
可直接翻译为 PLC 数据块（DB/Struct）。
"""
import math
import random
from dataclasses import dataclass, field
from typing import List, Optional

MATERIAL_WEIGHT = 0.1       # 每个物料重量（吨）
BATCHING_BIN_CAPACITY = 110.0  # 配料站小仓容量（吨）


class Conveyor:
    """皮带模型"""

    def __init__(self, conv_id: str, conv_config: dict):
        self.id = conv_id
        self.name = conv_config['name']
        self.length = conv_config['length']  # 米
        self.pixel_length = conv_config['pixel_length']  # 像素
        self.start_pos = conv_config['start_pos']
        self.end_pos = conv_config['end_pos']
        self.direction = conv_config.get('direction', 'forward')
        self.color = conv_config.get('color', '#FFFFFF')

        self.current_speed_pps = 0
        self.is_running = False
        self.materials_on_belt: List = []

    @property
    def current_speed(self) -> float:
        return self.current_speed_pps

    @property
    def is_vertical(self) -> bool:
        return self.start_pos[0] == self.end_pos[0]

    def start(self, speed_mps: float):
        self.current_speed_pps = speed_mps * (self.pixel_length / self.length if self.length > 0 else 1)
        self.is_running = True

    def stop(self):
        self.is_running = False
        self.current_speed_pps = 0

    def get_position_at_distance(self, pixel_distance: float) -> tuple:
        if self.pixel_length == 0:
            return self.start_pos
        t = min(pixel_distance / self.pixel_length, 1.0)
        x = self.start_pos[0] + (self.end_pos[0] - self.start_pos[0]) * t
        y = self.start_pos[1] + (self.end_pos[1] - self.start_pos[1]) * t
        return (x, y)

    def get_cart_stop_position(self, bin_id: str) -> tuple:
        parts = bin_id.split('-')
        if len(parts) != 2:
            return self.end_pos
        row_num = int(parts[1]) - 1
        conveyor_height = abs(self.end_pos[1] - self.start_pos[1])
        segment_height = conveyor_height / 7
        target_y = self.end_pos[1] + row_num * segment_height
        return (self.end_pos[0], target_y)

    def get_distance_for_bin(self, bin_id: str) -> float:
        parts = bin_id.split('-')
        if len(parts) == 2:
            row_num = int(parts[1]) - 1
            conveyor_height = abs(self.end_pos[1] - self.start_pos[1])
            segment_height = conveyor_height / 7
            stop_y = self.end_pos[1] + row_num * segment_height
            dx = self.end_pos[0] - self.start_pos[0]
            dy = stop_y - self.start_pos[1]
            return math.sqrt(dx * dx + dy * dy)
        if bin_id.startswith('S') and bin_id[1:].isdigit():
            return self.pixel_length
        return self.pixel_length


class _FallbackSensor:
    """传感器回退哨兵，始终返回未触发"""
    is_active = False


_FALLBACK_SENSOR = _FallbackSensor()


@dataclass
class Sensor:
    """接近开关传感器模型 — PLC 运行时基类"""
    sensor_id: str = ''
    name: str = ''
    position: tuple = (0, 0)
    conveyor: str = ''
    distance_from_start: int = 0
    is_active: bool = False
    real_state: bool = False
    trigger_count: int = 0
    last_trigger_time: int = 0
    hold_timer: int = 0

    @classmethod
    def from_config(cls, sensor_id: str, sensor_config: dict) -> 'Sensor':
        """从配置字典创建传感器"""
        if 'position' in sensor_config:
            pos = sensor_config['position']
        else:
            pos = (sensor_config['x'], sensor_config['y'])
        return cls(
            sensor_id=sensor_id,
            name=sensor_config['name'],
            position=pos,
            conveyor=sensor_config['conveyor'],
            distance_from_start=sensor_config.get('distance_from_start', 0),
        )

    def trigger(self, time_ms: int):
        if not self.real_state:
            self.real_state = True
            self.trigger_count += 1
            self.last_trigger_time = time_ms
            self.hold_timer = 200

    def update(self, delta_time: int):
        if self.hold_timer > 0:
            self.hold_timer -= delta_time
            if self.hold_timer <= 0:
                self.hold_timer = 0
                self.real_state = False

    def release(self):
        self.real_state = False
        self.hold_timer = 0


class TransferHopper:
    """中转斗模型"""

    def __init__(self, hopper_id: str, hopper_config: dict):
        self.id = hopper_id
        self.hopper_id = hopper_id
        self.name = hopper_config['name']
        self.position = hopper_config['position']
        self.width = hopper_config['width']
        self.height = hopper_config['height']
        self.input_conveyor = hopper_config['input_conveyor']
        self.output_conveyor = hopper_config['output_conveyor']

        self.capacity_tons = 8.5
        self.current_weight = 0.0
        self.fill_rate = 0.195

        self.is_open = True
        self._manual_switch_state = True
        self.weight = 0.0
        self.residual_weight = 0.0
        self.is_active = False

        self.switch_fault_mode = None
        self.weight_fault_mode = None
        self.weight_offset = 0.0
        self.belt_speed_multiplier = 1.0
        self.stored_materials = []

    @property
    def stored_count(self) -> int:
        return len(self.stored_materials)

    def capacity(self) -> float:
        return int(self.capacity_tons)

    @property
    def current_level(self) -> float:
        return int(self.current_weight)

    @property
    def level_percent(self) -> float:
        return (self.current_weight / self.capacity_tons) * 100

    @property
    def is_full(self) -> bool:
        return self.current_weight >= self.capacity_tons

    def get_display_weight(self) -> float:
        if self.weight_fault_mode == 'stuck_zero':
            return 0.0
        stored_weight = len(self.stored_materials) * MATERIAL_WEIGHT
        if self.weight_fault_mode == 'offset':
            return stored_weight * random.uniform(0.8, 1.2) + self.weight_offset
        return stored_weight

    def add_stored_weight(self, weight_tons: float):
        self.residual_weight += weight_tons

    def subtract_stored_weight(self, weight_tons: float):
        self.residual_weight = max(0, self.residual_weight - weight_tons)

    def get_stored_material_count(self) -> int:
        return len(self.stored_materials)

    def get_current_weight(self) -> float:
        return self.current_weight

    def get_effective_switch_state(self) -> bool:
        if self.switch_fault_mode == 'stuck_closed':
            return False
        elif self.switch_fault_mode == 'stuck_open':
            return True
        return self.is_open

    def get_display_switch_state(self) -> bool:
        return self.is_open

    def store_material(self, material, current_time: float):
        self.stored_materials.append({
            'material': material,
            'arrival_time': current_time
        })
        self.residual_weight += MATERIAL_WEIGHT
        self.current_weight = len(self.stored_materials) * MATERIAL_WEIGHT
        self.weight = self.current_weight
        self.is_active = True

    def can_release_material(self) -> bool:
        if not self.get_effective_switch_state():
            return False
        if self.current_weight <= 0 and len(self.stored_materials) == 0:
            return False
        return True

    def release_material(self):
        if not self.can_release_material():
            return None
        if len(self.stored_materials) == 0:
            return None
        stored = self.stored_materials.pop(0)
        material = stored['material']
        self.current_weight -= MATERIAL_WEIGHT
        self.current_weight = max(self.current_weight, 0)
        self.weight = self.current_weight

        if len(self.stored_materials) == 0:
            self.is_active = False
        return material

    def receive_material_direct(self):
        """物料直通（斗开关开时），不存储，直接通过"""
        self.is_active = True
        self.current_weight = max(0, self.current_weight - MATERIAL_WEIGHT)

    def send_material(self):
        """从中转斗释放一个物料到下一皮带"""
        if self.current_weight <= 0:
            return
        self.current_weight = max(0, self.current_weight - MATERIAL_WEIGHT)
        self.weight = self.current_weight
        if self.current_weight <= 0:
            self.is_active = False

    def calculate_residual_weight(self, conveyors, route_hoppers, route_conveyors, route_id=None):
        """计算清空阶段的斗内余料重量（calculate_residual_weight 别名）"""
        return self.get_residual_weight_for_clearing(
            conveyors, route_hoppers, route_conveyors, route_id)

    def get_residual_weight_for_clearing(self, conveyors, route_hoppers, route_conveyors, route_id=None):
        import pos
        hopper_id = self.hopper_id
        if route_id:
            key = (hopper_id, route_id)
            conveyor_ids = pos.CLEARING_ROUTE_CONVEYORS.get(key)
            if conveyor_ids:
                total_weight = 0.0
                for conv_id in conveyor_ids:
                    conv = conveyors.get(conv_id)
                    if conv and hasattr(conv, 'length'):
                        material_count = (conv.length / 2.5) * 2
                        total_weight += material_count * 0.1
                return total_weight
        if hopper_id not in route_hoppers:
            return 0.0
        hopper_idx = route_hoppers.index(hopper_id)
        if hopper_idx < len(route_conveyors):
            conv_id = route_conveyors[hopper_idx]
            conv = conveyors.get(conv_id)
            if conv and hasattr(conv, 'length'):
                total_length = conv.length
                material_count = (total_length / 2.5) * 2
                return material_count * 0.1
        return 0.0

    def reset(self):
        self.current_weight = 0.0
        self.weight = 0.0
        self.residual_weight = 0.0
        self.is_open = True
        self._manual_switch_state = True
        self.is_active = False
        self.stored_materials = []


class SmallBin:
    """高位配料站小仓模型"""

    def __init__(self, bin_id: str, bin_config: dict):
        self.id = bin_id
        self.name = bin_config['name']
        self.column = bin_config['column']
        self.row = bin_config['row']
        self.target_conveyor = bin_config['target_conveyor']
        self.capacity = bin_config.get('capacity', BATCHING_BIN_CAPACITY)
        self.current_level = 0.0
        self.consumption_rate = 0.01

    @property
    def level_percent(self) -> float:
        return (self.current_level / self.capacity) * 100 if self.capacity > 0 else 0

    @property
    def is_full(self) -> bool:
        return self.current_level >= self.capacity

    def receive_material(self, weight_tons: float = None) -> bool:
        if weight_tons is None:
            weight_tons = MATERIAL_WEIGHT
        new_level = self.current_level + weight_tons
        if new_level >= self.capacity:
            self.current_level = self.capacity
            return False
        self.current_level = new_level
        return True

    def reset(self):
        self.current_level = 0.0
        self.consumption_rate = 0.01
