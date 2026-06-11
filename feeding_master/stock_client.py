"""
Stock Management 客户端 — 连接 :8895，拉取料位数据
"""
import json
import socket
import sys
import time
from typing import Dict, List, Optional


STOCK_HOST = '127.0.0.1'
STOCK_PORT = 8895


class StockClient:
    """Stock Management TCP 客户端"""

    def __init__(self, host: str = STOCK_HOST, port: int = STOCK_PORT):
        self.host = host
        self.port = port
        self._sock: Optional[socket.socket] = None
        self._connected = False

    def connect(self) -> bool:
        if self._connected:
            return True
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(3)
            self._sock.connect((self.host, self.port))
            self._sock.settimeout(10)
            self._connected = True
            print(f"[FeedingMaster] 已连接 Stock Management {self.host}:{self.port}", flush=True)
            return True
        except Exception as e:
            print(f"[FeedingMaster] Stock 连接失败: {e}", file=sys.stderr)
            self._sock = None
            return False

    def disconnect(self):
        self._connected = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _request(self, payload: dict) -> Optional[dict]:
        if not self._connected or self._sock is None:
            return None
        try:
            self._sock.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            buf = b""
            while b"\n" not in buf:
                chunk = self._sock.recv(4096)
                if not chunk:
                    self.disconnect()
                    return None
                buf += chunk
            return json.loads(buf.decode("utf-8").strip())
        except Exception as e:
            print(f"[FeedingMaster] Stock 请求失败: {e}", file=sys.stderr)
            self.disconnect()
            return None

    def get_all_levels(self) -> List[dict]:
        resp = self._request({"action": "get_all"})
        if resp and resp.get("ok"):
            return resp.get("data", [])
        return []

    def get_levels(self, bin_ids: List[str]) -> List[dict]:
        resp = self._request({"action": "get_levels", "bin_ids": bin_ids})
        if resp and resp.get("ok"):
            return resp.get("data", [])
        return []

    def start_feeding(self, bin_id: str):
        self._request({"action": "start_feeding", "bin_id": bin_id})

    def stop_feeding(self, bin_id: str):
        self._request({"action": "stop_feeding", "bin_id": bin_id})
