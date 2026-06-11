# 上料主控系统 — 五模块独立架构方案

## 1. 系统拓扑

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         工控机集群 (可分布部署)                             │
│                                                                          │
│  ┌─────────────────────┐              ┌─────────────────────┐            │
│  │  Stock Management   │  料位数据     │   Scheduling Engine │            │
│  │  料仓库存管理        │ ──── :8895 → │   调度引擎 (已有)    │            │
│  │                     │              │                     │            │
│  │  28+12仓实时料位    │              │  遗传算法优化        │            │
│  │  消耗+补充模拟      │              │  :8891-8894         │            │
│  └─────────┬───────────┘              └──────────┬──────────┘            │
│            │ 料位推送                             ↑ 调度请求              │
│            ↓                                      │ 调度结果              │
│  ┌──────────────────────────────────────────────────────────┐            │
│  │                    FeedingMaster (:8896)                  │            │
│  │                      上料主控 (控制大脑)                    │            │
│  │                                                          │            │
│  │  ┌──────────┐  ┌───────────┐  ┌───────────┐             │            │
│  │  │ 状态转换  │  │ 路线状态机 │  │ 执行器规则 │             │            │
│  │  │ 引擎     │  │           │  │ 引擎      │             │            │
│  │  └──────────┘  └───────────┘  └───────────┘             │            │
│  │                                                          │            │
│  │  输入: 料位 + 传感器 + 调度结果 → 输出: 控制指令            │            │
│  └────────┬────────────────────┬────────────────────────────┘            │
│           │ 控制指令            │ 状态快照                                 │
│           ↓                    ↓                                          │
│  ┌────────────────┐   ┌──────────────────────────┐                       │
│  │ Upper Computer │   │  Fault Diagnosis (:8897) │                       │
│  │ 上位机 (HMI)    │   │  故障诊断引擎 (已有逻辑)   │                       │
│  │                │   │                          │                       │
│  │ 界面 + 动画     │   │  6类规则诊断              │                       │
│  │ 消息路由        │   │  120帧历史队列            │                       │
│  │ Modbus 桥      │   │  输出诊断结果→上位机       │                       │
│  └───────┬────────┘   └──────────────────────────┘                       │
│          │ Modbus TCP :502                                               │
│          ↓                                                               │
│  ┌──────────────────────────────────────────────────────┐                │
│  │                    PLC (下位机)                        │                │
│  │                    纯 I/O，零逻辑                      │                │
│  │                                                      │                │
│  │  输入: 接近开关·称重·料位计·编码器                      │                │
│  │  输出: 接触器(皮带)·电磁阀(斗)·变频器(小车)              │                │
│  └──────────────────────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────────────────────┘
```

## 2. 五个模块的职责与接口

### 2.1 Stock Management (料仓库存管理) — :8895

**职责**：维护 40 个料仓的实时料位数据（28 配料站 + 12 高位仓）。

**仿真模式**：每 1 秒按各仓消耗速率递减，feeding 期间按 0.195 t/s 递增对应料仓。

**对接方**：FeedingMaster、Upper Computer

**协议**：
```json
// 请求
{"action": "get_levels", "bin_ids": ["P1-1", "P1-2"]}
// 响应
{"bins": [{"bin_id": "P1-1", "level_tons": 45.2, "level_pct": 41.1, "capacity": 110.0}]}

// 推送 (主动)
{"event": "level_update", "bin_id": "P1-1", "level_tons": 45.3, "level_pct": 41.2}
```

---

### 2.2 Scheduling Engine (调度引擎) — :8891-8894 [已有]

**职责**：接收料仓状态 + 小车位置 + 分料方向，运行遗传算法，返回最优上料序列。

**对接方**：FeedingMaster（唯一调用方）

**协议**（已有，不变）：
```json
// 请求 → Scheduling Server
{"timestamp": "...", "belt_id": "D8", "boost_mode": false,
 "bins": [{"bin_id":"P2-1","stock":45.2,"consumption_rate":0.01,...}],
 "cart_position": 3, "left_divert": false, "right_divert": true}

// 响应 ← Scheduling Server
{"sequence": ["P2-1","P2-2",...], "is_feasible": true, "steps": [...], ...}
```

**FeedingMaster 传入的数据**（替代当前 `simulation_controller._build_bins_for_scheduling()`）：
- 料位数据 → 来自 Stock Management
- 小车位置 → 来自 Upper Computer 转发的 PLC 传感器状态
- 分料器状态 → 同上
- boost_mode → FeedingMaster 根据是否有料仓低于紧急阈值判定

---

### 2.3 Fault Diagnosis (故障诊断) — :8897

**职责**：接收 FeedingMaster 发来的**完整状态快照**，运行六类诊断规则，输出诊断结果。

**对接方**：
- FeedingMaster → 发送状态快照（每 500ms）
- Upper Computer → 接收诊断结果（显示在故障面板）

**状态快照协议**（FeedingMaster → Diagnosis :8897）：
```json
{
  "timestamp": "2026-06-11 17:30:00.500",
  "active_routes": {
    "route3": {
      "state": "feeding",
      "target_bin": "P1-1",
      "strategy": "reverse"
    }
  },
  "belts": [
    {"id": "E5",  "is_running": true,  "speed": 2.5},
    {"id": "E8",  "is_running": true,  "speed": 2.5},
    {"id": "E10", "is_running": true,  "speed": 2.5},
    {"id": "D7",  "is_running": false, "speed": 0}
  ],
  "sensors": [
    {"id": "S-E5",  "is_active": true,  "conveyor": "E5"},
    {"id": "S-E8",  "is_active": false, "conveyor": "E8"},
    {"id": "S-E10", "is_active": true,  "conveyor": "E10"}
  ],
  "hoppers": [
    {"id": "hopper1", "is_open": true,  "weight": 2.3, "stored_count": 23},
    {"id": "hopper3", "is_open": true,  "weight": 1.1, "stored_count": 11}
  ],
  "carts": [
    {"id": "Cart1", "position": 1, "target": 1, "moving": false, "divert": [false, false]}
  ]
}
```

**诊断结果协议**（Diagnosis → Upper Computer :8897 回调）：
```json
{
  "timestamp": "2026-06-11 17:30:01.000",
  "results": [
    {"sensor_id": "S-E8", "fault_type": "stuck_low", "confidence": 0.92,
     "description": "S-E8 在FEEDING阶段持续低电平，与上游S-E5矛盾"},
    {"belt_id": "E10", "fault_type": "speed_zero", "confidence": 0.85,
     "description": "E10皮带运行中传感器无触发"}
  ]
}
```

---

### 2.4 FeedingMaster (上料主控) — :8896 [核心大脑]

**职责**：串联所有模块，是唯一的控制逻辑承载者。

**输入源**：
| 数据 | 来源 | 协议 |
|------|------|------|
| 料仓料位 | Stock Management :8895 | TCP JSON pull |
| 调度序列 | Scheduling Engine :8891-8894 | TCP JSON request/response |
| 传感器状态 | Upper Computer :8896 | TCP JSON push |

**输出目标**：
| 数据 | 目标 | 协议 |
|------|------|------|
| 控制指令 | Upper Computer :8896 | TCP JSON push |
| 状态快照 | Fault Diagnosis :8897 | TCP JSON push (每 500ms) |
| 调度请求 | Scheduling Engine :8891-8894 | TCP JSON request |

**内部处理循环**（50ms 周期）：
```
1. 拉取料位数据 (Stock Management)
2. 接收传感器状态 (Upper Computer 转发)
3. 物料追踪更新
4. 状态转换引擎判定 (FEEDING→CLEARING 等)
5. 路线状态机处理
6. 执行器规则引擎 → 生成控制指令
7. 推送控制指令 → Upper Computer
8. 每500ms: 构建状态快照 → Fault Diagnosis
9. 皮带空闲时: 发送调度请求 → Scheduling Engine
```

**内部模块**（从当前 `plc_runtime/` 搬移并演进）：
```
feeding_master/
├── models.py              ← 数据模型
├── actuator.py            ← 执行器规则引擎
├── material_tracker.py    ← 物料追踪
├── master_controller.py   ← 主控制循环 (核心)
├── tcp_server.py          ← TCP :8896 (与 Upper Computer 通信)
├── stock_client.py        ← Stock Management 客户端
├── sched_client.py        ← Scheduling Engine 客户端
├── diagnosis_client.py    ← Fault Diagnosis 客户端
└── main.py                ← 启动入口
```

---

### 2.5 Upper Computer (上位机) — HMI + 消息路由

**职责**：
1. **HMI** — PyQt5 界面，状态显示，皮带动画，料位柱状图
2. **消息路由** — FeedingMaster ↔ PLC 双向桥接
3. **Modbus 桥** — JSON 控制指令 → Modbus 线圈 / 离散输入 → JSON 传感器状态

**接收的数据**：
| 来源 | 数据 | 用途 |
|------|------|------|
| FeedingMaster :8896 | 控制指令 | 转 Modbus → PLC |
| Stock Management :8895 | 料位数据 | HMI 显示 |
| Fault Diagnosis :8897 | 诊断结果 | 故障面板显示 |
| PLC Modbus :502 | 传感器状态 | 转发 → FeedingMaster |

**不包含任何控制逻辑**——全部交给 FeedingMaster。

**内部模块**：
```
controllers/upper_computer/
├── message_router.py      ← 消息路由引擎
├── modbus_bridge.py       ← JSON ↔ Modbus 转换
├── feedingmaster_client.py ← FeedingMaster 客户端
├── stock_client.py        ← Stock Management 客户端
└── diagnosis_listener.py  ← 诊断结果监听
```

---

## 3. 完整数据流图

```
                         ┌─────────────────────┐
                         │  Stock Management   │
                         │       :8895         │
                         └──┬────────────┬─────┘
               料位数据      │            │ 料位推送(显示)
                            ↓            ↓
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Scheduling  │    │ FeedingMaster│    │    Upper     │
│   Engine     │    │    :8896     │    │  Computer    │
│ :8891-8894   │    │              │    │   (HMI)      │
│              │    │  控制大脑     │    │              │
│  遗传算法    │    │  状态机      │    │  界面+路由    │
│  序列优化    │    │  指令生成    │    │  Modbus桥    │
└──────┬───────┘    └──┬───┬───┬──┘    └──────┬───────┘
       ↑               │   │   │              │
       │ 调度请求       │   │   │ 状态快照     │ Modbus :502
       │ (料位+车位     │   │   │ (500ms)      │
       │  +分料方向)    │   │   ↓              ↓
       │               │   │ ┌──────────┐  ┌──────────┐
       └───────────────┘   │ │  Fault   │  │   PLC    │
                           │ │Diagnosis │  │  下位机   │
                           │ │  :8897   │  │  纯I/O   │
                           │ │          │  └──────────┘
                           │ │ 诊断结果 ──→ Upper Computer
                           │ └──────────┘
                           │
                           │ 控制指令 → Upper Computer
                           └───────────────────────────
```

## 4. 端口分配总表

| 端口 | 服务 | 协议 | 通信方 |
|------|------|------|--------|
| :8891 | Scheduling D7 | TCP JSON | FeedingMaster ↔ Scheduler |
| :8892 | Scheduling D8 | TCP JSON | FeedingMaster ↔ Scheduler |
| :8893 | Scheduling D9 | TCP JSON | FeedingMaster ↔ Scheduler |
| :8894 | Scheduling D6 | TCP JSON | FeedingMaster ↔ Scheduler |
| :8895 | Stock Management | TCP JSON | FeedingMaster + Upper Computer |
| :8896 | FeedingMaster | TCP JSON | Upper Computer |
| :8897 | Fault Diagnosis | TCP JSON | FeedingMaster → Diag / Diag → Upper |
| :502  | PLC Modbus | Modbus TCP | Upper Computer ↔ PLC |

## 5. 与当前代码的对应关系

### 需要新建

```
stock_management/                  ← 新建
feeding_master/                    ← 新建 (从 plc_runtime/ 搬移核心代码)
controllers/upper_computer/        ← 新建
```

### 需要改造

```
controllers/simulation_controller.py  ← 删除控制逻辑，仅保留 HMI
controllers/plc_runtime/              ← 删除 (合并到 feeding_master/)
fault_diagnosis/                       ← 已有逻辑，加 TCP server :8897
scheduling/                            ← 不变 (已是独立服务)
```

### 需要新增的 TCP Server

```
scheduling/server.py                  ← 已有
stock_management/tcp_server.py        ← 新建 :8895
feeding_master/tcp_server.py          ← 新建 :8896
fault_diagnosis/server.py             ← 新建 :8897
```

## 6. 实施路径

### Phase 1: Stock Management 模块
- 创建 `stock_management/`，独立运行
- 实现料仓数据模型 + 消耗模拟 + TCP server :8895

### Phase 2: FeedingMaster 模块
- 从 `plc_runtime/` 搬移 models/actuator/material_tracker
- 实现 `master_controller.py` 主循环
- 实现各客户端 (stock/sched/diagnosis)
- 实现 TCP server :8896

### Phase 3: Fault Diagnosis Server
- 在 `fault_diagnosis/` 现有逻辑上包装 TCP server :8897
- 接收状态快照 → 运行诊断规则 → 回传结果

### Phase 4: Upper Computer 改造
- 创建 `controllers/upper_computer/`
- 实现消息路由 + Modbus 桥
- simulation_controller.py 瘦身为纯 HMI

### Phase 5: 端到端联调
- 仿真模式全链路验证
- Modbus 模式对接 PLC
