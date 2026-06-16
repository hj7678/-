# 纯HMI上位机 — 分离方案

## 目标

在现有代码不动的前提下，新建 `upper_hmi/` 模块，作为**纯物理仿真 + HMI 显示**的上位机。启动即为 FM 接管模式，不包含任何决策逻辑。

## 模块结构

```
upper_hmi/
├── __init__.py
├── main.py                  ← 启动入口 (替代 main.py)
├── hmi_window.py            ← 主窗口 (移植自 main_window.py, 裁剪)
├── physics_engine.py        ← 物理引擎 (移植自 simulation_controller 物理部分)
├── simulation_view.py       ← 皮带动画/料仓显示 (复用现有 views/)
└── bridge.py                ← 桥接封装 (FM连接 + Stock连接)
```

## 与现有仿真 controller 的对比

| 组件 | 现有 simulation_controller | 新 physics_engine |
|------|--------------------------|-------------------|
| _update_materials | ✅ | ✅ 移植 |
| _update_sensors | ✅ | ✅ 移植 |
| _update_hoppers | ✅ | ✅ 移植 |
| _update_cart_positions | ✅ | ✅ 移植 (FM接管时teleport) |
| _spawn_materials | ✅ | ✅ 移植 |
| _update_bin_consumption | ✅ | ✅ 移植 |
| _check_level_thresholds | ✅ | ❌ 删除 (FM负责) |
| _check_clearing_completion | ✅ | ❌ 删除 |
| _check_auto_feed_idle | ✅ | ❌ 删除 |
| _request_immediate_scheduling | ✅ | ❌ 删除 |
| _on_tcp_schedule_received | ✅ | ❌ 删除 |
| _resolve_clearing_strategy | ✅ | ❌ 删除 |
| start_tcp_scheduling | ✅ | ❌ 删除 |
| IOBus/Modbus支持 | ✅ | ❌ 删除 (FM已处理) |
| bridge 通信 | 可选手动 | 强制自动 |

## 数据流

```
Stock :8895 ──料位──→ FeedingMaster :8896 ──指令──→ upper_hmi
                                                    (纯物理+HMI)
upper_hmi ──传感器状态──→ FeedingMaster
upper_hmi ──料位推送──→ Stock :8895
```

## HMI 裁剪

只保留 UI 面板的必要部分：
- 顶部按钮栏：保留 调度服务/桥接控制
- 皮带动画画布
- 料位柱状图
- 状态面板（传感器/斗/小车）
- 路线状态显示
- 运行日志

移除：
- 控制面板中的手动操作按钮（由FM指令驱动）
- 调度序列显示（FM自己管）
- 故障诊断面板（保留显示，移除触发逻辑）

## 启动方式

```bash
# 终端1: python -m stock_management.main
# 终端2: python -m scheduling.main
# 终端3: python -m feeding_master.main
# 终端4: python -m upper_hmi.main          ← 新上位机

# 或者保留原仿真用于对比:
# 终端4: python main.py                     ← 原仿真
```

## 实施步骤

1. 创建 `upper_hmi/physics_engine.py` — 从 simulation_controller 移植物理方法
2. 创建 `upper_hmi/hmi_window.py` — 从 main_window.py 裁剪
3. 创建 `upper_hmi/bridge.py` — 封装 FM 连接
4. 创建 `upper_hmi/main.py` — 启动入口
5. 测试对比: 原仿真 vs 新上位机 + FM
