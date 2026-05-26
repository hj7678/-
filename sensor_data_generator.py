"""
传感器数据生成器 - Sensor Data Generator
根据仿真状态生成模拟的传感器数据，写入JSON文件

功能：
1. 根据皮带上物料位置，生成接近开关传感器信号
2. 根据中转斗状态，生成开关和称重数据
3. 支持故障注入（通过SensorDataManager）
4. 作为仿真软件与传感器数据文件的桥梁
"""

import time
import random
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass

import config
from sensor_data_manager import SensorDataManager, FaultMode, get_data_manager


@dataclass
class ConveyorSensorState:
    """皮带传感器状态"""
    conveyor_id: str
    sensor_ids: List[str]  # 该皮带上的传感器ID列表
    sensor_distances: Dict[str, float]  # 传感器到皮带起点的距离


class SensorDataGenerator:
    """
    传感器数据生成器
    
    根据仿真状态生成传感器数据：
    1. 接近开关：根据物料位置判断是否触发
    2. 中转斗开关：直接读取中转斗状态
    3. 称重传感器：直接读取中转斗重量
    
    故障处理：
    - 接近开关故障：通过 SensorDataManager 的故障注入接口模拟
    - 中转斗故障：通过 TransferHopper 的故障模式属性模拟
    """
    
    def __init__(self, data_manager: SensorDataManager = None):
        self.data_manager = data_manager or get_data_manager()
        
        # 故障诊断系统引用（用于生成包含故障的数据）
        self._fault_diagnosis = None
        
        # 构建皮带与传感器的映射
        self._conveyor_sensors: Dict[str, ConveyorSensorState] = {}
        self._sensor_to_conveyor: Dict[str, str] = {}
        self._build_conveyor_sensor_mapping()
    
    def set_fault_diagnosis(self, fault_diagnosis):
        """设置故障诊断系统引用"""
        self._fault_diagnosis = fault_diagnosis
    
    def _build_conveyor_sensor_mapping(self):
        """构建皮带与传感器的映射关系"""
        for sensor_id, sensor_config in config.SENSORS.items():
            conveyor_id = sensor_config.get('conveyor', sensor_id)
            distance = sensor_config.get('distance_from_start', 0)
            
            if conveyor_id not in self._conveyor_sensors:
                self._conveyor_sensors[conveyor_id] = ConveyorSensorState(
                    conveyor_id=conveyor_id,
                    sensor_ids=[],
                    sensor_distances={}
                )
            
            self._conveyor_sensors[conveyor_id].sensor_ids.append(sensor_id)
            self._conveyor_sensors[conveyor_id].sensor_distances[sensor_id] = distance
            self._sensor_to_conveyor[sensor_id] = conveyor_id
    
    def generate_sensor_data(self,
                           materials: List[Any],
                           hoppers: Dict[str, Any],
                           conveyors: Dict[str, Any],
                           active_routes: Set[str] = None):
        """
        生成传感器数据

        Args:
            materials: 当前活跃物料列表
            hoppers: 中转斗字典
            conveyors: 皮带字典
            active_routes: 活跃路线集合
        """
        # 生成接近开关传感器数据
        self._generate_proximity_sensor_data(materials, conveyors, active_routes)

        # 生成中转斗数据
        self._generate_hopper_data(hoppers)

        # 生成皮带转速传感器数据
        self._generate_conveyor_speed_data(conveyors)

    def _generate_conveyor_speed_data(self, conveyors: Dict[str, Any]):
        """生成皮带转速传感器数据（sint类型）

        转速规则：
        - 正常运行转速: SPEED_NORMAL_VALUE (500)
        - 异常转速: 低于 SPEED_ABNORMAL_THRESHOLD (450)
        - 停止时转速: 0
        """
        for conv_id, conveyor in conveyors.items():
            speed_sensor_id = config.CONVEYOR_SPEED_SENSORS.get(conv_id)
            if not speed_sensor_id:
                continue

            # 根据皮带是否运行确定转速
            if conveyor.is_running:
                # 正常运行转速 = 配置的正常转速值
                speed = config.SPEED_NORMAL_VALUE
                # 添加小波动模拟真实传感器（±5的波动）
                speed += random.randint(-5, 5)
            else:
                # 皮带停止时转速为0
                speed = 0

            # 写入传感器数据（会应用故障）
            self.data_manager.write_conveyor_speed(speed_sensor_id, speed)
    
    def _generate_proximity_sensor_data(self,
                                       materials: List[Any],
                                       conveyors: Dict[str, Any],
                                       active_routes: Set[str] = None):
        """
        生成接近开关传感器数据
        
        逻辑：
        - 遍历所有物料
        - 如果物料在皮带上且皮带在运行中
        - 检查物料位置是否在传感器触发范围内（±2米）
        - 应用故障模拟
        """
        # 初始化所有传感器为False
        all_sensors = list(config.SENSORS.keys())
        sensor_values: Dict[str, bool] = {sid: False for sid in all_sensors}
        
        # 根据物料位置计算传感器状态
        for material in materials:
            if not material.is_active:
                continue
            
            conveyor_id = material.current_conveyor
            if not conveyor_id:
                continue
            
            conveyor = conveyors.get(conveyor_id)
            if not conveyor or not conveyor.is_running:
                continue
            
            # 获取该皮带上的传感器
            conv_sensors = self._conveyor_sensors.get(conveyor_id)
            if not conv_sensors:
                continue
            
            material_distance = material.distance_on_conveyor
            
            # 检查每个传感器
            for sensor_id in conv_sensors.sensor_ids:
                sensor_distance = conv_sensors.sensor_distances[sensor_id]
                # 物料在传感器位置±2米范围内触发
                if abs(material_distance - sensor_distance) < 2:
                    sensor_values[sensor_id] = True
        
        # 应用故障模拟
        final_values = self._apply_sensor_faults(sensor_values)
        
        # 写入数据
        self.data_manager.write_all_sensors(final_values)
    
    def _apply_sensor_faults(self, sensor_values: Dict[str, bool]) -> Dict[str, bool]:
        """应用传感器故障"""
        final_values = sensor_values.copy()
        
        if self._fault_diagnosis:
            for sensor_id, original_value in sensor_values.items():
                # 使用故障诊断系统计算故障状态
                simulated_value = self._fault_diagnosis.update_sensor_state(
                    sensor_id, original_value, 0.05
                )
                final_values[sensor_id] = simulated_value
        
        return final_values
    
    def _generate_hopper_data(self, hoppers: Dict[str, Any]):
        """
        生成中转斗数据
        
        逻辑：
        - 开关状态：使用get_effective_switch_state()获取考虑故障后的实际状态
        - 称重数据：使用get_display_weight()获取考虑故障后的显示称重值
        """
        for hopper_id, hopper in hoppers.items():
            # 写入开关状态（使用实际生效状态，考虑故障）
            switch_value = hopper.get_effective_switch_state()
            self.data_manager.write_hopper_switch(hopper_id, switch_value)
            
            # 写入称重数据（吨）
            weight_value = hopper.get_display_weight()
            self.data_manager.write_hopper_weight(hopper_id, weight_value)
    
    def update_single_sensor(self, sensor_id: str, value: bool):
        """更新单个传感器数据"""
        self.data_manager.write_sensor(sensor_id, value)
    
    def update_hopper_switch(self, hopper_id: str, value: bool):
        """更新中转斗开关状态"""
        self.data_manager.write_hopper_switch(hopper_id, value)
    
    def update_hopper_weight(self, hopper_id: str, value: float):
        """更新中转斗称重数据"""
        self.data_manager.write_hopper_weight(hopper_id, value)
    
    def inject_sensor_fault(self, sensor_id: str, fault_mode: FaultMode, 
                           duration: float = -1.0, probability: float = 1.0):
        """注入传感器故障"""
        self.data_manager.inject_sensor_fault(sensor_id, fault_mode, duration, probability)
    
    def inject_hopper_switch_fault(self, hopper_id: str, stuck_closed: bool = True,
                                   duration: float = -1.0):
        """
        注入中转斗开关故障
        
        Args:
            hopper_id: 中转斗ID
            stuck_closed: True=卡在关, False=卡在开
            duration: 故障持续时间
        """
        fault_mode = FaultMode.STUCK_LOW if stuck_closed else FaultMode.STUCK_HIGH
        self.data_manager.inject_hopper_switch_fault(hopper_id, fault_mode, duration)
    
    def inject_hopper_weight_fault(self, hopper_id: str, stuck_zero: bool = True,
                                   offset: float = 0.0, duration: float = -1.0):
        """
        注入中转斗称重故障
        
        Args:
            hopper_id: 中转斗ID
            stuck_zero: True=显示0, False=偏移
            offset: 偏移量
            duration: 故障持续时间
        """
        fault_mode = FaultMode.STUCK_LOW if stuck_zero else FaultMode.SENSITIVITY_LOSS
        self.data_manager.inject_hopper_weight_fault(hopper_id, fault_mode, offset, duration)
    
    def clear_all_faults(self):
        """清除所有故障"""
        self.data_manager.clear_all_faults()
    
    def get_fault_status(self) -> Dict[str, Any]:
        """获取故障状态"""
        return self.data_manager.get_fault_status()
    
    def get_data_file_path(self) -> str:
        """获取数据文件路径"""
        return self.data_manager.get_data_file_path()


# 全局单例
_generator_instance: Optional[SensorDataGenerator] = None


def get_data_generator(data_manager: SensorDataManager = None) -> SensorDataGenerator:
    """获取传感器数据生成器单例"""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = SensorDataGenerator(data_manager)
    return _generator_instance


def reset_generator():
    """重置生成器单例"""
    global _generator_instance
    _generator_instance = None
