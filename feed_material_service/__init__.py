"""上料点原料状态服务端
负责存储上料点各物料的有料/无料状态，供 FM 查询和 UI 设置。
所有通信通过 TCP (main.py)，本模块仅提供数据模型。
"""

import threading
import time
from typing import Dict, Optional

# 料仓前缀 → 物料后缀映射
BIN_MATERIAL_SUFFIX = {
    'P1': 'stone',       # 石粉
    'P2': 'stone',       # 石粉
    'P3': '10mm',       # 10mm碎石
    'P4': '20mm',       # 20mm碎石
}

# 上料点 → 物料类型列表
FEED_POINT_MATERIALS = {
    'feed1_1': ['stone'],
    'feed1_2': ['stone'],
    'feed2_1': ['stone'],
    'feed2_2': ['stone', '10mm', '20mm'],
    'feed3': ['stone', '10mm'],
}

# S仓 → 物料类型映射
# S仓 → 物料类型映射（与 pos.py SILO_BIN_MATERIALS 一致）
SILO_MATERIAL = {
    'S1': '20mm', 'S2': '20mm', 'S3': '20mm',
    'S4': '20mm', 'S5': '20mm', 'S6': '20mm',
    'S7': 'stone', 'S8': 'stone',
    'S9': '10mm', 'S10': '10mm', 'S11': '10mm', 'S12': '10mm',
}


def _state_key(feed_point: str, material: str) -> str:
    """生成物料状态 key。单物料上料点直接用 feed_point 名"""
    mats = FEED_POINT_MATERIALS.get(feed_point, [])
    return feed_point if len(mats) <= 1 else f"{feed_point}_{material}"


class FeedMaterialService:
    """上料点原料状态服务（单例）"""

    _instance: Optional['FeedMaterialService'] = None
    _lock = threading.Lock()

    def __init__(self):
        self._states: Dict[str, bool] = {}
        self._lock = threading.Lock()
        # 默认全部有料
        for fp, mats in FEED_POINT_MATERIALS.items():
            for m in mats:
                self._states[_state_key(fp, m)] = True
        self._start_periodic_log()

    @classmethod
    def instance(cls) -> 'FeedMaterialService':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get_state(self, feed_point: str, material: str) -> bool:
        with self._lock:
            return self._states.get(_state_key(feed_point, material), True)

    def set_state(self, key: str, has_material: bool):
        old = self._states.get(key)
        with self._lock:
            self._states[key] = has_material
        if old != has_material:
            print(f"[上料点服务] UI写入: {key} → {'有料' if has_material else '无料'}", flush=True)

    def get_all_states(self) -> Dict[str, bool]:
        with self._lock:
            return dict(self._states)

    def has_material(self, feed_point: str, bin_prefix: str) -> bool:
        if feed_point not in FEED_POINT_MATERIALS:
            return True
        if bin_prefix.startswith('S'):
            material = SILO_MATERIAL.get(bin_prefix, 'stone')
        else:
            material = BIN_MATERIAL_SUFFIX.get(bin_prefix, 'stone')
        return self.get_state(feed_point, material)

    def _start_periodic_log(self):
        def _log_loop():
            while True:
                time.sleep(10)
                with self._lock:
                    states = dict(self._states)
                items = [f"{k}={states[k]}" for k in sorted(states.keys())]
                print(f"[上料点服务] 定时状态: {', '.join(items)}", flush=True)
        t = threading.Thread(target=_log_loop, daemon=True)
        t.start()