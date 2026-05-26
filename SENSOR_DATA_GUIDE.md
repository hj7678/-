# 传感器数据管理系统

## 概述

本系统模拟实际生产环境中传感器数据的采集和管理。传感器数据存储在JSON文件中，支持仿真模式和监听模式两种工作方式。

## 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                      仿真软件（上位机）                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐    ┌─────────────────────┐                │
│  │ SimulationController│◄──►│ SensorDataManager  │                │
│  │   (仿真控制器)     │    │  (传感器数据管理器)  │                │
│  └──────────────────┘    └─────────────────────┘                │
│            ▲                       ▲                              │
│            │                       │                              │
│            │              ┌────────┴────────┐                    │
│            │              │                  │                    │
│            │      ┌──────┴──────┐    ┌─────┴─────┐              │
│            │      │ 写入数据     │    │ 读取数据   │              │
│            │      │ (仿真模式)   │    │ (监听模式) │              │
│            │      └──────┬──────┘    └─────┬─────┘              │
│            │              │                │                     │
│  ┌─────────┴──────────────┴────────────────┴─────────────────┐  │
│  │                      JSON 数据文件                         │  │
│  │                 data/sensor_data.json                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 数据文件格式

### 文件位置
`data/sensor_data.json`

### JSON结构

```json
{
    "_comment": "传感器实时数据文件",
    "timestamp": "2026-04-29T08:00:00.000Z",
    "sensors": {
        "S-E1": {"type": "proximity", "value": false, "unit": "bool"},
        "S-E2": {"type": "proximity", "value": false, "unit": "bool"},
        ...
    },
    "hoppers": {
        "hopper1": {
            "switch": {"type": "switch", "value": true, "unit": "bool"},
            "weight": {"type": "weight", "value": 0.0, "unit": "ton"}
        },
        ...
    }
}
```

## 传感器类型

### 1. 接近开关传感器（proximity）
- **数据类型**: bool
- **含义**: true=有料流, false=无料流
- **示例**: `{"type": "proximity", "value": true, "unit": "bool"}`

### 2. 中转斗开关（switch）
- **数据类型**: bool
- **含义**: true=开（物料可通过）, false=关（物料存储）
- **示例**: `{"type": "switch", "value": true, "unit": "bool"}`

### 3. 中转斗称重（weight）
- **数据类型**: float
- **含义**: 当前重量（吨）
- **示例**: `{"type": "weight", "value": 2.5, "unit": "ton"}`

## 工作模式

### 仿真模式（默认）
仿真软件根据物料位置自动生成传感器数据，写入JSON文件。

```python
# 启用仿真模式
controller.set_sensor_data_mode(True)

# 生成的数据会自动写入 data/sensor_data.json
```

### 监听模式
外部系统向JSON文件写入数据，仿真软件读取数据进行显示。

```python
# 切换到监听模式（停止生成数据）
controller.set_sensor_data_mode(False)

# 从JSON读取数据
data = controller.get_sensor_data_from_json()
```

## 故障注入

### 接近开关传感器故障

| 故障模式 | 描述 | 效果 |
|---------|------|------|
| `stuck_low` | 卡在低电平 | 始终输出false |
| `stuck_high` | 卡在高电平 | 始终输出true |
| `random` | 随机值 | 随机输出true/false |
| `sensitivity_loss` | 灵敏度降低 | 有物料时30%概率漏检 |
| `intermittent` | 间歇性故障 | 50%概率保持原状态 |

### 中转斗故障

| 故障模式 | 描述 | 效果 |
|---------|------|------|
| `stuck_closed` | 开关卡在关 | 物料无法通过，存储在斗内 |
| `stuck_open` | 开关卡在开 | 物料正常通过 |
| `weight_zero` | 称重显示0 | 称重数据恒为0 |
| `weight_offset` | 称重偏移 | 称重数据偏移±20% |

### 使用示例

```python
from sensor_data_manager import FaultMode

# 注入传感器故障
controller.inject_sensor_fault("S-E1", "stuck_low")

# 注入中转斗开关故障（卡关）
controller.inject_hopper_switch_fault("hopper1", stuck_closed=True)

# 注入称重故障（显示0）
controller.inject_hopper_weight_fault("hopper1", stuck_zero=True)

# 清除所有故障
controller.clear_all_sensor_faults()
```

## API接口

### SimulationController 传感器相关方法

| 方法 | 描述 |
|------|------|
| `get_sensor_data_from_json()` | 从JSON读取传感器数据 |
| `set_sensor_data_mode(simulation_mode)` | 设置工作模式 |
| `get_data_file_path()` | 获取数据文件路径 |
| `export_sensor_data()` | 导出数据为JSON字符串 |
| `inject_sensor_fault(sensor_id, fault_mode)` | 注入传感器故障 |
| `inject_hopper_switch_fault(hopper_id, stuck_closed)` | 注入开关故障 |
| `inject_hopper_weight_fault(hopper_id, stuck_zero)` | 注入称重故障 |
| `clear_all_sensor_faults()` | 清除所有故障 |
| `get_sensor_fault_status()` | 获取故障状态 |

### SensorDataManager 方法

| 方法 | 描述 |
|------|------|
| `read_all_sensors()` | 读取所有接近开关状态 |
| `read_sensor(sensor_id)` | 读取单个接近开关 |
| `read_all_hopper_data()` | 读取所有中转斗数据 |
| `write_sensor(sensor_id, value)` | 写入接近开关状态 |
| `write_hopper_switch(hopper_id, value)` | 写入中转斗开关状态 |
| `write_hopper_weight(hopper_id, value)` | 写入中转斗称重数据 |
| `inject_sensor_fault(...)` | 注入传感器故障 |
| `clear_all_faults()` | 清除所有故障 |

## 实际对接指南

### 1. 作为真实上位机使用

将仿真软件当作真实上位机使用时：

1. **仿真模式**：软件自动生成传感器数据，用于测试和演示
2. **监听模式**：外部PLC/传感器系统向JSON文件写入实时数据

### 2. 数据流向

```
实际传感器/PLC → JSON文件 → 仿真软件（显示/诊断）
                     ↑
              外部系统写入
```

### 3. 外部写入示例

外部系统（如PLC程序）可以这样写入数据：

```python
import json

# 读取当前数据
with open('data/sensor_data.json', 'r') as f:
    data = json.load(f)

# 更新传感器数据
data['sensors']['S-E1']['value'] = True  # 模拟有料流
data['hoppers']['hopper1']['switch']['value'] = False  # 模拟开关关闭
data['hoppers']['hopper1']['weight']['value'] = 1.5  # 模拟称重1.5吨

# 保存
with open('data/sensor_data.json', 'w') as f:
    json.dump(data, f, indent=4)
```

## 文件清单

| 文件 | 描述 |
|------|------|
| `sensor_data_manager.py` | 传感器数据管理器 |
| `sensor_data_generator.py` | 传感器数据生成器 |
| `data/sensor_data.json` | 传感器数据文件 |
| `sensor_fault_diagnosis.py` | 故障诊断系统（原有） |
| `controllers/simulation_controller.py` | 仿真控制器（已集成） |
