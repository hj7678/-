# FeedingMaster ↔ 上位机 通信协议（完整版）

## 概述

| 项 | 值 |
|-----|-----|
| 传输层 | TCP |
| 地址 | `127.0.0.1:8896`（FM 监听） |
| 编码 | UTF-8 |
| 格式 | JSON Lines（每条消息以 `\n` 结尾） |
| 连接模型 | 上位机为客户端。FM 同时只接受一个连接，新连接自动断开旧连接。 |
| 通信模式 | 全双工 |

---

## 一、上行消息（上位机 → FM）

### 1.1 sensor_states — 传感器状态推送

频率：100ms（FM接管）/ 500ms（监控）

```json
{
  "type": "sensor_states",
  "data": {
    "proximity": {
      "S-E1": true, "S-E2": false, "S-E4": false, "S-E5": false,
      "S-E6": false, "S-E7": false, "S-E8": false, "S-E9": false,
      "S-E10": false,
      "S-D1": false, "S-D2": false, "S-D2-2": false, "S-D3": false,
      "S-D4": false, "S-D5": false,
      "S-D7": false, "S-D8": false, "S-D9": false, "S-D13": false
    },
    "hopper_states": {
      "hopper1": true, "hopper2": false, "hopper3": false,
      "hopper4": false, "hopper5": false, "hopper6": false, "hopper7": false
    },
    "hopper_weights": {
      "hopper1": 0.0, "hopper2": 0.0, "hopper3": 0.0,
      "hopper4": 0.0, "hopper5": 0.0, "hopper6": 0.0, "hopper7": 0.0
    },
    "cart_positions": {
      "Cart1": 1, "Cart2": 1, "Cart3": 1
    },
    "cart_divert": {
      "Cart1": [true, false],
      "Cart2": [true, false],
      "Cart3": [false, true]
    },
    "belt_states": {
      "E1": false, "E2": false, "E4": false, "E5": false,
      "E6": false, "E7": false, "E8": false, "E9": false, "E10": false,
      "D1": false, "D2": false, "D3": false, "D4": false, "D5": false,
      "D6": false, "D7": false, "D8": false, "D9": false, "D13": false
    },
    "belt_speeds": {
      "E1": 0.0, "E2": 0.0, "E4": 0.0, "E5": 0.0,
      "E6": 0.0, "E7": 0.0, "E8": 0.0, "E9": 0.0, "E10": 0.0,
      "D1": 0.0, "D2": 0.0, "D3": 0.0, "D4": 0.0, "D5": 0.0,
      "D6": 0.0, "D7": 0.0, "D8": 0.0, "D9": 0.0, "D13": 0.0
    },
    "cart4_position": 1,
    "cart4_is_moving": false,
    "active_routes": ["route1", "route5"],
    "route_states": {
      "route1": "feeding", "route2": "idle", "route3": "idle",
      "route4": "idle", "route5": "moving_to_target",
      "route6": "idle", "route7": "idle", "route8": "idle"
    },
    "scheduling_active": true,
    "route_targets": {
      "route1": "P1-1", "route5": "S3"
    },
    "route_cart_moving": {
      "route1": false, "route5": true
    }
  }
}
```

#### 字段详解

**`proximity`** — 接近开关传感器，`true`=物料遮挡（触发），`false`=无物料：

| ID | 所在皮带 |
|-----|---------|
| S-E1 | E1 |
| S-E2 | E2 |
| S-E4 | E4 |
| S-E5 | E5 |
| S-E6 | E6 |
| S-E7 | E7 |
| S-E8 | E8 |
| S-E9 | E9 |
| S-E10 | E10 |
| S-D1 | D1 |
| S-D2 | D2 |
| S-D2-2 | D2（80%处） |
| S-D3 | D3 |
| S-D4 | D4 |
| S-D5 | D5 |
| S-D7 | D7 |
| S-D8 | D8 |
| S-D9 | D9 |
| S-D13 | D13 |

**`hopper_states`** / **`hopper_weights`** — 7 个中转斗：

| ID | 名称 |
|-----|------|
| hopper1 | 中转斗1 |
| hopper2 | 中转斗2 |
| hopper3 | 中转斗3 |
| hopper4 | 中转斗4 |
| hopper5 | 中转斗5 |
| hopper6 | 中转斗6 |
| hopper7 | 中转斗7 |

`hopper_states` 值为 `true`=开，`false`=关。`hopper_weights` 为当前吨数（float）。

**`cart_positions`** — Cart1/2/3 物理位置（int, 1-7）：

| ID | 所在皮带 | 说明 |
|-----|---------|------|
| Cart1 | D7 | P1 配料站 |
| Cart2 | D8 | P2/P3 配料站 |
| Cart3 | D9 | P4 配料站 |

**`cart_divert`** — 分料传感器，`[左分料, 右分料]`，Cart1 永远 `[true,false]`，Cart2 可变，Cart3 永远 `[false,true]`。

**`belt_states`** / **`belt_speeds`** — 19 条皮带，`true`=运行中：

| 系列 | ID 列表 |
|------|---------|
| E 系列 | E1, E2, E4, E5, E6, E7, E8, E9, E10 |
| D 系列 | D1, D2, D3, D4, D5, D6, D7, D8, D9, D13 |

**`cart4_position`** — Cart4 物理位置（int, 1-6），D6 高位储料仓。

**`cart4_is_moving`** — Cart4 是否在 18s/格 物理移动中。

**`active_routes`** — 当前活跃路线（`string[]`），路线 ID: `route1` ~ `route8`。

**`route_states`** — 8 条路线状态（`string`），枚举值：

| 值 | 含义 |
|------|------|
| `idle` | 空闲 |
| `moving_to_target` | 小车驶向目标 |
| `feeding` | 正常上料 |
| `clearing` | 清空余料 |
| `waiting` | 清空完成，等待续料 |
| `standby` | 节能待机 |

**`scheduling_active`** — `bool`，UI"调度服务"按钮状态。

**`route_targets`** — 每条路线当前目标料仓 ID。P 仓格式 `P{列}-{行}`（如 `P1-1`），S 仓格式 `S{编号}`（如 `S3`，编号 1-12）。

**`route_cart_moving`** — 每条路线的小车是否在移动（`bool`）。

---

### 1.2 manual_start — 手动上料

```json
{"type": "manual_start", "bin_id": "P1-3", "route_id": "route1"}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `bin_id` | string | 目标料仓 |
| `route_id` | string | 路线 ID |

---

### 1.3 manual_stop — 手动停止

```json
{"type": "manual_stop", "route_id": "route1"}
```

---

### 1.4 emergency_stop — 急停

```json
{"type": "emergency_stop"}
```

---

## 二、下行消息（FM → 上位机）

### 2.1 command — 控制指令

频率：50ms

```json
{
  "type": "command",
  "commands": [
    {"device": "belt", "id": "E1", "action": "start"},
    {"device": "belt", "id": "D7", "action": "stop"},
    {"device": "hopper", "id": "hopper1", "action": "open"},
    {"device": "hopper", "id": "hopper3", "action": "close"},
    {"device": "cart", "id": "Cart1", "action": "move", "target": 3, "route_id": "route1"}
  ],
  "route_states": {
    "route1": {"state": "feeding", "target_bin": "P1-1", "cart_target": 1, "cart_moving": false},
    "route2": {"state": "idle"},
    "route3": {"state": "idle"},
    "route4": {"state": "idle"},
    "route5": {"state": "moving_to_target", "target_bin": "S3", "cart_target": 5, "cart_moving": true},
    "route6": {"state": "idle"},
    "route7": {"state": "idle"},
    "route8": {"state": "idle"}
  },
  "schedule": {
    "executing_bin": {"D6": "S3", "D7": "P1-1", "D8": "", "D9": ""},
    "sequences": {
      "D7": ["P1-2", "P1-3", "P1-4"],
      "D8": ["P2-1", "P2-2"],
      "D9": [],
      "D6": []
    }
  },
  "operation_log": [
    {"route_id": "route1", "state": "feeding", "msg": "路线route1 上料中 → P1-1", "target": "P1-1"}
  ]
}
```

#### 2.1.1 `commands` — 执行器指令

每条：`{"device": string, "id": string, "action": string, "target"?: int, "route_id"?: string}`

**皮带** (`device: "belt"`): `action`: `"start"` | `"stop"`。ID 同 1.1 的 19 条皮带。

**中转斗** (`device: "hopper"`): `action`: `"open"` | `"close"`。ID: `hopper1` ~ `hopper7`。

**小车** (`device: "cart"`): `action`: `"move"`。附加字段：`target`（目标位置 int），`route_id`（关联路线 string）。ID: `Cart1`, `Cart2`, `Cart3`, `Cart4`。

#### 2.1.2 `route_states` — 路线状态

每条路线一个对象，key 为路线 ID (`route1`~`route8`)：

| 字段 | 类型 | 说明 |
|------|------|------|
| `state` | string | 路线状态（枚举同 1.1） |
| `target_bin` | string | 当前目标料仓 |
| `cart_target` | int | 小车目标位置 |
| `cart_moving` | bool | 小车是否移动中 |

IDLE 状态的路线只含 `state` 字段（用于通知上位机移除路线）。

#### 2.1.3 `schedule` — 调度序列

| 字段 | 类型 | 说明 |
|------|------|------|
| `executing_bin` | `{string: string}` | 每条皮带 (D6/D7/D8/D9) 当前执行的料仓，空串=无 |
| `sequences` | `{string: [string]}` | 每条皮带的调度队列 |

#### 2.1.4 `operation_log` — 操作日志

仅在状态或位置变化时推送。每条：

| 字段 | 类型 | 说明 |
|------|------|------|
| `route_id` | string | 路线 ID |
| `state` | string | 当前状态 |
| `msg` | string | 日志文本（中文） |
| `target` | string | 目标料仓 |

---

## 三、路线与设备对应关系

### 路线配置（config.FEED_ROUTES）

| ID | 名称 | 皮带 | 斗 | 小车 | 终点皮带 |
|-----|------|------|-----|------|---------|
| route1 | ① | E1,E4,E8,E10,D7 | hopper1,hopper3,hopper4 | Cart1 | D7 |
| route2 | ② | E2,E4,E8,E10,D7 | hopper1,hopper3,hopper4 | Cart1 | D7 |
| route3 | ③ | E5,E8,E10,D7 | hopper1,hopper3,hopper4 | Cart1 | D7 |
| route4 | ④ | E6,E7,E9,D9 | hopper2,hopper6,hopper7 | Cart3 | D9 |
| route5 | ⑤ | E6,E7,E9,D5,D6 | hopper2,hopper6,hopper7 | Cart4 | D6 |
| route6 | ⑥ | D13,D2,D4,D8 | hopper5 | Cart2 | D8 |
| route7 | ⑦ | D1,D3,D9 | — | Cart3 | D9 |
| route8 | ⑧ | D4,D2,D8 | — | Cart2 | D8 |

### 小车→皮带

| 小车 | 皮带 | 配料站 |
|------|------|--------|
| Cart1 | D7 | P1 |
| Cart2 | D8 | P2/P3 |
| Cart3 | D9 | P4 |
| Cart4 | D6 | 高位储料仓 S1~S12 |

### 料仓 ID

- P 仓：`P1-1` ~ `P1-7`, `P2-1` ~ `P2-7`, `P3-1` ~ `P3-7`, `P4-1` ~ `P4-7`（28 个）
- S 仓：`S1` ~ `S12`（12 个，对应 6 列×2 行高位储料仓）

---

## 四、消息交换时序

```
上位机                               FM
  │                                   │
  │── TCP connect ──────────────────→│
  │                                   │
  │── sensor_states (100ms) ────────→│  推送传感器/皮带/小车/斗快照
  │                                   │  FM 处理 → 状态机 → 生成指令
  │←─ command (50ms) ───────────────│  皮带启停/斗开关/小车移动
  │   + route_states                  │  路线状态同步
  │   + schedule                      │  调度序列（HMI 显示）
  │   + operation_log                 │  操作日志（变化时）
  │                                   │
  │── manual_start ─────────────────→│  用户点击料仓手动上料
  │── manual_stop  ─────────────────→│  用户点击停止按钮
  │── emergency_stop ───────────────→│  急停按钮
```

---

## 五、子系统全景

```
┌──────────┐  料位写入(8895)   ┌──────────┐  调度请求(8891-94)  ┌──────────┐
│ 上位机    │ ────────────────→ │  Stock   │ ←─────────────── │ 调度引擎  │
│ (HMI)    │                   │ Management│                   │ 遗传算法  │
│ PyQt5    │ ←── 料位查询 ──── │ (8895)   │                   │ 序列优化  │
└────┬─────┘                   └──────────┘                   └──────────┘
     │                                                              │
     │ sensor_states ↕ commands (8896)                              │
     │                                                              │
┌────┴─────┐                                                       │
│ Feeding  │ ←──── 料位查询(8895) ─────────────────────────────────┘
│ Master   │
│ 控制大脑  │
│ 状态机   │
│ 执行器   │
└──────────┘
```
