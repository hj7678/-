"""
Stock Management 客户端 — Upper Computer 侧

扩展共享基类，添加 HMI 专用方法（料位设置、消耗控制等）。
"""
from typing import Dict, List

from shared.stock_client import BaseStockClient


class StockClient(BaseStockClient):
    """Upper Computer Stock Client — 扩展基类，添加写入方法"""

    def set_level(self, bin_id: str, level_tons: float):
        if not self._sock:
            self.connect()
        self._request({"action": "set_level", "bin_id": bin_id, "level_tons": level_tons})

    def set_levels_batch(self, data: Dict[str, float]):
        """批量推送料位（桥接用）"""
        if not self._sock:
            self.connect()
        self._request({"action": "set_levels_batch", "data": data})

    def set_consumption_rate(self, bin_id: str, rate: float):
        if not self._sock:
            self.connect()
        self._request({"action": "set_consumption", "bin_id": bin_id, "rate": rate})

    def set_consumption_rates_batch(self, rates: Dict[str, float]):
        if not self._sock:
            self.connect()
        self._request({"action": "set_consumption_batch", "rates": rates})

    def randomize_all(self, lo_pct: float = 25.0, hi_pct: float = 90.0):
        if not self._sock:
            self.connect()
        self._request({"action": "randomize", "lo_pct": lo_pct, "hi_pct": hi_pct})

    def start_consumption(self):
        if not self._sock:
            self.connect()
        self._request({"action": "start_consumption"})

    def stop_consumption(self):
        if not self._sock:
            self.connect()
        self._request({"action": "stop_consumption"})