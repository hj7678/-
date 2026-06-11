"""
料仓库存管理 — 独立进程，模拟40个料仓的实时料位

28个配料站 (P1-1 ~ P4-7) + 12个高位仓 (S1-1 ~ S6-2)

仿真模式：
  - 每1秒按各仓消耗速率递减
  - 收到 refill 事件后按 0.195 t/s 递增
  - 料位不超出容量上限、不低于0
"""
import threading
import time
from typing import Dict, List, Optional


# ── 料仓配置 ──────────────────────────────────

BATCHING_STATION = {
    'columns': 4, 'rows': 7,
    'col_names': ['P1', 'P2', 'P3', 'P4'],
    'capacity': 110.0,  # 吨
}

HIGH_SILO = {
    'columns': 6, 'rows': 2,
    'col_names': ['S1', 'S2', 'S3', 'S4', 'S5', 'S6'],
    'capacity': 420.0,  # 吨
}

FEED_RATE = 0.195  # 上料速率 t/s


def _build_all_bin_ids() -> List[str]:
    ids = []
    for col in BATCHING_STATION['col_names']:
        for row in range(1, BATCHING_STATION['rows'] + 1):
            ids.append(f"{col}-{row}")
    for col in HIGH_SILO['col_names']:
        for row in range(1, HIGH_SILO['rows'] + 1):
            ids.append(f"{col}-{row}")
    return ids


ALL_BIN_IDS = _build_all_bin_ids()


class BinState:
    """单个料仓状态"""

    __slots__ = ('bin_id', 'level_tons', 'capacity', 'consumption_rate',
                 '_last_update')

    def __init__(self, bin_id: str, capacity: float):
        self.bin_id = bin_id
        self.level_tons = 0.0
        self.capacity = capacity
        self.consumption_rate = 0.01   # t/s 默认
        self._last_update = time.time()

    @property
    def level_pct(self) -> float:
        return (self.level_tons / self.capacity) * 100 if self.capacity > 0 else 0

    def to_dict(self) -> dict:
        return {
            'bin_id': self.bin_id,
            'level_tons': round(self.level_tons, 2),
            'level_pct': round(self.level_pct, 1),
            'capacity': self.capacity,
            'consumption_rate': self.consumption_rate,
        }

    def consume(self, delta_seconds: float):
        """按消耗速率递减"""
        if self.consumption_rate <= 0:
            return
        consumed = self.consumption_rate * delta_seconds
        self.level_tons = max(0.0, self.level_tons - consumed)

    def refill(self, delta_seconds: float):
        """上料补充递增"""
        added = FEED_RATE * delta_seconds
        self.level_tons = min(self.capacity, self.level_tons + added)


class BinStore:
    """料仓数据存储 + 消耗模拟"""

    def __init__(self):
        self._bins: Dict[str, BinState] = {}
        self._lock = threading.Lock()

        # 配料站 28仓
        for col in BATCHING_STATION['col_names']:
            for row in range(1, BATCHING_STATION['rows'] + 1):
                bid = f"{col}-{row}"
                self._bins[bid] = BinState(bid, BATCHING_STATION['capacity'])

        # 高位仓 12仓
        for col in HIGH_SILO['col_names']:
            for row in range(1, HIGH_SILO['rows'] + 1):
                bid = f"{col}-{row}"
                self._bins[bid] = BinState(bid, HIGH_SILO['capacity'])

        # 当前正在上料的料仓 (feeding 事件)
        self._feeding_bins: Dict[str, float] = {}  # bin_id → start_time
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ── 查询接口 ──

    def get_levels(self, bin_ids: List[str]) -> List[dict]:
        with self._lock:
            return [self._bins[bid].to_dict() for bid in bin_ids if bid in self._bins]

    def get_all(self) -> List[dict]:
        with self._lock:
            return [b.to_dict() for b in self._bins.values()]

    def get_bin(self, bin_id: str) -> Optional[dict]:
        with self._lock:
            b = self._bins.get(bin_id)
            return b.to_dict() if b else None

    # ── 修改接口 ──

    def set_level(self, bin_id: str, level_tons: float):
        with self._lock:
            b = self._bins.get(bin_id)
            if b:
                b.level_tons = max(0.0, min(b.capacity, level_tons))

    def set_consumption_rate(self, bin_id: str, rate: float):
        with self._lock:
            b = self._bins.get(bin_id)
            if b:
                b.consumption_rate = max(0.0, rate)

    def start_feeding(self, bin_id: str):
        """标记料仓开始上料"""
        with self._lock:
            self._feeding_bins[bin_id] = time.time()

    def stop_feeding(self, bin_id: str):
        """标记料仓停止上料"""
        with self._lock:
            self._feeding_bins.pop(bin_id, None)

    # ── 后台循环 ──

    def _run(self):
        print("[StockMgmt] 消耗模拟线程启动", flush=True)
        last_tick = time.time()
        while self._running:
            now = time.time()
            delta = now - last_tick
            last_tick = now

            with self._lock:
                # 消耗
                for b in self._bins.values():
                    b.consume(delta)

                # 上料补充
                for bid in list(self._feeding_bins.keys()):
                    b = self._bins.get(bid)
                    if b:
                        b.refill(delta)

            time.sleep(1.0)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
