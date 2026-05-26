"""
皮带模型 - Conveyor Model
"""

from enum import Enum
from typing import Tuple, Optional, List
from dataclasses import dataclass
import math
import config


class ConveyorState(Enum):
    """皮带状态"""
    STOPPED = 0
    RUNNING = 1
    FAULT = 2


@dataclass
class ConveyorSegment:
    """皮带线段"""
    start_pos: Tuple[int, int]
    end_pos: Tuple[int, int]
    color: str


class Conveyor:
    """皮带类
    
    重要：所有皮带的移动速度统一使用像素/秒作为标准单位，
    确保物料在不同皮带上以一致的视觉速度移动。
    """

    # 类级别的统一像素/米转换系数（所有皮带共用）
    _unified_pixel_per_meter = 10.0

    @classmethod
    def set_unified_pixel_per_meter(cls, value: float):
        """设置统一的像素/米转换系数"""
        cls._unified_pixel_per_meter = value

    def __init__(self, conveyor_id: str, config_data: dict):
        self.id = conveyor_id
        self.name = config_data['name']
        self.length = config_data['length']  # 配置的长度（米）
        self.base_speed = config_data['speed']  # 配置的基础速度（米/秒）
        self.start_pos = config_data['start_pos']
        self.end_pos = config_data['end_pos']
        self.color = config_data['color']
        self.is_vertical = config_data.get('vertical', False)

        # 计算像素长度（用于统一移动速度）
        self.pixel_length = math.sqrt(
            (self.end_pos[0] - self.start_pos[0])**2 + 
            (self.end_pos[1] - self.start_pos[1])**2
        )
        
        # 当前速度（像素/秒）- 统一使用像素/秒
        self.current_speed_pps = 0

        self.state = ConveyorState.STOPPED
        self.fault_reason = None
        self.running_time = 0  # 累计运行时间(秒)
        self.materials_passed = 0  # 经过的物料数量

    @property
    def current_speed(self) -> float:
        """返回米/秒速度（兼容性）"""
        return self.current_speed_pps

    @property
    def is_running(self) -> bool:
        return self.state == ConveyorState.RUNNING

    @property
    def is_stopped(self) -> bool:
        return self.state == ConveyorState.STOPPED

    @property
    def is_fault(self) -> bool:
        return self.state == ConveyorState.FAULT

    def start(self, speed: float = None) -> bool:
        """启动皮带

        Args:
            speed: 皮带速度（米/秒）。如果为None，使用base_speed
        """
        if self.state == ConveyorState.FAULT:
            return False
        self.state = ConveyorState.RUNNING

        # 使用统一的像素/米转换系数
        target_speed = speed if speed is not None else self.base_speed
        self.current_speed_pps = target_speed * self._unified_pixel_per_meter
        return True

    def stop(self):
        """停止皮带"""
        self.state = ConveyorState.STOPPED
        self.current_speed_pps = 0

    def set_fault(self, reason: str = None):
        """设置故障"""
        self.state = ConveyorState.FAULT
        self.fault_reason = reason
        self.current_speed_pps = 0

    def clear_fault(self):
        """清除故障"""
        self.state = ConveyorState.STOPPED
        self.fault_reason = None

    def update(self, delta_time: float, speed_multiplier: float):
        """更新皮带状态"""
        if self.state == ConveyorState.RUNNING:
            self.current_speed_pps = self.base_speed * speed_multiplier * self._unified_pixel_per_meter
            self.running_time += delta_time

    def get_animation_offset(self, time_ms: int) -> float:
        """获取动画偏移量"""
        if not self.is_running:
            return 0
        return (time_ms / 50) % 20

    def get_segments(self) -> List[ConveyorSegment]:
        """获取皮带线段"""
        return [ConveyorSegment(self.start_pos, self.end_pos, self.color)]

    def get_center_pos(self) -> Tuple[int, int]:
        """获取皮带中心位置"""
        x = (self.start_pos[0] + self.end_pos[0]) // 2
        y = (self.start_pos[1] + self.end_pos[1]) // 2
        return (x, y)

    def get_length_pixels(self) -> float:
        """获取皮带像素长度"""
        return self.pixel_length

    def get_position_at_distance(self, pixel_distance: float) -> Tuple[int, int]:
        """根据像素距离获取位置（统一使用像素）"""
        total_length = self.pixel_length
        if total_length == 0:
            return self.start_pos

        ratio = min(pixel_distance / total_length, 1.0)
        x = int(self.start_pos[0] + (self.end_pos[0] - self.start_pos[0]) * ratio)
        y = int(self.start_pos[1] + (self.end_pos[1] - self.start_pos[1]) * ratio)
        return (x, y)

    def get_distance_for_bin(self, bin_id: str) -> float:
        """获取指定小仓在皮带上的像素距离"""
        from views.main_window import BinPositionManager
        pos = BinPositionManager.get_bin_position(bin_id)
        if pos:
            bin_x, bin_y = pos
            dx = bin_x - self.start_pos[0]
            dy = bin_y - self.start_pos[1]
            return math.sqrt(dx * dx + dy * dy)
        return self.pixel_length

    def is_position_on_conveyor(self, pos: Tuple[int, int], threshold: int = 20) -> bool:
        """检查位置是否在皮带上"""
        x1, y1 = self.start_pos
        x2, y2 = self.end_pos
        x, y = pos

        dx = x2 - x1
        dy = y2 - y1

        if dx == 0 and dy == 0:
            return abs(x - x1) <= threshold and abs(y - y1) <= threshold

        t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy

        distance = math.sqrt((x - proj_x) ** 2 + (y - proj_y) ** 2)
        return distance <= threshold

    def get_distance_to_end(self, pos: Tuple[int, int]) -> float:
        """获取位置到皮带末端的像素距离"""
        x1, y1 = self.start_pos
        x2, y2 = self.end_pos
        x, y = pos

        dx = x2 - x1
        dy = y2 - y1

        if dx == 0 and dy == 0:
            return math.sqrt((x - x1) ** 2 + (y - y1) ** 2)

        t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
        proj_x = x1 + t * dx
        proj_y = y1 + t * dy

        return math.sqrt((x - proj_x) ** 2 + (y - proj_y) ** 2)

    def get_info(self) -> dict:
        """获取皮带信息"""
        return {
            'id': self.id,
            'name': self.name,
            'state': self.state.name,
            'speed': self.current_speed_pps,
            'speed_mps': self.current_speed_pps / (self.pixel_length / self.length) if self.pixel_length > 0 and self.length > 0 else 0,
            'running_time': self.running_time,
            'materials_passed': self.materials_passed,
            'fault_reason': self.fault_reason,
        }
