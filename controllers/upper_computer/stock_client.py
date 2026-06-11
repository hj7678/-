"""
Stock Management 客户端 — Upper Computer 连接 :8895

获取料位数据用于 HMI 显示。
"""
import json
import socket
from typing import Optional, List


STOCK_HOST = '127.0.0.1'
STOCK_PORT = 8895


class StockClient:
    """Upper Computer → Stock Management 客户端"""

    def __init__(self, host: str = STOCK_HOST, port: int = STOCK_PORT):
        self.host = host
        self.port = port

    def _request(self, payload: dict) -> Optional[dict]:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect((self.host, self.port))
            sock.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            buf = b""
            while b"\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
            return json.loads(buf.decode("utf-8").strip())
        except Exception:
            return None
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    def get_all_levels(self) -> List[dict]:
        resp = self._request({"action": "get_all"})
        if resp and resp.get("ok"):
            return resp.get("data", [])
        return []
