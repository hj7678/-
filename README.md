# 搅拌站后料场上料系统仿真软件

基于 PyQt5 的搅拌站后料场上料系统仿真软件，支持自动调度、物理仿真、故障诊断和下位机通信。

## 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                     PyQt5 上位机界面                          │
│  ┌─────────┐  ┌──────────────────┐  ┌────────────────────┐   │
│  │ 控制面板 │  │    仿真画布(2D)   │  │   状态监控面板      │   │
│  └─────────┘  └──────────────────┘  └────────────────────┘   │
│        │              │                      │               │
│        └──────────────┼──────────────────────┘               │
│                       │                                      │
│            SimulationController (核心仿真引擎)                │
│                       │                                      │
│     ┌─────────────────┼─────────────────┐                    │
│     ▼                 ▼                  ▼                    │
│  调度服务(TCP)    诊断服务(TCP)     下位机通信(TCP/UDP)       │
│  :8891~8894       :8890              :8888/:8889             │
└──────────────────────────────────────────────────────────────┘
```

## 核心功能

### 物理仿真
- **19条皮带**、**20个接近开关**、**7个中转斗**、**5个上料点**
- **28仓配料站**（P1-P4 × 7行）+ **12仓高位储料仓**（S1-S6 × 2行）
- **4个分料小车**（Cart1-Cart4），18秒/格移动
- **8条上料路线**（6状态状态机：IDLE→MOVING_TO_TARGET→FEEDING→CLEARING→WAITING→STANDBY）
- **3种清空策略**：顺序(sequential)、反序(reverse)、换列(column_switch)

### 自动调度
- TCP调度服务独立进程（端口8891-8894）
- 遗传算法+贪心启发式优化
- **触发规则**：紧急<10%、空闲<70t、预请求≥80%（均120s冷却）
- 节能待机（STANDBY）：无待补料仓时自动停止皮带

### 物料物理仿真
- 物料从上料点→皮带→中转斗→分料小车→目标料仓
- 中转斗实时囤积/释放（0.195t/s，容量8500kg）
- 料仓消耗模拟搅拌站生产
- 清空余料：中转斗关闭→物料囤积→黄色填充实时显示

### 故障系统
- 接近开关故障：卡高/卡低
- 中转斗故障：开关卡死、称重异常
- 皮带故障：速度异常
- 小车传感器故障：位置/极限/分料
- 本地/TCP双模式诊断

### 实时动画
- 暗色工业风格2D画布
- 皮带运行/停止状态实时显示
- 3种骨料粒子动画（石粉/10mm/20mm）
- 中转斗黄色填充（实时囤料量）
- FEEDING时紫色/黄色闪烁箭头
- 高位储料仓颜色分级（红→橙→黄→绿）

## 安装

```bash
pip install -r requirements.txt
```

依赖：Python 3.10+, PyQt5 5.15+, NumPy, Pandas, openpyxl

## 运行

```bash
# 1. 启动调度服务（独立终端）
python -m scheduling.main

# 2. 启动仿真软件
python main.py
```

## 解耦架构

独立前端后端分离版本位于 `decoupled_system/`：

```bash
# 后端（headless）
python -m server.main --port 9501

# 前端（连接后端）
python main.py --backend localhost:9501
```

## 项目结构

```
sensor_simulate/
├── main.py                          # 程序入口
├── config.py                        # 配置（从pos.py构建）
├── pos.py                           # 物理布局坐标
├── styles.py                        # UI样式
├── models/                          # 数据模型
│   └── material.py                  # 物料模型
├── views/                           # UI组件
│   ├── main_window.py               # 主窗口
│   ├── simulation_view.py           # 2D仿真画布
│   ├── control_panel.py             # 控制面板
│   ├── status_panel.py              # 状态监控
│   ├── operation_log_panel.py       # 运行信息栏
│   ├── feed_point_select_dialog.py  # 上料点选择
│   └── bin_select_dialog.py         # 料仓选择
├── controllers/                     # 控制器
│   ├── simulation_controller.py     # 核心仿真引擎
│   ├── route_state_manager.py       # 路线状态机
│   ├── tcp_scheduling_client.py     # 调度TCP客户端
│   ├── tcp_diagnosis_client.py      # 诊断TCP客户端
│   └── fault_diagnosis_adapter.py   # 诊断适配器
├── scheduling/                      # 调度服务
│   ├── main.py                      # 调度服务入口
│   ├── server.py                    # TCP调度服务端
│   ├── engine.py                    # 调度优化引擎
│   ├── bin_config.py                # 料仓配置映射
│   ├── config.py                    # 调度参数
│   └── sched_types.py               # 调度数据类型
├── fault_diagnosis/                 # 故障诊断
│   ├── engine.py                    # 诊断引擎
│   └── types.py                     # 诊断类型
├── tcp_diagnosis/                   # TCP诊断配置
├── requirements.txt
└── README.md
```

## 版本

v2.6 — 2026年6月

---

### 关联项目

`decoupled_system/` — 前后端解耦架构（独立进程，TCP通信，多前端支持）
