# 接近开关故障诊断逻辑重构

## 问题

当前诊断引擎只在 `FEEDING` 状态下诊断，不考虑上料阶段上下文，导致"相邻传感器均点亮但本传感器点亮"时误判为卡高电平。

## 需求

诊断需要结合**路线状态**（上料阶段）来判断，4 个阶段各有规则：

### 阶段 1：小车移动 (moving_to_target)
| 检查项 | 规则 | 故障类型 |
|--------|------|----------|
| 路线所有接近开关 | 必须全部 false | 否则卡高 |
| 皮带运行状态 | 非终点皮带运行，终点皮带停止 | 皮带异常 |
| 路线所有中转斗开关 | 必须全部 false | 开关卡开 |

### 阶段 2：正常上料 (feeding)
| 检查项 | 规则 | 故障类型 |
|--------|------|----------|
| 中转斗开关 + 称重 | 开关必须 true 且称重 = 0 | 开关故障 / 称重故障 |
| 接近开关（中间位置）| 上游 true + 下游 true + 本传感器 false | 卡低 |
| 接近开关（末尾位置）| 上游点亮超过 30s 本传感器仍未点亮 | 卡低 |
| 接近开关（中间位置）| 上游 false + 下游 false + 本传感器 true | 卡高 |
| 接近开关（末尾位置）| ≥2 个上游传感器未点亮但本传感器已点亮 | 卡高 |

### 阶段 3：清空余料 (clearing)
| 检查项 | 规则 | 故障类型 |
|--------|------|----------|
| 中转斗开关 | 必须全部 false | 开关卡开 |
| 称重传感器 | 值 > 0 不能持续超过 3s | 称重故障 |
| 接近开关 | 点亮时间不能超过 5s | 卡高 |

### 阶段 4：上料完成 (waiting)
| 检查项 | 规则 | 故障类型 |
|--------|------|----------|
| 接近开关 | 必须全部 false | 卡高 |
| 中转斗开关 | 必须全部 false | 开关卡开 |
| 称重传感器 | 值必须保持稳定（波动 → 故障）| 称重故障 |

## 实现方案

修改 `fault_diagnosis/engine.py`，将 `_diagnose_proximity` 拆分为按阶段分派：

```
_diagnose_proximity(snapshot)
  → for each active route:
      switch route.state:
        MOVING_TO_TARGET → _check_moving_stage()
        FEEDING         → _check_feeding_stage()
        CLEARING        → _check_clearing_stage()
        WAITING         → _check_waiting_stage()
```

### 修改文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `fault_diagnosis/engine.py` | 重写 | 4 阶段规则引擎 |

### 需要新增的辅助方法

- `_get_upstream_sensors(route, sid)` — 获取上游传感器列表
- `_get_downstream_sensors(route, sid)` — 获取下游传感器列表
- `_is_last_sensor(route, sid)` — 判断是否为路线最后一个传感器
- `_upstream_lit_duration(route, sid, now)` — 上游传感器连续点亮时长
- `_weight_positive_duration(hid, now)` — 称重 > 0 持续时长
- `_proximity_lit_duration(sid, now)` — 接近开关点亮持续时长

### 常量

```python
CLEARING_PROXIMITY_MAX_LIT_S = 5.0    # 清空阶段接近开关最大点亮时长
CLEARING_WEIGHT_MAX_POSITIVE_S = 3.0   # 清空阶段称重 > 0 最大持续时长
FEEDING_UPSTREAM_LIT_TIMEOUT_S = 30.0  # feeding 阶段上游点亮超时判卡低
```

## 验证

1. `python main.py` 启动仿真
2. 手动启动一条路线，观察各阶段诊断输出
3. 模拟故障场景（如手动关闭接近开关）验证阶段特定规则
