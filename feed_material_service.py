"""上料点原料状态服务端
负责存储上料点各物料的有料/无料状态，供 FM 查询和 UI 设置。
"""

import threading
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
    'feed2_2': ['stone', '10mm', '20mm'],
    'feed3': ['stone', '10mm'],
}

# S仓 → 物料类型映射
SILO_MATERIAL = {
    'S1': 'stone', 'S2': 'stone', 'S3': 'stone',
    'S4': '10mm', 'S5': '10mm', 'S6': '10mm',
    'S7': '20mm', 'S8': '20mm', 'S9': '20mm',
}


def _state_key(feed_point: str, material: str) -> str:
    return f"{feed_point}_{material}"


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

    @classmethod
    def instance(cls) -> 'FeedMaterialService':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get_state(self, feed_point: str, material: str) -> bool:
        """获取指定上料点指定物料的有料状态"""
        with self._lock:
            return self._states.get(_state_key(feed_point, material), True)

    def set_state(self, key: str, has_material: bool):
        """设置上料点物料状态
        key 格式: feed2_2_stone, feed3_10mm 等
        """
        with self._lock:
            self._states[key] = has_material

    def get_all_states(self) -> Dict[str, bool]:
        """获取全部状态"""
        with self._lock:
            return dict(self._states)

    def has_material(self, feed_point: str, bin_prefix: str) -> bool:
        """根据上料点和目标仓前缀判断是否有料
        feed_point: 上料点ID (feed2_2, feed3)
        bin_prefix: 目标仓前缀 (P1, P2, P3, P4, S1-S9)
        """
        if feed_point not in FEED_POINT_MATERIALS:
            return True  # 非物料级上料点，默认有料

        if bin_prefix.startswith('S'):
            material = SILO_MATERIAL.get(bin_prefix, 'stone')
        else:
            material = BIN_MATERIAL_SUFFIX.get(bin_prefix, 'stone')

        return self.get_state(feed_point, material)

    def get_material_key(self, feed_point: str, bin_prefix: str) -> str:
        """获取物料激光传感器 key"""
        if feed_point not in FEED_POINT_MATERIALS:
            return feed_point
        if bin_prefix.startswith('S'):
            material = SILO_MATERIAL.get(bin_prefix, 'stone')
        else:
            material = BIN_MATERIAL_SUFFIX.get(bin_prefix, 'stone')
        return _state_key(feed_point, material)