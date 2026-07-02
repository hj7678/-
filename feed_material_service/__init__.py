"""上料点原料状态服务端
负责存储上料点各物料的有料/无料状态，供 FM 查询和 UI 设置。
"""

import threading
import time
import json
import socket
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
        """获取指定上料点指定物料的有料状态"""
        with self._lock:
            return self._states.get(_state_key(feed_point, material), True)

    def set_state(self, key: str, has_material: bool):
        """设置上料点物料状态（UI 控制面板调用）
        key 格式: feed2_2_stone, feed3_10mm 等
        """
        old = self._states.get(key)
        with self._lock:
            self._states[key] = has_material
        if old != has_material:
            print(f"[上料点服务] UI写入: {key} → {'有料' if has_material else '无料'}", flush=True)

    def get_all_states(self) -> Dict[str, bool]:
        """获取全部状态"""
        with self._lock:
            return dict(self._states)

    def _start_periodic_log(self):
        """启动定时日志线程"""
        def _log_loop():
            while True:
                time.sleep(10)
                with self._lock:
                    states = dict(self._states)
                items = [f"{k}={states[k]}" for k in sorted(states.keys())]
                print(f"[上料点服务] 定时状态: {', '.join(items)}", flush=True)
        t = threading.Thread(target=_log_loop, daemon=True)
        t.start()

    def start_server(self, host='127.0.0.1', port=9010):
        """启动 TCP 服务端，供独立终端连接"""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen(5)
        print(f"[上料点服务] TCP 服务端已启动, 端口 {port}", flush=True)

        def _serve():
            while True:
                try:
                    conn, addr = server.accept()
                    t = threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True)
                    t.start()
                except Exception:
                    break

        t = threading.Thread(target=_serve, daemon=True)
        t.start()

    def _handle_client(self, conn, addr):
        try:
            data = conn.recv(4096).decode('utf-8')
            msg = json.loads(data) if data.strip() else {}
            msg_type = msg.get('type', '')
            if msg_type == 'get_states':
                resp = {'type': 'feed_material_rsp', 'states': self.get_all_states()}
            elif msg_type == 'set_state':
                key = msg.get('key', '')
                value = msg.get('value', True)
                self.set_state(key, value)
                resp = {'type': 'ok'}
            else:
                resp = {'type': 'error', 'message': f'unknown: {msg_type}'}
            conn.sendall(json.dumps(resp).encode('utf-8'))
        except Exception:
            pass
        finally:
            conn.close()

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