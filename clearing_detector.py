"""
清空余料检测器 — 零依赖独立模块

基于接近开关传感器状态变化判断清空余料是否完成。

输入:
  - 路线配置（皮带、中转斗、目标仓）
  - 传感器位置 & 当前状态
  - 当前仿真时间

输出:
  - 各段皮带是否清空完成
  - 路线整体是否清空完成

规则:
  1. 传感器 true→false 后开始计时
  2. 保持 false 达到 `距离/2.5 + 2s` → 该段完成
  3. 所有段完成 → 路线清空完成
"""

from typing import Dict, List, Optional, Set, Tuple

# =============================================================================
# 基础参数
# =============================================================================
BELT_SPEED = 2.5       # m/s
TOLERANCE_TIME = 2.0    # 容错时间 (s)
LINE_SPACING = 5.4      # 相邻料仓间距 (m)

# 终点皮带：传感器到最近料仓(P-7)的基础距离
ENDPOINT_BASE_DIST = {'D7': 22.1, 'D8': 17.4, 'D9': 12.1}

# ---------------------------------------------------------------------------
# 每条路线的皮带配置: (皮带ID, 皮带长度, 传感器ID, 传感器距起点比例)
# 最后一个元素为终点皮带（需动态计算目标仓距离）
# ---------------------------------------------------------------------------
ROUTE_BELT_CONFIGS = {
    'route1': [
        ('E1',  16.8, 'S-E1', 0.05, False),   # → (hopper1)
        ('E4',  85.2, 'S-E4', 0.05, 'hopper1'),
        ('E8',  59.7, 'S-E8', 0.05, 'hopper3'),
        ('E10', 35.0, 'S-E10', 0.05, 'hopper4'),
        ('D7',  59.9, 'S-D7', 0.05, 'ENDPOINT'),
    ],
    'route2': [
        ('E2',  20.0, 'S-E2', 0.05, False),
        ('E4',  85.2, 'S-E4', 0.05, 'hopper1'),
        ('E8',  59.7, 'S-E8', 0.05, 'hopper3'),
        ('E10', 35.0, 'S-E10', 0.05, 'hopper4'),
        ('D7',  59.9, 'S-D7', 0.05, 'ENDPOINT'),
    ],
    'route3': [
        ('E5',  27.2, 'S-E5', 0.05, 'hopper1'),
        ('E8',  59.7, 'S-E8', 0.05, 'hopper3'),
        ('E10', 35.0, 'S-E10', 0.05, 'hopper4'),
        ('D7',  59.9, 'S-D7', 0.05, 'ENDPOINT'),
    ],
    'route4': [
        ('E6',  22.5, 'S-E6', 0.05, False),
        ('E7',  56.0, 'S-E7', 0.05, 'hopper2'),
        ('E9',  48.0, 'S-E9', 0.05, 'hopper6'),
        ('D9',  49.9, 'S-D9', 0.05, 'ENDPOINT'),
    ],
    'route5': [
        ('E6',  22.5, 'S-E6', 0.05, False),
        ('E7',  56.0, 'S-E7', 0.05, 'hopper2'),
        ('E9',  48.0, 'S-E9', 0.05, 'hopper6'),
        ('D5',  27.2, 'S-D5', 0.05, 'hopper7'),
        ('D6',  30.0, 'S-D6', 0.05, 'ENDPOINT'),
    ],
    'route6': [
        ('D13', 15.8, 'S-D13', 0.05, False),
        ('D2',  65.8, 'S-D2',  0.05, False),
        ('D4',  20.0, 'S-D4',  0.05, 'hopper5'),
        ('D8',  55.2, 'S-D8',  0.05, 'ENDPOINT'),
    ],
    'route7': [
        ('D1',  65.8, 'S-D1', 0.05, False),
        ('D3',  36.6, 'S-D3', 0.05, False),
        ('D9',  49.9, 'S-D9', 0.05, 'ENDPOINT'),
    ],
    'route8': [
        ('D2',  65.8, 'S-D2-2', 0.80, False),
        ('D4',  20.0, 'S-D4',   0.05, 'hopper5'),
        ('D8',  55.2, 'S-D8',   0.05, 'ENDPOINT'),
    ],
}

# =============================================================================
# 数据结构
# =============================================================================

class BeltSegment:
    """单段皮带清空状态"""
    def __init__(self, belt_id: str, sensor_id: str, timeout: float):
        self.belt_id = belt_id
        self.sensor_id = sensor_id
        self.timeout = timeout           # 需要保持熄灭的时间 (s)
        self.sensor_went_false_at = 0.0  # 传感器熄灭时刻
        self.completed = False

    def update(self, sensor_active: bool, current_time: float) -> bool:
        """更新传感器状态，返回本段是否清空完成"""
        if self.completed:
            return True
        if sensor_active:
            self.sensor_went_false_at = 0.0  # 重新触发，重置
            return False
        # 传感器熄灭
        if self.sensor_went_false_at == 0.0:
            self.sensor_went_false_at = current_time
        elapsed = current_time - self.sensor_went_false_at
        if elapsed >= self.timeout:
            self.completed = True
            return True
        return False

    def reset(self):
        self.sensor_went_false_at = 0.0
        self.completed = False


class RouteClearingState:
    """单条路线的清空状态"""
    def __init__(self, route_id: str, segments: List[BeltSegment]):
        self.route_id = route_id
        self.segments = segments
        self.completed = False

    def update(self, sensor_states: Dict[str, bool], current_time: float) -> Tuple[bool, List[str]]:
        """更新所有段，返回 (是否完成, [刚完成的传感器列表])"""
        if self.completed:
            return True, []
        just_completed = []
        all_done = True
        for seg in self.segments:
            active = sensor_states.get(seg.sensor_id, False)
            done = seg.update(active, current_time)
            if done and seg.sensor_id not in [s for s in self.segments if s.completed]:
                just_completed.append(seg.sensor_id)
            if not done:
                all_done = False
        if all_done:
            self.completed = True
        return self.completed, just_completed

    def reset(self):
        self.completed = False
        for seg in self.segments:
            seg.reset()


# =============================================================================
# 主类
# =============================================================================

class ClearingDetector:
    """清空余料检测器

    用法:
        detector = ClearingDetector()
        detector.init_route('route1', 'P1-5')
        ...
        # 每帧调用:
        done, just = detector.update('route1', sensor_states, current_time)
        if done:
            print('清空完成!')
    """

    def __init__(self):
        self._routes: Dict[str, RouteClearingState] = {}

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def init_route(self, route_id: str, target_bin: str) -> bool:
        """初始化路线的清空检测。

        Args:
            route_id: 路线ID (route1~route8)
            target_bin: 目标料仓 (如 'P1-5', 'S3')

        Returns:
            是否成功初始化
        """
        configs = ROUTE_BELT_CONFIGS.get(route_id)
        if not configs:
            return False

        segments = []
        for belt_id, length, sensor_id, sensor_dist, hopper in configs:
            if hopper == 'ENDPOINT':
                timeout = self._calc_endpoint_timeout(belt_id, target_bin, length, sensor_dist)
            elif hopper is False:
                # 无存储组件的皮带：跳过（余料经此皮带进入下一皮带）
                continue
            else:
                # 连接中转斗的皮带
                remaining = length * (1.0 - sensor_dist)
                timeout = remaining / BELT_SPEED + TOLERANCE_TIME
            segments.append(BeltSegment(belt_id, sensor_id, timeout))

        if not segments:
            return False

        self._routes[route_id] = RouteClearingState(route_id, segments)
        return True

    def update(self, route_id: str, sensor_states: Dict[str, bool],
               current_time: float) -> Tuple[bool, List[str]]:
        """更新清空检测状态。

        Args:
            route_id: 路线ID
            sensor_states: {sensor_id: is_active} 传感器当前状态
            current_time: 当前仿真时间 (秒)

        Returns:
            (是否完成, [刚完成的传感器ID列表])
        """
        state = self._routes.get(route_id)
        if not state:
            return False, []
        return state.update(sensor_states, current_time)

    def is_completed(self, route_id: str) -> bool:
        state = self._routes.get(route_id)
        return state.completed if state else False

    def get_segment_status(self, route_id: str) -> List[dict]:
        """获取各段状态（调试用）"""
        state = self._routes.get(route_id)
        if not state:
            return []
        result = []
        for seg in state.segments:
            result.append({
                'belt': seg.belt_id, 'sensor': seg.sensor_id,
                'timeout': seg.timeout, 'completed': seg.completed,
                'false_since': seg.sensor_went_false_at,
            })
        return result

    def reset_route(self, route_id: str):
        state = self._routes.get(route_id)
        if state:
            state.reset()

    def reset_all(self):
        for state in self._routes.values():
            state.reset()

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _calc_endpoint_timeout(self, belt_id: str, target_bin: str,
                                length: float, sensor_dist: float) -> float:
        """计算终点皮带传感器判定时间"""
        if belt_id not in ENDPOINT_BASE_DIST:
            base = length * (1.0 - sensor_dist)  # 回退：全程距离
        else:
            base = ENDPOINT_BASE_DIST[belt_id]
        try:
            row = int(target_bin.split('-')[1])
        except (ValueError, IndexError):
            row = 7
        distance = base + LINE_SPACING * (8 - row)
        return distance / BELT_SPEED + TOLERANCE_TIME


# =============================================================================
# 自测
# =============================================================================

if __name__ == '__main__':
    import time

    detector = ClearingDetector()

    # 测试路线1，目标仓 P1-5
    detector.init_route('route1', 'P1-5')
    print("=== 路线① 清空参数 (P1-5) ===")
    for seg in detector._routes['route1'].segments:
        print(f"  {seg.belt_id} ({seg.sensor_id}): timeout={seg.timeout:.1f}s")

    # 模拟传感器全部熄灭
    sim_time = 0.0
    sensor_states = {'S-E1': False, 'S-E4': False, 'S-E8': False, 'S-E10': False, 'S-D7': False}

    # 逐步推进时间
    for t in [0, 5, 10, 15, 20, 25, 30, 35, 40]:
        sim_time = float(t)
        done, just = detector.update('route1', sensor_states, sim_time)
        status = detector.get_segment_status('route1')
        completed = [s['sensor'] for s in status if s['completed']]
        print(f"  t={sim_time:.0f}s: completed={completed}, route_done={done}")

    print()
    print("=== 不同目标仓的终点判定时间 ===")
    for target in ['P1-7', 'P1-5', 'P1-1']:
        detector.init_route('route1', target)
        seg = detector._routes['route1'].segments[-1]  # 最后一个=终点
        print(f"  {target}: D7/S-D7 timeout={seg.timeout:.1f}s")
