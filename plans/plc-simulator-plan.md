# PLC 模拟器 (下位机仿真) — 独立模块方案

## 1. 定位

```
┌──────────────────────────────────────────────────────────┐
│                     工控机 (上位机侧)                       │
│                                                          │
│  Stock Mgmt :8895    FeedingMaster :8896    FaultDiag :8897 │
│         │                   │                    │        │
│         └───────────────────┼────────────────────┘        │
│                             │ TCP JSON                    │
│                      ┌──────↓───────┐                     │
│                      │ Upper Computer│                    │
│                      │  (HMI + 路由) │                     │
│                      └──────┬───────┘                     │
│                             │ Modbus TCP :1502            │
├─────────────────────────────┼─────────────────────────────┤
│                             ↓                              │
│  ┌──────────────────────────────────────────────────┐    │
│  │            PLC Simulator (下位机模拟器)             │    │
│  │                     :1502                         │    │
│  │                                                   │    │
│  │  Modbus TCP Server                                │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐        │    │
│  │  │ 线圈      │  │ 离散输入  │  │ 保持寄存器│        │    │
│  │  │ (执行器)  │  │ (传感器)  │  │ (称重等) │        │    │
│  │  └──────────┘  └──────────┘  └──────────┘        │    │
│  │        ↑              │              │             │    │
│  │        │         ┌────↓──────────────↓──┐         │    │
│  │        │         │   物理仿真引擎        │         │    │
│  │        └─────────┤  (50ms 循环)         │         │    │
│  │                  │  物料运动 · 传感器触发 │         │    │
│  │                  │  小车移动 · 称重变化   │         │    │
│  │                  └──────────────────────┘         │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

PLC Simulator 对上位机表现为一个标准的 Modbus TCP 从站，端口 1502（避免与真实 PLC 的 502 冲突）。

## 2. Modbus 地址映射表

### 线圈 (0xxxx) — 上位机 → 下位机写入（执行器命令）

| 地址 | 内容 | 说明 |
|------|------|------|
| 1001-1019 | 19条皮带启停 | 1=启动, 0=停止 |
| 2001-2007 | 7个中转斗开关 | 1=打开, 0=关闭 |
| 3001-3004 | 4个小车分料方向 | 1=左翻, 0=右翻 |
| 3005-3008 | 4个小车移动方向 | 1=正向, 0=反向 |
| 3009-3013 | 5个上料点出料开关 | 1=出料, 0=停止 |

### 离散输入 (1xxxx) — 下位机 → 上位机读取（传感器状态）

| 地址 | 内容 | 说明 |
|------|------|------|
| 1001-1020 | 20个接近开关 | 1=有料(触发), 0=无料 |
| 2001-2007 | 7个中转斗开关到位 | 1=未关到位(开/运动中), 0=关门到位 |
| 3001-3004 | 4个小车左极限 | 1=到达左极限, 0=未到达 |
| 3005-3008 | 4个小车右极限 | 1=到达右极限, 0=未到达 |
| 4001-4004 | 4个小车到位信号 | 1=已到达目标, 0=移动中 |
| 5001-5007 | 7个中转斗有料检测 | 1=有料, 0=无料 |

### 保持寄存器 (4xxxx) — 下位机 → 上位机读取（模拟量 / 位置值）

| 地址 | 内容 | 比例 | 说明 |
|------|------|------|------|
| 40051-40057 | 7个中转斗称重 | ×0.01t | 当前重量，单位 0.01 吨 |
| 40101-40104 | 4个小车当前位置 | ×1 | 1-7 (或更多) |
| 40201-40219 | 19条皮带当前速度 | ×0.1 m/s | 0=停止, 25=2.5m/s |

> **不在下位机的数据**：
> - 料仓料位 (40001-40028, 40301-40312) → Stock Management
> - 激光测距仪有料状态 → Stock Management
> - 这些由 Stock Management 直接发给 FeedingMaster 和 Upper Computer

## 3. 物理仿真引擎

### 3.1 皮带运行模拟

```
上位机写线圈 1001=1 (启动E1皮带)
  → PLC Simulator 收到
  → 设置 E1 状态: running=True, speed=2.5m/s
  → 50ms 循环: 累加运行时间

当物料到达传感器位置时:
  → 设置对应离散输入 = 1
  → 保持 200ms 后恢复 0
```

皮带与接近开关 (20个) 的对应关系：

```
E1  → S-E1   (距离起点 5%)
E2  → S-E2   (距离起点 5%)
E4  → S-E4   (距离起点 5%)
E5  → S-E5   (距离起点 5%)
E6  → S-E6   (距离起点 5%)
E7  → S-E7   (距离起点 5%)
E8  → S-E8   (距离起点 5%)
E9  → S-E9   (距离起点 5%)
E10 → S-E10  (距离起点 5%)
D1  → S-D1   (距离起点 5%)
D2  → S-D2   (距离起点 5%)
D2  → S-D2-2 (距离起点 80%)
D3  → S-D3   (距离起点 5%)
D4  → S-D4   (距离起点 5%)
D5  → S-D5   (距离起点 5%)
D6  → S-D6   (距离起点 5%)
D7  → S-D7   (距离起点 5%)
D8  → S-D8   (距离起点 5%)
D9  → S-D9   (距离起点 5%)
D13 → S-D13  (距离起点 5%)
```

### 3.2 上料点出料模拟

```
上位机写线圈 3009=1 (上料点1出料开关打开):
  → PLC Simulator: 上料点1 出料开关=开
  → 如果对应皮带也在运行 → 物料进入皮带
  → 每 500ms 生成一个物料

上位机写线圈 3009=0 (上料点1出料开关关闭):
  → 停止生成物料
```

5 个上料点对应关系：
```
线圈 3009 → feed1_1 (路线①)
线圈 3010 → feed1_2 (路线②)
线圈 3011 → feed2_1 (路线③)
线圈 3012 → feed2_2 (路线④/⑤)
线圈 3013 → feed3   (路线⑥)
```

### 3.3 中转斗模拟

**开关到位检测**：
```
上位机写线圈 2001=1 (打开hopper1):
  → PLC Simulator: hopper1 开始动作
  → 过渡 500ms 后: 斗完全打开
  → 离散输入 2001=1 (未关到位 = 已打开)

上位机写线圈 2001=0 (关闭hopper1):
  → PLC Simulator: hopper1 开始关闭
  → 过渡 500ms 后: 斗完全关闭
  → 离散输入 2001=0 (关门到位)
```

**有料检测**：
```
物料进入中转斗:
  → 离散输入 5001=1 (有料)

斗内物料全部排出:
  → 离散输入 5001=0 (无料)
```

**称重模拟**：
```
物料到达中转斗:
  → 累加保持寄存器 40051 (每次 +0.1t)
  → 更新离散输入 5001=1 (有料)

中转斗开关打开 + 下一皮带运行:
  → 物料流出 (每次 -0.1t)
  → 称重归零时: 离散输入 5001=0 (无料)
```

### 3.4 小车位置模拟

```
上位机写线圈 3005=1 (Cart1 正向移动):
  → PLC Simulator 每 2秒 移动 1 个位置
  → 更新保持寄存器 40101 (当前位置)
  → 到达目标时: 设置离散输入 4001=1 (到位信号)
  → 到达极限时: 设置离散输入 3001=1 (左极限) 或 3005=1 (右极限)
```

小车参数：
- Cart1 (D7): 行程 1-7, 速度 2s/格
- Cart2 (D8): 行程 1-7, 速度 2s/格
- Cart3 (D9): 行程 1-7, 速度 2s/格
- Cart4 (D5/D6): 行程 1-6, 速度 2s/格

### 3.5 分料方向传感器模拟

```
上位机写线圈 3001=1 (Cart1 左翻):
  → PLC Simulator 更新: Cart1 左翻
  → 通过保持寄存器 40101 的附加位反馈分料状态
  (或者新增离散输入地址)
```

## 4. 故障注入能力

PLC Simulator 支持通过配置文件注入故障，用于测试 Fault Diagnosis 模块：

```json
// plc_simulator/fault_config.json
{
  "sensors": {
    "S-E8": {"mode": "stuck_low"},         // 卡在低电平
    "S-D7": {"mode": "stuck_high"}         // 卡在高电平
  },
  "switches": {
    "hopper3": {"mode": "stuck_closed"}     // 斗开关卡在关
  },
  "weights": {
    "hopper1": {"mode": "offset", "value": 5.0}  // 称重偏差 5 吨
  }
}
```

## 5. 模块结构

```
plc_simulator/                          ← 新建
├── __init__.py
├── modbus_server.py                    ← Modbus TCP Server (:1502)
├── device_models.py                    ← 设备模型 (Belt/Hopper/Cart/Sensor)
├── physics_engine.py                   ← 物理仿真引擎 (50ms 循环)
├── fault_injector.py                   ← 故障注入
├── config.py                           ← 设备参数 + 传感器位置
├── fault_config.json                   ← 故障配置文件
└── main.py                             ← 启动入口
```

## 6. 核心接口

### modbus_server.py

```python
class PlcSimulatorServer:
    """PLC 模拟器 Modbus TCP Server"""
    
    def __init__(self, host='0.0.0.0', port=1502):
        self.host = host
        self.port = port
        self.coils = [False] * 2000          # 线圈
        self.discrete_inputs = [False] * 5000 # 离散输入
        self.holding_regs = [0] * 50000       # 保持寄存器
        
    def start(self):
        # 启动 Modbus TCP Server
        # 同步 coils/discrete_inputs/holding_regs 到 Modbus 数据存储
        
    def update_from_physics(self, physics_state):
        """从物理引擎更新 Modbus 寄存器"""
        for belt_id, belt in physics_state.belts.items():
            self.coils[belt.coil_addr] = belt.is_running
        for sensor_id, sensor in physics_state.sensors.items():
            self.discrete_inputs[sensor.di_addr] = sensor.is_active
        for hopper_id, hopper in physics_state.hoppers.items():
            self.holding_regs[hopper.hr_addr] = int(hopper.weight * 100)
        ...
```

### physics_engine.py

```python
class PhysicsEngine:
    """物理仿真引擎 — 模拟现场设备的物理行为"""
    
    def __init__(self):
        self.belts: Dict[str, BeltDevice] = {}
        self.hoppers: Dict[str, HopperDevice] = {}
        self.carts: Dict[str, CartDevice] = {}
        self.sensors: Dict[str, SensorDevice] = {}
        self.feed_points: Dict[str, FeedPointDevice] = {}
        
    def tick(self, delta_seconds: float, coil_states: Dict[int, bool]):
        """一个物理周期 (50ms)"""
        # 1. 读取线圈状态 → 更新设备
        # 2. 模拟物料在皮带上的运动
        # 3. 物料到达传感器位置 → 触发
        # 4. 小车位置更新
        # 5. 称重传感器更新
        # 6. 更新离散输入 + 保持寄存器
```

### main.py

```python
# 启动方式
python -m plc_simulator.main                # 默认 :1502
python -m plc_simulator.main --port 1502    # 指定端口
python -m plc_simulator.main --fault fault_config.json  # 注入故障

# 启动后输出:
# [PLC Sim] Modbus TCP Server 已启动 0.0.0.0:1502
# [PLC Sim] 物理引擎 50ms 循环已启动
# [PLC Sim] 等待上位机连接...
```

## 7. 联调时的数据流

```
                         FeedingMaster :8896
                              │
                    控制指令   │   传感器状态
                     (JSON)    │    (JSON)
                              ↓
┌─────────────────────────────────────────────┐
│              Upper Computer                  │
│                                             │
│  feedingmaster_client ←→ message_router     │
│                              │              │
│                     ┌────────↓────────┐     │
│                     │  modbus_bridge  │     │
│                     │  JSON↔Modbus   │     │
│                     └────────┬────────┘     │
└──────────────────────────────┼──────────────┘
                               │ Modbus TCP :1502
                               ↓
┌──────────────────────────────────────────────┐
│              PLC Simulator                    │
│                                              │
│  Modbus Server ←→ Physics Engine             │
│                                              │
│  线圈写入 → 解析命令 → 更新设备状态            │
│  设备状态 → 物理计算 → 更新离散输入/保持寄存器  │
└──────────────────────────────────────────────┘
```

## 8. 启动顺序（联调）

```
1. python -m scheduling.main          # 调度服务 :8891-8894
2. python -m stock_management.main    # 库存管理 :8895
3. python -m fault_diagnosis.main     # 故障诊断 :8897 (如已改造)
4. python -m plc_simulator.main       # PLC 模拟器 :1502
5. python -m feeding_master.main      # 上料主控 :8896
6. python main.py                     # 上位机 (HMI + Modbus 桥)
```

## 9. 调试特性

- **控制台面板**：实时打印线圈写入 / 传感器触发事件
- **Modbus 查询工具兼容**：可用 Modbus Poll 直接读写寄存器验证
- **Web 面板（可选）**：`localhost:1503` 显示所有设备状态（便于无 HMI 时调试）
- **故障注入热更新**：运行中修改 `fault_config.json`，自动生效

## 10. 实施建议

PLC Simulator 应该**在 FeedingMaster 和 Upper Computer 之后实施**，因为它需要明确的 Modbus 地址表。建议顺序：

1. FeedingMaster 完成 → 确定控制指令 JSON 格式
2. Upper Computer 的 modbus_bridge 完成 → 确定 JSON↔Modbus 映射
3. PLC Simulator 对照 Modbus 地址表实现
