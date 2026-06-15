"""
料仓库存管理 — 纯数据中转站，独立进程

28个配料站 (P1-1 ~ P4-7) + 12个高位仓 (S1-1 ~ S6-2)

职责：存储和提供料位数据。不模拟消耗/补充——这些由仿真端或真实料位传感器负责。
"""
import threading
from typing import Dict, List, Optional


BATCHING_STATION = {
    'columns': 4, 'rows': 7,
    'col_names': ['P1', 'P2', 'P3', 'P4'],
    'capacity': 110.0,
}

HIGH_SILO = {
    'columns': 6, 'rows': 2,
    'col_names': ['S1', 'S2', 'S3', 'S4', 'S5', 'S6'],
    'capacity': 420.0,
}


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

    __slots__ = ('bin_id', 'level_tons', 'capacity', 'consumption_rate')

    def __init__(self, bin_id: str, capacity: float):
        self.bin_id = bin_id
        self.level_tons = 0.0
        self.capacity = capacity
        self.consumption_rate = 0.01

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


class BinStore:
    """料仓数据存储（纯数据，无模拟）"""

    def __init__(self):
        self._bins: Dict[str, BinState] = {}
        self._lock = threading.Lock()
        self._feeding: set = set()        # 正在补料的料仓 (仅展示用)
        self._discharging: set = set()    # 正在出料的高位仓 (仅展示用)

        for col in BATCHING_STATION['col_names']:
            for row in range(1, BATCHING_STATION['rows'] + 1):
                bid = f"{col}-{row}"
                self._bins[bid] = BinState(bid, BATCHING_STATION['capacity'])

        for col in HIGH_SILO['col_names']:
            for row in range(1, HIGH_SILO['rows'] + 1):
                bid = f"{col}-{row}"
                self._bins[bid] = BinState(bid, HIGH_SILO['capacity'])

    # ── 查询 ──

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

    # ── 修改 ──

    def set_level(self, bin_id: str, level_tons: float):
        with self._lock:
            b = self._bins.get(bin_id)
            if b:
                b.level_tons = max(0.0, min(b.capacity, level_tons))

    def set_levels_batch(self, data: Dict[str, float]):
        """批量设置料位 {bin_id: level_tons}"""
        with self._lock:
            for bid, val in data.items():
                b = self._bins.get(bid)
                if b:
                    b.level_tons = max(0.0, min(b.capacity, float(val)))

    def set_consumption_rate(self, bin_id: str, rate: float):
        """设置单个料仓消耗速率"""
        with self._lock:
            b = self._bins.get(bin_id)
            if b:
                b.consumption_rate = max(0.0, float(rate))

    def randomize_levels(self, lo_pct: float = 25.0, hi_pct: float = 90.0):
        import random
        with self._lock:
            for b in self._bins.values():
                pct = random.uniform(lo_pct, hi_pct)
                b.level_tons = round(pct * b.capacity / 100.0, 2)

    # ── 展示用状态追踪 ──

    def mark_feeding(self, bin_id: str):
        with self._lock:
            self._feeding.add(bin_id)

    def unmark_feeding(self, bin_id: str):
        with self._lock:
            self._feeding.discard(bin_id)

    def mark_discharging(self, bin_id: str):
        with self._lock:
            self._discharging.add(bin_id)

    def unmark_discharging(self, bin_id: str):
        with self._lock:
            self._discharging.discard(bin_id)

    def get_status_summary(self) -> dict:
        """获取展示用摘要"""
        with self._lock:
            bins_sorted = sorted(self._bins.values(), key=lambda b: b.level_pct)
            return {
                'total_tons': round(sum(b.level_tons for b in self._bins.values()), 1),
                'feeding': sorted(self._feeding),
                'discharging': sorted(self._discharging),
                'lowest': [(b.bin_id, round(b.level_pct, 1), b.consumption_rate)
                           for b in bins_sorted[:5]],
                'highest': [(b.bin_id, round(b.level_pct, 1), b.consumption_rate)
                            for b in bins_sorted[-5:]],
            }
