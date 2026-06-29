"""
Stock Management 客户端 — FeedingMaster 侧

扩展共享基类，添加 FM 专用方法。
"""
from typing import List

from shared.stock_client import BaseStockClient


class StockClient(BaseStockClient):
    """FeedingMaster Stock Client — 扩展基类，添加调度相关方法"""

    def get_levels(self, bin_ids: List[str]) -> List[dict]:
        resp = self._request({"action": "get_levels", "bin_ids": bin_ids})
        if resp and resp.get("ok"):
            return resp.get("data", [])
        return []

    def start_feeding(self, bin_id: str):
        self._request({"action": "start_feeding", "bin_id": bin_id})

    def stop_feeding(self, bin_id: str):
        self._request({"action": "stop_feeding", "bin_id": bin_id})