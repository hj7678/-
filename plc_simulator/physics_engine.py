"""
PLC 模拟器 — 物理仿真引擎

模拟现场设备的物理行为: 皮带运行、物料流动、传感器触发、小车移动、称重变化。

50ms 周期循环，读取线圈状态，更新离散输入和保持寄存器。
"""
import threading
import time
from typing import Dict, List, Optional

from plc_simulator.modbus_server import ModbusMemory


# ── 地址定义 ──

# 线圈
COIL_BELTS = {f"E{i}": 1000 + i for i in [1,2,4,5,6,7,8,9,10]}  # E 系列
COIL_BELTS.update({f"D{i}": 1000 + i for i in [1,2,3,4,5,6,7,8,9,13]})  # D 系列
# 实际映射: E1=1001 ... D13=1019 (19条)

BELT_COILS = {
    'E1': 1001, 'E2': 1002, 'E4': 1003, 'E5': 1004, 'E6': 1005,
    'E7': 1006, 'E8': 1007, 'E9': 1008, 'E10': 1009,
    'D1': 1010, 'D2': 1011, 'D3': 1012, 'D4': 1013, 'D5': 1014,
    'D6': 1015, 'D7': 1016, 'D8': 1017, 'D9': 1018, 'D13': 1019,
}

HOPPER_COILS = {f'hopper{i}': 2000 + i for i in range(1, 8)}  # 2001-2007

CART_DIVERT_COILS = {'Cart1': 3001, 'Cart2': 3002, 'Cart3': 3003, 'Cart4': 3004}
CART_MOVE_COILS  = {'Cart1': 3005, 'Cart2': 3006, 'Cart3': 3007, 'Cart4': 3008}

FEED_COILS = {
    'feed1_1': 3009, 'feed1_2': 3010, 'feed2_1': 3011, 'feed2_2': 3012, 'feed3': 3013,
}

# 离散输入
PROXIMITY_DI = {
    'S-E1': 1001, 'S-E2': 1002, 'S-E4': 1003, 'S-E5': 1004, 'S-E6': 1005,
    'S-E7': 1006, 'S-E8': 1007, 'S-E9': 1008, 'S-E10': 1009,
    'S-D1': 1010, 'S-D2': 1011, 'S-D2-2': 1012, 'S-D3': 1013, 'S-D4': 1014,
    'S-D5': 1015, 'S-D6': 1016, 'S-D7': 1017, 'S-D8': 1018, 'S-D9': 1019, 'S-D13': 1020,
}

HOPPER_POS_DI = {f'hopper{i}': 2000 + i for i in range(1, 8)}    # 2001-2007 开关到位
CART_LEFT_LIMIT  = {'Cart1': 3001, 'Cart2': 3002, 'Cart3': 3003, 'Cart4': 3004}
CART_RIGHT_LIMIT = {'Cart1': 3005, 'Cart2': 3006, 'Cart3': 3007, 'Cart4': 3008}
CART_ARRIVAL     = {'Cart1': 4001, 'Cart2': 4002, 'Cart3': 4003, 'Cart4': 4004}
HOPPER_MATERIAL  = {f'hopper{i}': 5000 + i for i in range(1, 8)}  # 5001-5007 有料检测

# 保持寄存器
HOPPER_WEIGHT_HR = {f'hopper{i}': 40050 + i for i in range(1, 8)}  # 40051-40057
CART_POS_HR      = {'Cart1': 40101, 'Cart2': 40102, 'Cart3': 40103, 'Cart4': 40104}
BELT_SPEED_HR = {
    'E1': 40201, 'E2': 40202, 'E4': 40203, 'E5': 40204, 'E6': 40205,
    'E7': 40206, 'E8': 40207, 'E9': 40208, 'E10': 40209,
    'D1': 40210, 'D2': 40211, 'D3': 40212, 'D4': 40213, 'D5': 40214,
    'D6': 40215, 'D7': 40216, 'D8': 40217, 'D9': 40218, 'D13': 40219,
}

# 皮带到接近开关的映射 (belt_id → sensor_id)
BELT_SENSOR_MAP = {
    'E1': 'S-E1', 'E2': 'S-E2', 'E4': 'S-E4', 'E5': 'S-E5',
    'E6': 'S-E6', 'E7': 'S-E7', 'E8': 'S-E8', 'E9': 'S-E9', 'E10': 'S-E10',
    'D1': 'S-D1', 'D3': 'S-D3', 'D4': 'S-D4', 'D5': 'S-D5',
    'D6': 'S-D6', 'D7': 'S-D7', 'D8': 'S-D8', 'D9': 'S-D9', 'D13': 'S-D13',
}
# D2 有两个传感器
BELT_SENSOR_MAP_EXTRA = {'D2': ['S-D2', 'S-D2-2']}


class PhysicsEngine:
    """物理仿真引擎"""

    def __init__(self, mem: ModbusMemory):
        self.mem = mem
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._tick_ms = 50

        # 内部计时器
        self._belt_timers: Dict[str, float] = {}    # belt → 运行秒数
        self._hopper_weight: Dict[str, float] = {}   # hopper → 重量 (吨)
        self._hopper_transition: Dict[str, float] = {} # hopper → 开/关过渡剩余时间
        self._cart_positions: Dict[str, float] = {}   # cart → 位置 (浮点)
        self._cart_targets: Dict[str, int] = {}       # cart → 目标位置
        self._cart_moving: Dict[str, bool] = {}
        self._proximity_hold: Dict[str, float] = {}   # sensor → 保持时间

        # 初始化
        for hid in HOPPER_COILS:
            self._hopper_weight[hid] = 0.0
            self._hopper_transition[hid] = 0.0
        for cid in CART_POS_HR:
            self._cart_positions[cid] = 1.0
            self._cart_targets[cid] = 1
            self._cart_moving[cid] = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print("[PLC Sim] 物理引擎已启动 (50ms)", flush=True)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self):
        last = time.time()
        while self._running:
            now = time.time()
            delta = now - last
            last = now
            self._tick(delta)
            elapsed = time.time() - now
            time.sleep(max(0, self._tick_ms / 1000.0 - elapsed))

    def _tick(self, delta: float):
        # 1. 皮带运行模拟
        self._update_belts(delta)

        # 2. 中转斗开关过渡
        self._update_hoppers(delta)

        # 3. 小车移动
        self._update_carts(delta)

        # 4. 接近开关保持时间递减
        self._update_proximity_hold(delta)

    def _update_belts(self, delta: float):
        for belt_id, coil in BELT_COILS.items():
            running = self.mem.read_coil(coil)
            if running:
                t = self._belt_timers.get(belt_id, 0.0) + delta
                self._belt_timers[belt_id] = t

                # 皮带速度写保持寄存器 (2.5 m/s → 25)
                self.mem.write_holding(BELT_SPEED_HR[belt_id], 25)

                # 接近开关触发 (物料到达传感器位置)
                if belt_id in BELT_SENSOR_MAP:
                    sid = BELT_SENSOR_MAP[belt_id]
                    self.mem.write_discrete(PROXIMITY_DI[sid], True)
                    self._proximity_hold[sid] = 0.2  # 保持 200ms

                # D2 额外传感器
                if belt_id == 'D2':
                    for sid in BELT_SENSOR_MAP_EXTRA.get('D2', []):
                        self.mem.write_discrete(PROXIMITY_DI[sid], True)
                        self._proximity_hold[sid] = 0.2
            else:
                self._belt_timers[belt_id] = 0.0
                self.mem.write_holding(BELT_SPEED_HR[belt_id], 0)

    def _update_proximity_hold(self, delta: float):
        for sid in list(self._proximity_hold.keys()):
            remaining = self._proximity_hold[sid] - delta
            if remaining <= 0:
                # 释放传感器
                if sid in PROXIMITY_DI:
                    self.mem.write_discrete(PROXIMITY_DI[sid], False)
                del self._proximity_hold[sid]
            else:
                self._proximity_hold[sid] = remaining

    def _update_hoppers(self, delta: float):
        for hid, coil in HOPPER_COILS.items():
            cmd_open = self.mem.read_coil(coil)  # 上位机命令: 1=开

            # 过渡中
            if hid in self._hopper_transition and self._hopper_transition[hid] > 0:
                remaining = self._hopper_transition[hid] - delta
                if remaining <= 0:
                    self._hopper_transition[hid] = 0.0
                    # 过渡完成
                    self.mem.write_discrete(HOPPER_POS_DI[hid], cmd_open)  # 开=1, 关=0
                else:
                    self._hopper_transition[hid] = remaining
                    # 过渡中: 未关到位 = True
                    self.mem.write_discrete(HOPPER_POS_DI[hid], True)
                continue

            # 当前到位状态 vs 命令
            current_pos = self.mem.read_discrete(HOPPER_POS_DI[hid])
            if current_pos != cmd_open:
                # 开始过渡
                self._hopper_transition[hid] = 0.5  # 500ms 过渡
                self.mem.write_discrete(HOPPER_POS_DI[hid], True)  # 过渡中

            # 斗开 + 下一皮带运行 → 物料流出 → 称重递减
            if cmd_open:
                belt_running = any(
                    self.mem.read_coil(BELT_COILS.get(b, 0))
                    for b in BELT_COILS
                )
                if belt_running and self._hopper_weight.get(hid, 0) > 0:
                    new_w = max(0, self._hopper_weight[hid] - 0.1 * delta * 2)  # ~0.2t/s
                    self._hopper_weight[hid] = new_w
                    self.mem.write_holding(HOPPER_WEIGHT_HR[hid], int(new_w * 100))
                    if new_w <= 0:
                        self.mem.write_discrete(HOPPER_MATERIAL[hid], False)

    def _update_carts(self, delta: float):
        for cid in CART_POS_HR:
            moving = self.mem.read_coil(CART_MOVE_COILS.get(cid, 0))
            divert = self.mem.read_coil(CART_DIVERT_COILS.get(cid, 0))

            if moving:
                # 小车移动: 2s/格
                speed = delta / 2.0  # 格/秒 (每格2秒)
                pos = self._cart_positions.get(cid, 1.0)
                target = self._cart_targets.get(cid, 1)
                if abs(pos - target) > 0.01:
                    direction = 1 if target > pos else -1
                    new_pos = pos + direction * speed
                    if (direction > 0 and new_pos >= target) or (direction < 0 and new_pos <= target):
                        new_pos = float(target)
                        self._cart_moving[cid] = False
                        self.mem.write_discrete(CART_ARRIVAL[cid], True)
                    else:
                        self._cart_moving[cid] = True
                        self.mem.write_discrete(CART_ARRIVAL[cid], False)
                    self._cart_positions[cid] = new_pos

                # 更新位置寄存器
                self.mem.write_holding(CART_POS_HR[cid], int(pos))

                # 极限检测
                max_pos = 7 if cid != 'Cart4' else 6
                self.mem.write_discrete(CART_LEFT_LIMIT[cid], pos <= 1.0)
                self.mem.write_discrete(CART_RIGHT_LIMIT[cid], pos >= max_pos)

    # ── 外部调用 ──

    def add_material_to_hopper(self, hopper_id: str, weight_tons: float = 0.1):
        """物料到达中转斗 → 累加重量"""
        w = self._hopper_weight.get(hopper_id, 0.0) + weight_tons
        self._hopper_weight[hopper_id] = w
        self.mem.write_holding(HOPPER_WEIGHT_HR[hopper_id], int(w * 100))
        self.mem.write_discrete(HOPPER_MATERIAL[hopper_id], True)

    def set_cart_target(self, cart_id: str, target: int):
        """设置小车目标位置"""
        self._cart_targets[cart_id] = target
        current = int(self._cart_positions.get(cart_id, 1))
        if current != target:
            self._cart_moving[cart_id] = True
