# 调度与故障诊断模块对接方案

## 当前状态审计

经代码分析，**大部分基础对接代码已存在**：

### 已实现 ✅
- **TCP 诊断客户端**：`controllers/tcp_diagnosis_client.py` — 连接 TCP 诊断服务、收发数据
- **TCP 调度客户端**：`controllers/tcp_scheduling_client.py` — 连接 TCP 调度服务、收发数据
- **本地诊断适配器**：`controllers/fault_diagnosis_adapter.py` — 将仿真状态转为诊断引擎输入
- **UI 诊断模式选择**：控制面板已有 "本地诊断 / TCP 远程诊断" 单选按钮
- **UI 诊断服务连接按钮**：已有 "诊断服务：断开/连接中.../已连接"
- **UI 调度服务连接按钮**：已有 "调度服务：断开/连接中.../已连接"
- **调度结果显示**：状态面板已有 "调度上料顺序" 区域，D7/D8/D9 分别显示
- **信号链路**：ControlPanel → MainWindow → SimulationController 已完整铺设
- **数据发送**：`simulation_controller._generate_sensor_data()` 已向 TCP 客户端推送数据

### 缺失 ❌

1. **缺少本地调度模式** — 调度引擎 `SchedulingEngine.solve()` 只能通过 TCP 服务调用，没有进程内本地调度适配器。对比诊断模块已有本地 + TCP 双模式，调度模块只有 TCP 模式
2. **UI 缺少调度模式选择** — 诊断有 local/tcp 单选按钮，调度没有
3. **调度结果未接入仿真回路** — TCP 调度结果收到后只存储显示，没有反馈到小车控制中（可能是预期行为，需确认）

## 需要做的事

### 任务 1：添加本地调度适配器

新建 `controllers/scheduling_adapter.py`（类比 `controllers/fault_diagnosis_adapter.py`），将仿真内部状态转换为 `BinState` 列表，直接调用 `SchedulingEngine.solve()` 获取调度结果，无需 TCP。

```python
# 核心逻辑
from scheduling.engine import SchedulingEngine
from scheduling.sched_types import BinState
from scheduling.bin_config import BELT_BINS, BELT_COL_COUNT

class SchedulingAdapter:
    def run_scheduling(self, small_bins, belt_id: str) -> ScheduleResult:
        engine = SchedulingEngine(col_count=BELT_COL_COUNT[belt_id], belt_id=belt_id)
        bin_states = [...]  # 从 small_bins 构建
        return engine.solve(bin_states)
```

### 任务 2：调度模式切换（本地/TCP）

**修改文件**：
- `views/control_panel.py`：添加 "本地调度 / TCP 远程调度" 单选按钮，新增信号 `scheduling_mode_changed`
- `views/main_window.py`：处理 `scheduling_mode_changed` 信号，转发到 controller
- `controllers/simulation_controller.py`：添加 `_scheduling_mode` 字段、`set_scheduling_mode()` 方法，本地模式下定期调用 adapter

### 任务 3：本地调度接入仿真更新循环

在 `_run_fault_diagnosis()` 同级（或新方法 `_run_local_scheduling()`）中，本地模式下调用 `SchedulingAdapter.run_scheduling()` 获取结果并存储到 `_tcp_schedules`（与 TCP 模式统一存储、统一显示）。

### 涉及文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `controllers/scheduling_adapter.py` | **新建** | 本地调度适配器 |
| `views/control_panel.py` | 修改 | 添加调度模式单选按钮 + 信号 |
| `views/main_window.py` | 修改 | 连接新信号 |
| `controllers/simulation_controller.py` | 修改 | 添加本地调度模式逻辑 |

## 验证方式

1. 运行 `python main.py` 启动仿真
2. 检查控制面板是否有 "本地调度 / TCP 远程调度" 单选按钮
3. 选择 "本地调度"，启动一条路线，确认状态面板 "调度上料顺序" 区域显示结果（无需启动外部服务）
4. 选择 "TCP 远程调度"，确认按钮连接/断开逻辑正常
5. 切换诊断模式 "本地/TCP"，确认工作正常（无回归）
