"""
传感器数据管理器 - Sensor Data Manager
负责从JSON文件读取/写入传感器数据，模拟实际传感器数据采集

功能：
1. 读取传感器数据（模拟从PLC/传感器采集）
2. 写入传感器数据（模拟数据采集过程）
3. 提供故障注入接口（模拟传感器故障）
4. 支持两种模式：仿真模式（内部生成数据）、真实模式（从JSON读取）
5. 生成 generate_data.json 用于PLC读取的传感器数据
"""

import json
import os
import random
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, field
import threading

import config

# 生成数据文件路径（供PLC读取）
GENERATE_DATA_FILE = os.path.join(config.DATA_DIR, 'generate_data.json')


def get_beijing_time() -> float:
    """获取北京时间的时间戳（Unix时间戳）

    北京时间 = UTC+8
    返回自1970年1月1日以来的秒数（UTC）
    """
    beijing_tz = timezone(timedelta(hours=8))
    beijing_time = datetime.now(beijing_tz)
    return beijing_time.timestamp()


def get_beijing_time_str() -> str:
    """获取北京时间的格式化字符串

    返回格式: "2026-05-06 16:45:30.123456"（精确到微秒）
    """
    beijing_tz = timezone(timedelta(hours=8))
    beijing_time = datetime.now(beijing_tz)
    return beijing_time.strftime("%Y-%m-%d %H:%M:%S.%f")


class FaultMode(Enum):
    """故障模式"""
    NORMAL = "normal"
    STUCK_LOW = "stuck_low"       # 一直为0
    STUCK_HIGH = "stuck_high"     # 一直为1
    RANDOM = "random"             # 随机0/1
    SENSITIVITY_LOSS = "sensitivity_loss"  # 灵敏度降低
    INTERMITTENT = "intermittent"  # 间歇性故障
    # 小车位置传感器专用故障模式
    POSITION_STUCK = "position_stuck"      # 位置卡死不变（定位彻底失效）
    POSITION_OFFSET = "position_offset"    # 定位不准（偏移±1）


@dataclass
class SensorFaultConfig:
    """传感器故障配置"""
    sensor_id: str
    fault_mode: FaultMode = FaultMode.NORMAL
    fault_start_time: float = 0.0
    fault_duration: float = -1.0  # -1表示持续故障
    probability: float = 1.0  # 故障发生概率


@dataclass
class SensorReading:
    """传感器读数"""
    sensor_id: str
    value: Any  # bool 或 float
    unit: str
    timestamp: float
    is_simulated: bool = False  # 是否是模拟数据


class SensorDataManager:
    """
    传感器数据管理器
    
    工作模式：
    1. 仿真模式：内部生成模拟数据，写入JSON文件
    2. 监听模式：从JSON文件读取数据（由外部写入）
    
    数据流程：
    - 仿真模式：SimulationController -> SensorDataManager.generate_data() -> JSON文件
    - 监听模式：JSON文件(外部写入) -> SensorDataManager.read_data() -> SimulationController
    """
    
    def __init__(self, data_file: str = None):
        if data_file is None:
            # 默认使用 generate_data.json 作为数据文件
            data_file = GENERATE_DATA_FILE
        
        self.data_file = data_file
        self._lock = threading.RLock()  # 使用可重入锁避免死锁
        
        # 确保data目录存在
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        
        # 当前传感器数据缓存
        self._current_data: Dict[str, Any] = {}
        
        # 故障配置
        self._sensor_faults: Dict[str, SensorFaultConfig] = {}
        self._hopper_faults: Dict[str, SensorFaultConfig] = {}
        self._cart_faults: Dict[str, SensorFaultConfig] = {}  # 小车传感器故障 (key: "Cart1_position", "Cart1_left_limit"等)
        
        # 故障计时器
        self._fault_timers: Dict[str, float] = {}
        
        # 是否启用仿真模式（生成模拟数据）
        self._simulation_mode = True
        
        # 初始化/加载数据（强制初始化，确保所有数据都是正确的初始状态）
        self._force_initialize_data()

        # 皮带转速传感器故障配置
        self._conveyor_speed_faults: Dict[str, Optional[str]] = {}  # sensor_id -> fault_type

    def _force_initialize_data(self):
        """强制初始化所有数据为正确的初始状态"""
        # 创建默认数据结构
        self._current_data = {
            "timestamp": get_beijing_time_str(),
            "sensors": {},
            "hoppers": {},
            "conveyor_sensors": {},
            "cart_sensors": {},
            "level_sensors": {},
            "feed_signals": {},
        }
        
        # 初始化接近开关（所有为false）
        for sensor_id in config.SENSORS.keys():
            self._current_data['sensors'][sensor_id] = {
                'value': False,
                'unit': 'bool',
                'type': 'proximity'
            }
        
        # 初始化中转斗（开关=开，称重=0kg）
        for hopper_id in config.TRANSFER_HOPPERS.keys():
            self._current_data['hoppers'][hopper_id] = {
                'switch': {
                    'value': True,  # 初始状态：开
                    'unit': 'bool',
                    'type': 'switch'
                },
                'weight': {
                    'value': 0,  # 初始状态：称重=0 (kg)
                    'unit': 'int',
                    'type': 'weight'
                }
            }
        
        # 初始化皮带转速（所有为0，皮带停止）
        conveyor_sensors_list = [
            'S-CV-E1', 'S-CV-E2', 'S-CV-E4', 'S-CV-E5', 'S-CV-E6', 'S-CV-E7', 'S-CV-E8', 'S-CV-E9', 'S-CV-E10',
            'S-CV-D1', 'S-CV-D2', 'S-CV-D3', 'S-CV-D4', 'S-CV-D5', 'S-CV-D6', 'S-CV-D7', 'S-CV-D8', 'S-CV-D9', 'S-CV-D13'
        ]
        for sensor_id in conveyor_sensors_list:
            self._current_data['conveyor_sensors'][sensor_id] = {
                'type': 'speed',
                'value': 0,  # 皮带停止时转速为0
                'unit': 'sint'
            }
        
        # 初始化小车传感器（使用config中的默认值）
        for cart_id in config.CART_SENSORS.keys():
            self._current_data['cart_sensors'][cart_id] = {
                'position': {
                    'type': 'position',
                    'value': config.CART_DEFAULT_POSITION,
                    'unit': 'byte'
                },
                'left_limit': {
                    'type': 'limit',
                    'value': config.CART_DEFAULT_LEFT_LIMIT,
                    'unit': 'bool'
                },
                'right_limit': {
                    'type': 'limit',
                    'value': config.CART_DEFAULT_RIGHT_LIMIT,
                    'unit': 'bool'
                },
                'left_divert': {
                    'type': 'divert',
                    'value': config.CART_DEFAULT_LEFT_DIVERT,
                    'unit': 'bool'
                },
                'right_divert': {
                    'type': 'divert',
                    'value': config.CART_DEFAULT_RIGHT_DIVERT,
                    'unit': 'bool'
                }
            }
        
        # 初始化料位传感器（默认85%）
        col_names = ['P1', 'P2', 'P3', 'P4']
        for col in col_names:
            for row in range(1, 8):
                bin_id = f"{col}-{row}"
                self._current_data['level_sensors'][bin_id] = {
                    'type': 'level',
                    'unit': '%',
                    'value': 85.0
                }

        for i in range(1, 13):
            bin_id = f"S{i}"
            self._current_data['level_sensors'][bin_id] = {
                'type': 'level',
                'unit': '%',
                'value': 85.0
            }

        # 初始化上料控制信号（所有为false）
        default_feeds = ['feed1_1', 'feed1_2', 'feed2_1', 'feed2_2', 'feed3', 'silo_out']
        for feed_id in default_feeds:
            self._current_data['feed_signals'][feed_id] = {
                'type': 'feed_control',
                'unit': 'bool',
                'value': False
            }
        
        # 保存到文件
        self._save_to_file()
        # print(f"[INIT] 传感器数据已强制初始化到 generate_data.json")

    def _initialize_data(self):
        """初始化或加载数据"""
        if os.path.exists(self.data_file):
            self._load_from_file()
            # 确保 conveyor_sensors 数据存在
            if 'conveyor_sensors' not in self._current_data:
                self._ensure_conveyor_sensors()
            # 确保 cart_sensors 数据存在
            if 'cart_sensors' not in self._current_data:
                self._ensure_cart_sensors()
            # 确保 level_sensors 数据存在
            if 'level_sensors' not in self._current_data:
                self._ensure_level_sensors()
            # 确保 feed_signals 数据存在
            if 'feed_signals' not in self._current_data:
                self._ensure_feed_signals()
            # 确保 hoppers 数据存在
            if 'hoppers' not in self._current_data:
                self._ensure_hoppers()
            else:
                # 确保已有数据中的hoppers开关状态为开
                self._fix_hoppers_initial_state()
        else:
            self._create_default_data()
            self._ensure_conveyor_sensors()
            self._ensure_cart_sensors()
            self._ensure_level_sensors()
            self._ensure_feed_signals()
            self._ensure_hoppers()

    def _fix_hoppers_initial_state(self):
        """修复中转斗初始状态为开"""
        if 'hoppers' in self._current_data:
            hopper_ids = list(config.TRANSFER_HOPPERS.keys())
            for hopper_id in hopper_ids:
                if hopper_id in self._current_data['hoppers']:
                    # 修复开关状态为开
                    if 'switch' in self._current_data['hoppers'][hopper_id]:
                        self._current_data['hoppers'][hopper_id]['switch']['value'] = True
                    # 修复称重为0
                    if 'weight' in self._current_data['hoppers'][hopper_id]:
                        self._current_data['hoppers'][hopper_id]['weight']['value'] = 0.0
            self._save_to_file()

    def _ensure_conveyor_sensors(self):
        """确保皮带转速传感器数据结构存在"""
        if 'conveyor_sensors' not in self._current_data:
            self._current_data['conveyor_sensors'] = {}
        default_conveyors = [
            'S-CV-E1', 'S-CV-E2', 'S-CV-E4', 'S-CV-E5', 'S-CV-E6', 'S-CV-E7', 'S-CV-E8', 'S-CV-E9', 'S-CV-E10',
            'S-CV-D1', 'S-CV-D2', 'S-CV-D3', 'S-CV-D4', 'S-CV-D5', 'S-CV-D6', 'S-CV-D7', 'S-CV-D8', 'S-CV-D9', 'S-CV-D13'
        ]
        for sensor_id in default_conveyors:
            if sensor_id not in self._current_data['conveyor_sensors']:
                self._current_data['conveyor_sensors'][sensor_id] = {
                    'type': 'speed', 'value': 0, 'unit': 'sint'
                }
        self._save_to_file()

    def _ensure_cart_sensors(self):
        """确保运料小车传感器数据结构存在"""
        if 'cart_sensors' not in self._current_data:
            self._current_data['cart_sensors'] = {}

        # 为每个小车初始化传感器数据
        for cart_id in config.CART_SENSORS.keys():
            if cart_id not in self._current_data['cart_sensors']:
                self._current_data['cart_sensors'][cart_id] = {
                    'position': {
                        'type': 'position',
                        'value': config.CART_DEFAULT_POSITION,
                        'unit': 'byte'
                    },
                    'left_limit': {
                        'type': 'limit',
                        'value': config.CART_DEFAULT_LEFT_LIMIT,
                        'unit': 'bool'
                    },
                    'right_limit': {
                        'type': 'limit',
                        'value': config.CART_DEFAULT_RIGHT_LIMIT,
                        'unit': 'bool'
                    },
                    'left_divert': {
                        'type': 'divert',
                        'value': config.CART_DEFAULT_LEFT_DIVERT,
                        'unit': 'bool'
                    },
                    'right_divert': {
                        'type': 'divert',
                        'value': config.CART_DEFAULT_RIGHT_DIVERT,
                        'unit': 'bool'
                    }
                }
        self._save_to_file()

    def _ensure_level_sensors(self):
        """确保料位传感器数据结构存在"""
        if 'level_sensors' not in self._current_data:
            self._current_data['level_sensors'] = {}

        # 初始化高位配料站料仓
        col_names = ['P1', 'P2', 'P3', 'P4']
        for col in col_names:
            for row in range(1, 8):
                bin_id = f"{col}-{row}"
                if bin_id not in self._current_data['level_sensors']:
                    self._current_data['level_sensors'][bin_id] = {
                        'type': 'level',
                        'unit': '%',
                        'value': 85.0  # 默认85%
                    }

        # 初始化高位储料仓
        for i in range(1, 13):
            bin_id = f"S{i}"
            if bin_id not in self._current_data['level_sensors']:
                self._current_data['level_sensors'][bin_id] = {
                    'type': 'level',
                    'unit': '%',
                    'value': 85.0  # 默认85%
                }

        self._save_to_file()

    def _ensure_feed_signals(self):
        """确保上料控制信号数据结构存在"""
        if 'feed_signals' not in self._current_data:
            self._current_data['feed_signals'] = {}

        # 初始化所有上料点
        default_feeds = ['feed1_1', 'feed1_2', 'feed2_1', 'feed2_2', 'feed3', 'silo_out']
        for feed_id in default_feeds:
            if feed_id not in self._current_data['feed_signals']:
                self._current_data['feed_signals'][feed_id] = {
                    'type': 'feed_control',
                    'unit': 'bool',
                    'value': False
                }

        self._save_to_file()

    def _ensure_hoppers(self):
        """确保中转斗数据结构存在（初始状态：开关=开，称重=0kg）"""
        if 'hoppers' not in self._current_data:
            self._current_data['hoppers'] = {}

        # 初始化所有中转斗
        hopper_ids = list(config.TRANSFER_HOPPERS.keys())
        for hopper_id in hopper_ids:
            if hopper_id not in self._current_data['hoppers']:
                self._current_data['hoppers'][hopper_id] = {
                    'switch': {
                        'value': True,  # 初始状态：开
                        'unit': 'bool',
                        'type': 'switch'
                    },
                    'weight': {
                        'value': 0,  # 初始状态：称重=0 (kg)
                        'unit': 'int',
                        'type': 'weight'
                    }
                }
            else:
                # 修复已有数据：确保称重为int类型kg
                if 'weight' in self._current_data['hoppers'][hopper_id]:
                    w = self._current_data['hoppers'][hopper_id]['weight']
                    if 'value' in w:
                        # 如果是float，转为int kg
                        if isinstance(w['value'], float):
                            w['value'] = int(w['value'] * 1000)
                        elif isinstance(w['value'], int) and w.get('unit') == 'float':
                            # 如果是int但单位是float，说明之前保存有问题
                            w['value'] = 0
                        w['unit'] = 'int'

        self._save_to_file()

    def _create_default_data(self):
        """创建默认数据结构"""
        self._current_data = {
            "timestamp": get_beijing_time_str(),
            "sensors": {},
            "hoppers": {},
            "conveyor_sensors": {},
            "cart_sensors": {},
            "level_sensors": {},
            "feed_signals": {},
        }
        self._save_to_file()
    
    def _load_from_file(self):
        """从 generate_data.json 文件加载数据"""
        with self._lock:
            try:
                with open(GENERATE_DATA_FILE, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if not content:
                        self._create_default_data()
                        return
                    self._current_data = json.loads(content)
            except Exception as e:
                self._create_default_data()
    
    def _save_to_file(self):
        """保存数据到 generate_data.json 文件"""
        with self._lock:
            try:
                with open(GENERATE_DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self._current_data, f, indent=4, ensure_ascii=False)
            except Exception:
                pass

    def set_simulation_mode(self, enabled: bool):
        """设置是否启用仿真模式"""
        self._simulation_mode = enabled
    
    def is_simulation_mode(self) -> bool:
        """检查是否为仿真模式"""
        return self._simulation_mode
    
    # ============ 数据读取接口 ============
    
    def read_all_sensors(self) -> Dict[str, bool]:
        """
        读取所有接近开关传感器数据
        Returns: {sensor_id: value, ...}
        """
        self._load_from_file()
        sensors = self._current_data.get('sensors', {})
        return {sid: data['value'] for sid, data in sensors.items()}
    
    def read_sensor(self, sensor_id: str) -> Optional[bool]:
        """读取单个接近开关传感器"""
        self._load_from_file()
        sensors = self._current_data.get('sensors', {})
        if sensor_id in sensors:
            return sensors[sensor_id]['value']
        return None
    
    def read_all_hopper_data(self) -> Dict[str, Dict[str, Any]]:
        """
        读取所有中转斗数据
        Returns: {hopper_id: {"switch": bool, "weight": float}, ...}
        """
        self._load_from_file()
        hoppers = self._current_data.get('hoppers', {})
        result = {}
        for hid, data in hoppers.items():
            result[hid] = {
                'switch': data.get('switch', {}).get('value', True),
                'weight': data.get('weight', {}).get('value', 0.0)
            }
        return result

    def read_conveyor_speeds(self) -> Dict[str, int]:
        """
        读取所有皮带转速传感器数据
        Returns: {sensor_id: speed_value (sint), ...}
        """
        self._load_from_file()
        conveyor_sensors = self._current_data.get('conveyor_sensors', {})
        return {sid: int(data.get('value', 0)) for sid, data in conveyor_sensors.items()}

    def read_conveyor_speed(self, sensor_id: str) -> Optional[int]:
        """读取单个皮带转速传感器"""
        self._load_from_file()
        conveyor_sensors = self._current_data.get('conveyor_sensors', {})
        if sensor_id in conveyor_sensors:
            return int(conveyor_sensors[sensor_id].get('value', 0))
        return None

    # ============ 小车传感器读取接口 ============

    def read_cart_sensors(self) -> Dict[str, Dict[str, Any]]:
        """
        读取所有运料小车传感器数据
        Returns: {
            'Cart1': {'position': int, 'left_limit': bool, 'right_limit': bool, 'left_divert': bool, 'right_divert': bool},
            'Cart2': {...},
            'Cart3': {...}
        }
        """
        self._load_from_file()
        cart_sensors = self._current_data.get('cart_sensors', {})
        result = {}
        for cart_id, data in cart_sensors.items():
            result[cart_id] = {
                'position': data.get('position', {}).get('value', config.CART_DEFAULT_POSITION),
                'left_limit': data.get('left_limit', {}).get('value', config.CART_DEFAULT_LEFT_LIMIT),
                'right_limit': data.get('right_limit', {}).get('value', config.CART_DEFAULT_RIGHT_LIMIT),
                'left_divert': data.get('left_divert', {}).get('value', config.CART_DEFAULT_LEFT_DIVERT),
                'right_divert': data.get('right_divert', {}).get('value', config.CART_DEFAULT_RIGHT_DIVERT),
            }
        return result

    def read_cart_sensor(self, cart_id: str, sensor_type: str) -> Optional[Any]:
        """
        读取单个小车传感器
        Args:
            cart_id: 小车ID (Cart1/Cart2/Cart3)
            sensor_type: 传感器类型 (position/left_limit/right_limit/left_divert/right_divert)
        """
        self._load_from_file()
        cart_sensors = self._current_data.get('cart_sensors', {})
        if cart_id in cart_sensors and sensor_type in cart_sensors[cart_id]:
            return cart_sensors[cart_id][sensor_type].get('value')
        return None

    def read_cart_position(self, cart_id: str) -> Optional[int]:
        """读取小车位置传感器值"""
        return self.read_cart_sensor(cart_id, 'position')

    # ============ 小车传感器写入接口 ============

    def write_cart_sensor(self, cart_id: str, sensor_type: str, value: Any):
        """
        写入小车传感器数据（故障注入具有最高优先级，故障状态下外部写入无效）
        Args:
            cart_id: 小车ID
            sensor_type: 传感器类型 (position/left_limit/right_limit/left_divert/right_divert)
            value: 传感器值（仅无故障时生效）
        """
        if not self._current_data:
            self._load_from_file()

        if 'cart_sensors' not in self._current_data:
            self._current_data['cart_sensors'] = {}
        if cart_id not in self._current_data['cart_sensors']:
            self._ensure_cart_sensors()

        sensor_config = {
            'position': {'type': 'position', 'unit': 'byte'},
            'left_limit': {'type': 'limit', 'unit': 'bool'},
            'right_limit': {'type': 'limit', 'unit': 'bool'},
            'left_divert': {'type': 'divert', 'unit': 'bool'},
            'right_divert': {'type': 'divert', 'unit': 'bool'},
        }

        # 类型验证
        if sensor_type in ['left_limit', 'right_limit', 'left_divert', 'right_divert']:
            value = bool(value)
        elif sensor_type == 'position':
            value = int(value)
            # 限制范围 1-7
            value = max(config.CART_POSITION_MIN, min(config.CART_POSITION_MAX, value))

        # 应用小车传感器故障（最高优先级，覆盖外部传入值）
        fault_key = f"{cart_id}_{sensor_type}"
        final_value = self._apply_cart_sensor_fault(fault_key, cart_id, sensor_type, value)

        self._current_data['cart_sensors'][cart_id][sensor_type] = {
            'type': sensor_config[sensor_type]['type'],
            'unit': sensor_config[sensor_type]['unit'],
            'value': final_value
        }
        self._current_data['timestamp'] = get_beijing_time_str()
        self._save_to_file()

    def write_cart_position(self, cart_id: str, position: int):
        """写入小车位置传感器"""
        self.write_cart_sensor(cart_id, 'position', position)

    def write_cart_left_limit(self, cart_id: str, value: bool):
        """写入小车左极限传感器"""
        self.write_cart_sensor(cart_id, 'left_limit', value)

    def write_cart_right_limit(self, cart_id: str, value: bool):
        """写入小车右极限传感器"""
        self.write_cart_sensor(cart_id, 'right_limit', value)

    def write_cart_left_divert(self, cart_id: str, value: bool):
        """写入小车左分料传感器"""
        self.write_cart_sensor(cart_id, 'left_divert', value)

    def write_cart_right_divert(self, cart_id: str, value: bool):
        """写入小车右分料传感器"""
        self.write_cart_sensor(cart_id, 'right_divert', value)

    def write_all_cart_sensors(self, cart_id: str, position: int, left_limit: bool,
                               right_limit: bool, left_divert: bool, right_divert: bool):
        """批量写入小车所有传感器"""
        self.write_cart_position(cart_id, position)
        self.write_cart_left_limit(cart_id, left_limit)
        self.write_cart_right_limit(cart_id, right_limit)
        self.write_cart_left_divert(cart_id, left_divert)
        self.write_cart_right_divert(cart_id, right_divert)

    def read_hopper(self, hopper_id: str) -> Optional[Dict[str, Any]]:
        """读取单个中转斗数据"""
        self._load_from_file()
        hoppers = self._current_data.get('hoppers', {})
        if hopper_id in hoppers:
            return {
                'switch': hoppers[hopper_id].get('switch', {}).get('value', True),
                'weight': hoppers[hopper_id].get('weight', {}).get('value', 0.0)
            }
        return None
    
    # ============ 数据写入接口（仿真模式使用） ============
    
    def write_sensor(self, sensor_id: str, value: bool):
        """写入接近开关传感器数据"""
        self._load_from_file()
        
        # 应用故障
        final_value = self._apply_sensor_fault(sensor_id, value)
        
        if 'sensors' not in self._current_data:
            self._current_data['sensors'] = {}
        if sensor_id not in self._current_data['sensors']:
            self._current_data['sensors'][sensor_id] = {'type': 'proximity', 'unit': 'bool'}
        
        self._current_data['sensors'][sensor_id]['value'] = final_value
        self._current_data['timestamp'] = get_beijing_time_str()
        self._save_to_file()
    
    def write_hopper_switch(self, hopper_id: str, value: bool):
        """写入中转斗开关状态"""
        self._load_from_file()
        
        # 应用故障
        final_value = self._apply_hopper_switch_fault(hopper_id, value)
        
        if 'hoppers' not in self._current_data:
            self._current_data['hoppers'] = {}
        if hopper_id not in self._current_data['hoppers']:
            self._current_data['hoppers'][hopper_id] = {}
        if 'switch' not in self._current_data['hoppers'][hopper_id]:
            self._current_data['hoppers'][hopper_id]['switch'] = {'type': 'switch', 'unit': 'bool'}
        
        self._current_data['hoppers'][hopper_id]['switch']['value'] = final_value
        self._current_data['timestamp'] = get_beijing_time_str()
        self._save_to_file()
    
    def write_hopper_weight(self, hopper_id: str, value: float):
        """写入中转斗称重数据（单位：kg，int类型）

        Args:
            hopper_id: 中转斗ID
            value: 称重值（吨），方法内部转换为kg
        """
        self._load_from_file()

        # 应用称重故障
        final_value = self._apply_hopper_weight_fault(hopper_id, value)

        if 'hoppers' not in self._current_data:
            self._current_data['hoppers'] = {}
        if hopper_id not in self._current_data['hoppers']:
            self._current_data['hoppers'][hopper_id] = {}

        # 转换为kg并转为int类型
        weight_kg = int(round(final_value * 1000))
        self._current_data['hoppers'][hopper_id]['weight'] = {
            'type': 'weight',
            'unit': 'int',
            'value': weight_kg
        }

        self._current_data['timestamp'] = get_beijing_time_str()
        self._save_to_file()
    
    def write_all_sensors(self, sensor_values: Dict[str, bool]):
        """批量写入接近开关传感器数据"""
        for sensor_id, value in sensor_values.items():
            self.write_sensor(sensor_id, value)

    def write_conveyor_speed(self, sensor_id: str, value: int):
        """写入皮带转速传感器数据（sint类型）"""
        # 不每次都加载文件，只在必要时才加载
        if not self._current_data:
            self._load_from_file()

        # 应用故障
        final_value = self._apply_conveyor_speed_fault(sensor_id, value)

        if 'conveyor_sensors' not in self._current_data:
            self._current_data['conveyor_sensors'] = {}
        if sensor_id not in self._current_data['conveyor_sensors']:
            self._current_data['conveyor_sensors'][sensor_id] = {'type': 'speed', 'unit': 'sint'}

        self._current_data['conveyor_sensors'][sensor_id]['value'] = int(final_value)
        self._current_data['timestamp'] = get_beijing_time_str()

        self._save_to_file()

    def _apply_conveyor_speed_fault(self, sensor_id: str, normal_speed: int) -> int:
        """应用皮带转速故障"""
        fault_type = self._conveyor_speed_faults.get(sensor_id)

        if fault_type is None:
            return normal_speed

        if fault_type == 'stopped':
            # 关闭状态：转速为0
            return 0
        elif fault_type == 'speed_abnormal':
            # 转速异常：返回低于阈值的转速值（低于450视为异常）
            # 异常转速范围：350-440
            return random.randint(350, 440)

        return normal_speed

    def set_conveyor_speed_fault(self, sensor_id: str, fault_type: Optional[str]):
        """设置皮带转速传感器故障"""
        if fault_type:
            self._conveyor_speed_faults[sensor_id] = fault_type
        else:
            self._conveyor_speed_faults.pop(sensor_id, None)

    def clear_conveyor_speed_fault(self, sensor_id: str = None):
        """清除皮带转速传感器故障"""
        if sensor_id:
            self._conveyor_speed_faults.pop(sensor_id, None)
        else:
            self._conveyor_speed_faults.clear()

    def write_all_hopper_data(self, hopper_data: Dict[str, Dict[str, Any]]):
        """批量写入中转斗数据"""
        for hopper_id, data in hopper_data.items():
            if 'switch' in data:
                self.write_hopper_switch(hopper_id, data['switch'])
            if 'weight' in data:
                self.write_hopper_weight(hopper_id, data['weight'])
    
    # ============ 故障注入接口 ============
    
    def inject_sensor_fault(self, sensor_id: str, fault_mode: FaultMode, 
                           duration: float = -1.0, probability: float = 1.0):
        """
        注入传感器故障
        
        Args:
            sensor_id: 传感器ID
            fault_mode: 故障模式
            duration: 故障持续时间（秒），-1表示持续
            probability: 故障发生概率 (0-1)
        """
        config = SensorFaultConfig(
            sensor_id=sensor_id,
            fault_mode=fault_mode,
            fault_start_time=time.time(),
            fault_duration=duration,
            probability=probability
        )
        self._sensor_faults[sensor_id] = config
    
    def inject_hopper_switch_fault(self, hopper_id: str, fault_mode: FaultMode,
                                   duration: float = -1.0):
        """
        注入中转斗开关故障
        
        Args:
            hopper_id: 中转斗ID
            fault_mode: 故障模式（STUCK_CLOSED表示卡关，STUCK_OPEN表示卡开）
            duration: 故障持续时间（秒）
        """
        config = SensorFaultConfig(
            sensor_id=hopper_id,
            fault_mode=fault_mode,
            fault_start_time=time.time(),
            fault_duration=duration,
            probability=1.0
        )
        self._hopper_faults[hopper_id] = config
    
    def inject_hopper_weight_fault(self, hopper_id: str, fault_mode: FaultMode,
                                   offset: float = 0.0, duration: float = -1.0):
        """
        注入中转斗称重故障
        
        Args:
            hopper_id: 中转斗ID
            fault_mode: 故障模式
            offset: 称重偏移量
            duration: 故障持续时间（秒）
        """
        config = SensorFaultConfig(
            sensor_id=hopper_id,
            fault_mode=fault_mode,
            fault_start_time=time.time(),
            fault_duration=duration,
            probability=1.0
        )
        config.weight_offset = offset
        self._hopper_faults[hopper_id] = config
    
    def clear_fault(self, sensor_id: str = None, hopper_id: str = None):
        """清除故障"""
        if sensor_id:
            self._sensor_faults.pop(sensor_id, None)
        if hopper_id:
            self._hopper_faults.pop(hopper_id, None)
    
    def clear_all_faults(self):
        """清除所有故障"""
        self._sensor_faults.clear()
        self._hopper_faults.clear()
        self._cart_faults.clear()
    
    def get_fault_status(self) -> Dict[str, Any]:
        """获取故障状态"""
        return {
            'sensor_faults': {k: v.fault_mode.value for k, v in self._sensor_faults.items()},
            'hopper_faults': {k: v.fault_mode.value for k, v in self._hopper_faults.items()},
            'cart_faults': {k: v.fault_mode.value for k, v in self._cart_faults.items()}
        }
    
    # ============ 小车传感器故障注入接口 ============
    
    def inject_cart_sensor_fault(self, cart_id: str, sensor_type: str, 
                                  fault_mode: FaultMode, duration: float = -1.0):
        """
        注入运料小车传感器故障
        
        传感器类型及对应故障模式：
        - position（位置传感器）: POSITION_STUCK（定位卡死）, POSITION_OFFSET（定位不准）
        - left_limit（左极限）: STUCK_LOW（恒定为false）, STUCK_HIGH（恒定为true）
        - right_limit（右极限）: 同上
        - left_divert（左分料）: 同上
        - right_divert（右分料）: 同上
        
        故障注入后，generate_data.json中该数据项将不再接收上料过程写入的值，
        而是持续输出故障值，具有最高优先级。
        
        Args:
            cart_id: 小车ID (Cart1/Cart2/Cart3/Cart4)
            sensor_type: 传感器类型
            fault_mode: 故障模式
            duration: 故障持续时间（秒），-1表示持续
        """
        fault_key = f"{cart_id}_{sensor_type}"
        config_obj = SensorFaultConfig(
            sensor_id=fault_key,
            fault_mode=fault_mode,
            fault_start_time=time.time(),
            fault_duration=duration,
            probability=1.0
        )
        self._cart_faults[fault_key] = config_obj
    
    def clear_cart_sensor_fault(self, cart_id: str = None, sensor_type: str = None):
        """
        清除小车传感器故障
        
        Args:
            cart_id: 小车ID（为None则清除所有小车传感器故障）
            sensor_type: 传感器类型（为None则清除该小车的所有传感器故障）
        """
        if cart_id is None:
            self._cart_faults.clear()
            return
        
        if sensor_type is None:
            # 清除该小车的所有传感器故障
            prefix = f"{cart_id}_"
            keys_to_remove = [k for k in self._cart_faults if k.startswith(prefix)]
            for k in keys_to_remove:
                self._cart_faults.pop(k, None)
        else:
            fault_key = f"{cart_id}_{sensor_type}"
            self._cart_faults.pop(fault_key, None)
    
    def clear_cart_fault(self, cart_id: str, sensor_type: str):
        """清除指定小车的指定传感器故障（便捷方法）"""
        fault_key = f"{cart_id}_{sensor_type}"
        self._cart_faults.pop(fault_key, None)
    
    # ============ 内部方法 ============
    
    def _apply_sensor_fault(self, sensor_id: str, original_value: bool) -> bool:
        """应用传感器故障"""
        if sensor_id not in self._sensor_faults:
            return original_value
        
        fault = self._sensor_faults[sensor_id]
        
        # 检查故障是否过期
        if fault.fault_duration > 0:
            elapsed = time.time() - fault.fault_start_time
            if elapsed > fault.fault_duration:
                self._sensor_faults.pop(sensor_id, None)
                return original_value
        
        # 检查概率
        if random.random() > fault.probability:
            return original_value
        
        # 根据故障模式返回故障值
        if fault.fault_mode == FaultMode.STUCK_LOW:
            return False
        elif fault.fault_mode == FaultMode.STUCK_HIGH:
            return True
        elif fault.fault_mode == FaultMode.RANDOM:
            return random.choice([True, False])
        elif fault.fault_mode == FaultMode.SENSITIVITY_LOSS:
            # 30%概率漏检
            if original_value:
                return random.random() > 0.3
            return False
        elif fault.fault_mode == FaultMode.INTERMITTENT:
            # 50%概率保持上一个状态
            return original_value if random.random() > 0.5 else not original_value
        
        return original_value
    
    def _apply_hopper_switch_fault(self, hopper_id: str, original_value: bool) -> bool:
        """应用中转斗开关故障"""
        if hopper_id not in self._hopper_faults:
            return original_value
        
        fault = self._hopper_faults[hopper_id]
        
        # 检查故障是否过期
        if fault.fault_duration > 0:
            elapsed = time.time() - fault.fault_start_time
            if elapsed > fault.fault_duration:
                self._hopper_faults.pop(hopper_id, None)
                return original_value
        
        # STUCK_LOW = 卡关, STUCK_HIGH = 卡开
        if fault.fault_mode == FaultMode.STUCK_LOW:
            return False  # 卡在关
        elif fault.fault_mode == FaultMode.STUCK_HIGH:
            return True   # 卡在开
        
        return original_value
    
    def _apply_cart_sensor_fault(self, fault_key: str, cart_id: str, sensor_type: str, original_value: Any) -> Any:
        """
        应用小车传感器故障（最高优先级）
        
        对于位置传感器：
        - POSITION_STUCK: 保持首次故障时的位置不变（位置卡死）
        - POSITION_OFFSET: 在真实位置基础上偏移±1
        
        对于开关量传感器（left_limit, right_limit, left_divert, right_divert）：
        - STUCK_LOW: 恒定为False
        - STUCK_HIGH: 恒定为True
        
        Args:
            fault_key: 故障键
            cart_id: 小车ID
            sensor_type: 传感器类型
            original_value: 上料过程计算出的原始值
            
        Returns:
            故障覆盖后的值
        """
        if fault_key not in self._cart_faults:
            return original_value
        
        fault = self._cart_faults[fault_key]
        
        # 检查故障是否过期
        if fault.fault_duration > 0:
            elapsed = time.time() - fault.fault_start_time
            if elapsed > fault.fault_duration:
                self._cart_faults.pop(fault_key, None)
                return original_value
        
        mode = fault.fault_mode
        
        if sensor_type == 'position':
            # 位置传感器故障
            if mode == FaultMode.POSITION_STUCK:
                # 位置卡死：使用故障注入时记录的"卡死位置"（存在 _cart_stuck_positions 中）
                stuck_pos = getattr(self, '_cart_stuck_positions', {})
                if fault_key not in stuck_pos:
                    # 首次调用：记录当前位置作为卡死值
                    if not hasattr(self, '_cart_stuck_positions'):
                        self._cart_stuck_positions = {}
                    self._cart_stuck_positions[fault_key] = original_value
                return self._cart_stuck_positions.get(fault_key, original_value)
            elif mode == FaultMode.POSITION_OFFSET:
                # 定位不准：随机偏移±1，限制在有效范围内
                offset = random.choice([-1, 1])
                new_pos = original_value + offset
                new_pos = max(config.CART_POSITION_MIN, min(config.CART_POSITION_MAX, new_pos))
                return new_pos
        else:
            # 开关量传感器故障
            if mode == FaultMode.STUCK_LOW:
                return False
            elif mode == FaultMode.STUCK_HIGH:
                return True
        
        return original_value
    
    def _apply_hopper_weight_fault(self, hopper_id: str, original_value: float) -> float:
        """应用中转斗称重故障"""
        if hopper_id not in self._hopper_faults:
            return original_value
        
        fault = self._hopper_faults[hopper_id]
        
        # 检查故障是否过期
        if fault.fault_duration > 0:
            elapsed = time.time() - fault.fault_start_time
            if elapsed > fault.fault_duration:
                self._hopper_faults.pop(hopper_id, None)
                return original_value
        
        if fault.fault_mode == FaultMode.STUCK_LOW:
            return 0.0  # 恒为0
        elif fault.fault_mode == FaultMode.SENSITIVITY_LOSS:
            # 偏移±20%
            return original_value * random.uniform(0.8, 1.2)
        
        return original_value
    
    # ============ 料位传感器接口 ============

    def write_level_sensor(self, bin_id: str, value: float):
        """
        写入料位传感器数据

        Args:
            bin_id: 料仓ID (如 'P1-1', 'S1')
            value: 实际料位重量（吨）
        """
        if not self._current_data:
            self._load_from_file()

        if 'level_sensors' not in self._current_data:
            self._current_data['level_sensors'] = {}

        self._current_data['level_sensors'][bin_id] = {
            'type': 'level',
            'unit': '%',  # 百分比
            'value': round(value, 3)  # 保留3位小数
        }
        self._current_data['timestamp'] = get_beijing_time_str()
        self._save_to_file()

    def read_level_sensor(self, bin_id: str) -> Optional[float]:
        """读取单个料位传感器"""
        self._load_from_file()
        level_sensors = self._current_data.get('level_sensors', {})
        if bin_id in level_sensors:
            return level_sensors[bin_id].get('value', 0.0)
        return None

    def read_all_level_sensors(self) -> Dict[str, float]:
        """读取所有料位传感器数据"""
        self._load_from_file()
        level_sensors = self._current_data.get('level_sensors', {})
        return {bin_id: data.get('value', 0.0) for bin_id, data in level_sensors.items()}

    def write_all_level_sensors(self, level_data: Dict[str, float]):
        """批量写入料位传感器数据"""
        for bin_id, value in level_data.items():
            self.write_level_sensor(bin_id, value)

    # ============ 上料控制信号接口 ============

    def write_feed_signal(self, feed_id: str, value: bool):
        """
        写入上料控制信号

        Args:
            feed_id: 上料点ID (如 'feed1_1', 'feed2_1', 'silo_out')
            value: True=打开, False=关闭
        """
        if not self._current_data:
            self._load_from_file()

        if 'feed_signals' not in self._current_data:
            self._current_data['feed_signals'] = {}

        self._current_data['feed_signals'][feed_id] = {
            'type': 'feed_control',
            'unit': 'bool',
            'value': bool(value)
        }
        self._current_data['timestamp'] = get_beijing_time_str()
        self._save_to_file()

    def read_feed_signal(self, feed_id: str) -> Optional[bool]:
        """读取单个上料控制信号"""
        self._load_from_file()
        feed_signals = self._current_data.get('feed_signals', {})
        if feed_id in feed_signals:
            return feed_signals[feed_id].get('value', False)
        return None

    def read_feed_signals(self) -> Dict[str, bool]:
        """读取所有上料控制信号"""
        self._load_from_file()
        feed_signals = self._current_data.get('feed_signals', {})
        return {feed_id: data.get('value', False) for feed_id, data in feed_signals.items()}

    def write_all_feed_signals(self, feed_data: Dict[str, bool]):
        """批量写入上料控制信号"""
        for feed_id, value in feed_data.items():
            self.write_feed_signal(feed_id, value)

    def read_consumption_rates(self) -> Dict[str, float]:
        """读取料仓消耗速度"""
        self._load_from_file()
        return self._current_data.get('consumption_rates', {})

    def write_consumption_rates(self, rates: Dict[str, float]):
        """写入料仓消耗速度"""
        self._load_from_file()
        self._current_data['consumption_rates'] = dict(rates)
        self._save_to_file()

    # ============ 辅助方法 ============

    def get_generate_data_file_path(self) -> str:
        """获取生成数据文件路径"""
        return GENERATE_DATA_FILE

    def get_data_file_path(self) -> str:
        """获取数据文件路径"""
        return self.data_file

    def reset_data(self):
        """重置数据为默认值"""
        self._create_default_data()

    def reset_all_data(self):
        """重置全部数据（reset_data 的别名，兼容新接口）"""
        self.reset_data()
        self.clear_all_faults() if hasattr(self, 'clear_all_faults') else None

    def export_data(self) -> str:
        """导出当前数据为JSON字符串"""
        self._load_from_file()
        return json.dumps(self._current_data, indent=4, ensure_ascii=False)


# 全局单例
_data_manager_instance: Optional[SensorDataManager] = None


def get_data_manager(data_file: str = None) -> SensorDataManager:
    """获取传感器数据管理器单例"""
    global _data_manager_instance
    if _data_manager_instance is None:
        _data_manager_instance = SensorDataManager(data_file)
    return _data_manager_instance
