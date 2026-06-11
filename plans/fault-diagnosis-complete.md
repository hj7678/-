# 故障诊断系统完整逻辑梳理

## 一、系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      仿真软件 (模拟端)                        │
│                                                             │
│  ┌───────────────────────┐    ┌──────────────────────────┐ │
│  │ SensorFaultDiagnosis  │    │ ControlStrategyGenerator  │ │
│  │ (故障模式设置/UI显示)  │    │ (数据生成 + fault_overrides)│ │
│  └───────┬───────────────┘    └───────────┬──────────────┘ │
│          │                                │                 │
│          │  set_fault_mode()               │ generate_all_data()
│          │  同步更新 fault_overrides ──────→│   ↓             │
│          │                                │ _apply_fault_overrides()
│          │                                │ write_all_sensors()
│          │                                └───────┬───────────┘ │
│          │                                        │             │
│          │                               SensorDataManager      │
│          │                               (→ generate_data.json) │
│          │                                        │             │
│          │                                read_all_sensors()    │
│          │                                        │             │
│  ┌───────┴────────────────────────────────────────┴──────────┐ │
│  │                 _update_tcp_data()                         │ │
│  │  发送: sensors / hoppers / conveyors / route_states / ...  │ │
│  └─────────────────────────┬─────────────────────────────────┘ │
│                            │                                   │
└────────────────────────────┼───────────────────────────────────┘
                             │ TCP (127.0.0.1:8890)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                  TCP 诊断服务 (独立进程)                       │
│                                                             │
│  JSON 数据 → TcpDataAdapter → SystemSnapshot                 │
│                            ↓                                 │
│                     DiagnosisEngine.diagnose()               │
│                            ↓                                 │
│                     诊断结果 → JSON 响应                      │
└─────────────────────────────────────────────────────────────┘
```

两套诊断并行：
- **本地诊断**：`FaultDiagnosisAdapter` 直接读取内存对象 → `DiagnosisEngine`
- **TCP 诊断**：仿真端发 JSON → TCP 服务端 `TcpDataAdapter` → `DiagnosisEngine`

---

## 二、DiagnosisEngine 入口

`diagnose(snapshot)` → 每次调用产出 `List[DiagnosisResult]`，按 `sensor_id:fault_type` 键去重（30s 冷却），按置信度降序排列。

调用顺序（6 类方法，全部执行）：
1. `_diagnose_proximity` — 接近开关诊断（4 阶段）
2. `_diagnose_hopper_switch` — 中转斗开关诊断
3. `_diagnose_hopper_weight` — 中转斗称重诊断
4. `_diagnose_carts` — 小车传感器诊断
5. `_diagnose_conveyors` — 皮带转速诊断
6. `_diagnose_cross_sensor` — 跨传感器一致性诊断

---

## 三、A 类——接近开关诊断（按路线状态分 4 阶段）

仅对 **活跃路线**（`snapshot.active_route_ids`）进行诊断，按路线当前状态分发：

| 阶段 | 方法 | 触发条件 |
|------|------|----------|
| moving_to_target | `_check_moving_stage` | 小车正在移动到目标位置 |
| feeding | `_check_feeding_stage` | 正常上料中 |
| clearing | `_check_clearing_stage` | 上料完毕，清空余料 |
| waiting | `_check_waiting_stage` | 上料完成，等待下一轮 |
| idle | 不检测 | 路线空闲 |

### 阶段1：小车移动 `_check_moving_stage`

| 检查对象 | 规则 | fault_type | conf |
|----------|------|------------|------|
| 路线所有接近开关 | 必须全 false，否则 → 卡高 | `stuck_high` | 0.85 |
| 路线所有中转斗开关 | 必须全 false，否则 → 卡开 | `hopper_switch_stuck_open` | 0.85 |
| 非终点皮带 | 必须运行，否则 → 异常 | `conveyor_should_run` | 0.85 |
| 终点皮带 | 必须停止，否则 → 异常 | `conveyor_should_stop` | 0.85 |

### 阶段2：正常上料 `_check_feeding_stage`

| 检查对象 | 规则 | fault_type | conf |
|----------|------|------------|------|
| 路线全部皮带 | 必须运行 | `conveyor_should_run` | 0.85 |
| 路线所有中转斗开关 | 必须为 true（打开） | `hopper_switch_stuck_closed` | 0.80 |
| 路线所有中转斗称重 | 必须 = 0（刚开斗） | `weight_nonzero` | 0.75 |
| **接近开关（中间位置）卡低** | 本传感器 false + 上游全 true + 下游全 true | `stuck_low` | 0.90 |
| **接近开关（末尾位置）卡低** | 本传感器 false + 上游全 true + 上游点亮超过 30s | `stuck_low` | 0.85 |
| **接近开关（中间位置）卡高** | 本传感器 true + 上游全 false + 下游全 false | `stuck_high` | 0.90 |
| **接近开关（末尾位置）卡高** | 本传感器 true + ≥2 个上游为 false | `stuck_high` | 0.85 |

**关键辅助方法**：
- `_get_upstream_sensors(route, sid, snapshot)` — 获取路线上当前传感器之前的所有传感器
- `_get_downstream_sensors(route, sid, snapshot)` — 获取之后的所有传感器
- `_is_last_sensor(route, sid)` — 判断是否为路线最后一个接近开关
- `_min_neighbor_true_duration_ms(neighbor_ids, ts)` — 邻居连续点亮的最短时长

### 阶段3：清空余料 `_check_clearing_stage`

| 检查对象 | 规则 | fault_type | conf |
|----------|------|------------|------|
| 路线全部皮带 | 必须运行 | `conveyor_should_run` | 0.85 |
| 路线所有中转斗开关 | 必须全 false | `hopper_switch_stuck_open` | 0.85 |
| 接近开关 | 点亮时间不能超过 5s，超时 → 卡高 | `stuck_high` | 0.85 |

> 称重传感器在 clearing 阶段不参与诊断（已移除）。

### 阶段4：上料完成 `_check_waiting_stage`

| 检查对象 | 规则 | fault_type | conf |
|----------|------|------------|------|
| 非终点皮带 | 必须运行 | `conveyor_should_run` | 0.85 |
| 终点皮带 | 必须停止 | `conveyor_should_stop` | 0.85 |
| 路线所有接近开关 | 必须全 false，否则 → 卡高 | `stuck_high` | 0.85 |
| 路线所有中转斗开关 | 必须全 false，否则 → 卡开 | `hopper_switch_stuck_open` | 0.85 |
| 中转斗称重 | 3s 内波动幅度 > 0.05t → 称重故障 | `weight_volatile` | 0.75 |

---

## 四、B 类——中转斗开关诊断 `_diagnose_hopper_switch`

**独立运行，不限路线状态。** 遍历所有中转斗，3 条规则：

| # | 规则 | fault_type | conf |
|---|------|------------|------|
| 1 | 开关显示开 + 称重持续增加(>0.05 t/s) + 下游无物料 → **开关实际卡关** | `hopper_switch_stuck_closed` | 0.85 |
| 2 | 开关显示关 + 输入皮带运行 + 下游有物料 + 称重≈0 + 持续 3s → **开关实际卡开** | `hopper_switch_stuck_open` | 0.85 |
| 3 | FEEDING 状态下开关为关 | `hopper_switch_unexpected` | 0.50 |

---

## 五、C 类——中转斗称重诊断 `_diagnose_hopper_weight`

**独立运行，不限路线状态。** 遍历所有中转斗，4 条规则：

| # | 规则 | fault_type | conf |
|---|------|------------|------|
| 1a | 开关关 + 称重变化率 > 0.2925 t/s (`FILL_RATE*1.5`) → 变化率异常 | `weight_rate_anomaly` | 0.70 |
| 1b | 开关关 + 称重变化率 < -0.01 t/s → 异常下降 | `weight_decreasing` | 0.70 |
| 2 | 开关关 + 输入皮带运行 + 有至少 1s 历史 + 2s 内称重无变化 + 路线 FEEDING → 称重卡住 | `weight_stuck` | 0.80 |
| 3 | 称重 > 0.2t 且 3s 内波动 > 均值的 20% → 信号不稳定 | `weight_volatile` | 0.60 |
| 4 | 开关开 + 称重 > 0.1t + 有至少 1s 历史 + 未下降 → 称重异常非零 | `weight_nonzero_switch_open` | 0.65 |

---

## 六、D 类——小车传感器诊断 `_diagnose_carts`

**独立运行，不限路线状态。** 遍历 Cart1-4：

| # | 规则 | fault_type | conf |
|---|------|------------|------|
| 1 | 左右极限同时为 true（互斥） | `limit_mutual_exclusion` | 0.95 |
| 2 | 左右分料同时为 true（互斥） | `divert_mutual_exclusion` | 0.95 |
| 3 | 无活跃路线但分料传感器激活 | `divert_no_task` | 0.50 |

---

## 七、E 类——皮带转速诊断 `_diagnose_conveyors`

**独立运行，不限路线状态。** 所有 3 条规则均需持续 10s 才触发：

| # | 规则 | fault_type | conf |
|---|------|------------|------|
| 1 | 皮带运行 + 转速为 0 持续 10s | `speed_zero_while_running` | 0.90 |
| 2 | 皮带停止 + 转速非 0 持续 10s | `speed_nonzero_while_stopped` | 0.90 |
| 3 | 皮带运行 + 转速偏离均值 > 30% 持续 10s | `speed_volatile` | 0.50 |

---

## 八、F 类——跨传感器一致性诊断 `_diagnose_cross_sensor`

**仅检查 FEEDING 状态** 的活跃路线。3 条规则：

| # | 规则 | fault_type | conf |
|---|------|------------|------|
| 1 | 路线全部接近开关为 false + 皮带在运行 → 全传感器失效 | `route_all_sensors_false` | 0.55 |
| 2 | 开关显示开 + 称重持续增加(>0.05 t/s) → 开关-称重矛盾 | `switch_weight_conflict` | 0.75 |
| 3 | 下游传感器先于上游触发（跳过第一个传感器）→ 时序异常 | `trigger_order_anomaly` | 0.70 |

---

## 九、新旧方法的重叠关系

新阶段方法（A 类）和旧独立方法（B/C/F 类）并行运行，存在部分重叠：

| 检测内容 | A 类阶段方法 | B/C/F 旧方法 | 关系 |
|----------|-------------|-------------|------|
| feeding 开关未打开 | `hopper_switch_stuck_closed` (0.80) | B-rule3 `hopper_switch_unexpected` (0.50) | 不同 fault_type，都会报 |
| feeding 称重非零 | `weight_nonzero` (0.75) | C-rule4 `weight_nonzero_switch_open` (0.65) | 不同 fault_type，都会报 |
| waiting 称重波动 | `weight_volatile` (0.75) | C-rule3 `weight_volatile` (0.60) | 相同 fault_type，去重按首次报 |
| 开关-称重矛盾 | — | F-rule2 `switch_weight_conflict` (0.75) | 仅旧方法 |

去重机制：30s 冷却期内同 `sensor_id:fault_type` 不重复报告。不同 fault_type 的重复算是"多角度佐证"。

---

## 十、用户故障模拟系统 `SensorFaultDiagnosis`

路径：UI → `SimulationController.set_fault_mode()` → 同时写入两处：
1. `SensorFaultDiagnosis` — 控制 UI 显示（`sensor.is_active`）
2. `ControlStrategyGenerator.fault_overrides` — 控制 JSON 数据输出

### 支持的故障模式

| 模式 | 枚举值 | 效果 |
|------|--------|------|
| 关闭 | `OFF` | 清除故障 |
| 卡低电平 | `STUCK_LOW` | 传感器始终为 false |
| 卡高电平 | `STUCK_HIGH` | 传感器始终为 true |
| 随机 | `RANDOM` | 每次随机 0/1 |
| 灵敏度降低 | `SENSITIVITY_LOSS` | 真实 true 时有 30% 概率漏报为 false |
| 响应延迟 | `RESPONSE_DELAY` | 状态变化延迟 500ms |
| 间歇性 | `INTERMITTENT` | 每 2s 切换是否故障，50% 保持旧值 |

### 数据写入链路（已修复）

```
_generate_proximity_sensor_data()
  → 根据物料位置计算传感器物理状态
  → _apply_fault_overrides(sensor_values)  ← 检查 fault_overrides 字典
  → data_manager.write_all_sensors(final_values)
      → write_sensor() → _apply_sensor_fault()  ← 检查 _sensor_faults 字典（另一套）
      → 写入 generate_data.json
```

现在 `set_fault_mode()` 同步更新 `fault_overrides`，确保故障覆盖值写入 JSON。

---

## 十一、常量一览

| 常量 | 值 | 用途 |
|------|-----|------|
| `FILL_RATE` | 0.195 t/s | 称重变化率基准 |
| `REPORT_COOLDOWN` | 30.0 s | 同故障重复报告冷却 |
| `WEIGHT_HISTORY_SECONDS` | 5.0 s | 称重历史窗口 |
| `CONVEYOR_FAULT_DURATION` | 10.0 s | 皮带故障需持续时长 |
| `HOPPER_SWITCH_STUCK_OPEN_DURATION` | 3.0 s | 开关卡开需持续时长 |
| `FEEDING_UPSTREAM_LIT_TIMEOUT_S` | 30.0 s | feeding 末尾传感器上游点亮超时 |
| `CLEARING_PROXIMITY_MAX_LIT_S` | 5.0 s | clearing 接近开关最大点亮时长 |
| `WAITING_WEIGHT_VOLATILITY_THRESHOLD` | 0.05 t | waiting 称重波动阈值 |
| `DIAGNOSIS_INTERVAL_MS` | 500 ms | TCP 诊断客户端发送间隔 |
