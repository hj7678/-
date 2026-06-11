# 调度闭环自动上料方案（纯 TCP 模式）

## 需求

点击"调度服务"按钮后进入自动上料模式：
1. 发送料仓数据给调度服务 → 接收最优上料顺序
2. 取序列**第一个仓**，根据**上料点优先级规则**选择最优上料点和路线
3. 自动启动路线，上料完成后立即触发下一轮调度
4. 循环直到手动停止

## 上料点优先级规则

| 料仓 | 优先级（高→低） | 说明 |
|------|-----------------|------|
| P1 | feed1_1 > feed2_1 > feed1_2 | |
| P2/P3 | feed3 > silo_out | feed3 优先给 P2/P3 |
| P4 | feed3 > silo_out > feed2_2 | 但当 P2/P3 有调度任务时跳过 feed3 |

**公共规则**：
- 优先选有料的上料点（激光传感器检测）
- 多个上料点都有料时按上表优先级
- feed3 供给优先级：P2/P3 > P4

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `config.py` | 追加配置 | 上料点优先级 + 激光传感器 → 上料点映射 |
| `controllers/simulation_controller.py` | 修改 | 自动上料核心（优先级选择 + 路线启动 + 完成检测） |
| `views/main_window.py` | 修改 | 路线完成 → 触发下一轮调度 |
| `views/status_panel.py` | 修改 | 标记当前执行中的仓和后续序列 |

## 实现细节

### 1. config.py — 追加自动上料专属配置

```python
# 自动上料 —— 上料点优先级（数字越小优先级越高）
FEED_POINT_PRIORITY = {
    'P1': {'feed1_1': 1, 'feed2_1': 2, 'feed1_2': 3},
    'P2': {'feed3': 1, 'silo_out': 2},
    'P3': {'feed3': 1, 'silo_out': 2},
    'P4': {'feed3': 1, 'silo_out': 2, 'feed2_2': 3},
}

# 有激光传感器的上料点（silo_out 是储料仓，无激光传感器，默认为有料）
FEED_POINTS_WITH_LASER = ['feed1_1', 'feed1_2', 'feed2_1', 'feed2_2', 'feed3']

# feed3 优先供应 P2/P3
FEED3_PRIORITY_BELTS = ['P2', 'P3']
```

### 2. simulation_controller.py — _select_feed_point()

```python
def _select_feed_point(self, bin_id: str) -> tuple:
    """
    按优先级选择上料点和路线。
    返回 (feed_point, route_id) 或 (None, None)
    """
    available = config.BIN_TO_AVAILABLE_ROUTES.get(bin_id, [])
    if not available:
        return None, None

    prefix = bin_id.split('-')[0]
    priority_map = config.FEED_POINT_PRIORITY.get(prefix, {})

    candidates = []
    for feed_point, route_id in available:
        # 检查上料点是否有料
        if feed_point in config.FEED_POINTS_WITH_LASER:
            has_material = self.laser_sensor_states.get(feed_point, False)
        else:
            has_material = True  # silo_out 默认有料

        priority = priority_map.get(feed_point, 99)

        # feed3 优先给 P2/P3：P4 在 P2/P3 有任务时跳过 feed3
        if prefix == 'P4' and feed_point == 'feed3':
            if self._p2p3_has_pending_task():
                continue

        candidates.append((feed_point, route_id, has_material, priority))

    # 有料优先，其次按优先级数字排序
    candidates.sort(key=lambda x: (not x[2], x[3]))

    if candidates:
        return candidates[0][0], candidates[0][1]
    return None, None
```

### 3. simulation_controller.py — _on_tcp_schedule_received() 改

```python
def _on_tcp_schedule_received(self, belt_id, result):
    self._tcp_schedules[belt_id] = result

    if not self._auto_feeding_active:
        return
    if belt_id in self._executing_route:  # 该皮带正在执行中
        return

    seq = result.get('sequence', [])
    if not seq:
        return

    first_bin = seq[0]
    feed_point, route_id = self._select_feed_point(first_bin)
    if route_id is None:
        return

    # 设置路线参数
    self.set_route_target_bin(route_id, first_bin)
    # 路线⑧⑨需要设置 silo_bin
    if route_id in ('route8', 'route9'):
        self.set_route_silo_bin(route_id, self._get_silo_bin_for_route(route_id))

    # 启动路线
    self.start_route(route_id)
    self._executing_route[belt_id] = route_id
    self._executing_bin[belt_id] = first_bin
```

### 4. main_window.py — 路线完成后触发下一轮

在 `_on_route_state_changed` 中：
```python
# 自动上料：路线完成后触发下一轮调度
if new_state == 'waiting' and self.controller._auto_feeding_active:
    for belt_id, route in list(self.controller._executing_route.items()):
        if route == route_id:
            # 清除本次执行记录，触发下一轮（不等5秒定时器）
            del self.controller._executing_route[belt_id]
            del self.controller._executing_bin[belt_id]
            self.controller._request_immediate_scheduling(belt_id)
            break
```

### 5. status_panel.py — 增强显示

`update_schedule_display()` 增加：
- 序列第一个仓标记 "执行中 ▶"
- 后续仓显示为灰色

## 验证

1. `python -m scheduling.main` 启动调度服务
2. `python main.py` 启动仿真
3. 设置激光传感器状态（模拟上料点有/无料）
4. 点击"调度服务"按钮 → 观察自动选择优先级最高的有料上料点
5. 路线执行 → 完成后自动下一轮
6. 状态面板查看当前执行仓
