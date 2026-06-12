"""
Stock Management 客户端 — 持久连接

获取料位数据用于 HMI 显示。
"""
import json
import socket
import sys
import threading
from typing import Optional, List

STOCK_HOST = '127.0.0.1'
STOCK_PORT = 8895


class StockClient:
    """持久连接的 Stock Management 客户端"""

    def __init__(self, host: str = STOCK_HOST, port: int = STOCK_PORT):
        self.host = host
        self.port = port
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()

    def connect(self) -> bool:
        with self._lock:
            if self._sock:
                return True
            try:
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sock.settimeout(3)
                self._sock.connect((self.host, self.port))
                self._sock.settimeout(10)
                return True
            except Exception as e:
                print(f"[Upper] Stock 连接失败: {e}", file=sys.stderr)
                self._sock = None
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
        try:
            sock.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            buf = b""
            while b"\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    self.disconnect()
                    return None
                buf += chunk
            return json.loads(buf.decode("utf-8").strip())
        except Exception:
            self.disconnect()
            return None

    def set_level(self, bin_id: str, level_tons: float):
        if not self._sock:
            self.connect()
        self._request({"action": "set_level", "bin_id": bin_id, "level_tons": level_tons})

    def randomize_all(self, lo_pct: float = 25.0, hi_pct: float = 90.0):
        if not self._sock:
            self.connect()
        self._request({"action": "randomize", "lo_pct": lo_pct, "hi_pct": hi_pct})

    def get_all_levels(self) -> List[dict]:
        if not self._sock:
            self.connect()
        resp = self._request({"action": "get_all"})
        if resp and resp.get("ok"):
            return resp.get("data", [])
        return []
