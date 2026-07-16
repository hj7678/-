"""
Stock Management 客户端基类 — 零外部依赖，FM 和 HMI 共用

提供 TCP JSON Lines 通信和持久连接管理。
"""
import json
import socket
import sys
import threading
import time
from typing import Dict, List, Optional

STOCK_HOST = '127.0.0.1'
STOCK_PORT = 8895


class BaseStockClient:
    """Stock Management TCP 客户端基类"""

    def __init__(self, host: str = STOCK_HOST, port: int = STOCK_PORT):
        self.host = host
        self.port = port
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._last_fail_time = 0.0  # 冷却: 5s内不重复重连

    def connect(self) -> bool:
        with self._lock:
            if self._sock:
                return True
            try:
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sock.settimeout(3)
                self._sock.connect((self.host, self.port))
                self._sock.settimeout(10)
                print(f"[Stock] 已连接 {self.host}:{self.port}", flush=True)
                return True
            except Exception as e:
                print(f"[Stock] 连接失败: {e}", file=sys.stderr)
                self._sock = None
                self._last_fail_time = time.time()
                return False

    def disconnect(self):
        with self._lock:
            sock = self._sock
            self._sock = None
        if sock:
            try:
                sock.close()
            except Exception:
                pass

    def _request(self, payload: dict) -> Optional[dict]:
        with self._lock:
            sock = self._sock
        if sock is None:
            return None
        # 冷却: 上次失败后5s内直接返回None，不重试
        if time.time() - self._last_fail_time < 5.0:
            return None
        try:
            sock.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            buf = b""
            while b"\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    self.disconnect()
                    self._last_fail_time = time.time()
                    return None
                buf += chunk
            return json.loads(buf.decode("utf-8").strip())
        except Exception:
            self.disconnect()
            self._last_fail_time = time.time()
            print(f"[Stock] 请求失败，已断开", flush=True)
            return None

    def get_all_levels(self) -> List[dict]:
        resp = self._request({"action": "get_all"})
        if resp and resp.get("ok"):
            return resp.get("data", [])
        return []