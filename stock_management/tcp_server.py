"""
Stock Management TCP Server — :8895

协议: TCP JSON Lines (每行一个 JSON，以 \n 分隔)

请求:
  {"action": "get_levels", "bin_ids": ["P1-1", "P1-2"]}
  {"action": "get_all"}
  {"action": "get_bin", "bin_id": "P1-1"}
  {"action": "set_level", "bin_id": "P1-1", "level_tons": 45.0}
  {"action": "set_consumption", "bin_id": "P1-1", "rate": 0.02}
  {"action": "start_feeding", "bin_id": "P1-1"}
  {"action": "stop_feeding", "bin_id": "P1-1"}

响应:
  {"ok": true, "data": ...}
  {"ok": false, "error": "..."}
"""
import json
import socket
import threading
import sys
from typing import Optional

from stock_management.bin_store import BinStore

HOST = '127.0.0.1'
PORT = 8895


class StockServer:
    """料仓库存管理 TCP 服务"""

    def __init__(self, host: str = HOST, port: int = PORT):
        self.host = host
        self.port = port
        self.store = BinStore()
        self._server: Optional[socket.socket] = None
        self._running = False

    def start(self):
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self.host, self.port))
        self._server.listen(5)
        self._running = True
        self.store.start()
        print(f"[StockMgmt] 服务已启动 {self.host}:{self.port}", flush=True)

        while self._running:
            try:
                self._server.settimeout(1.0)
                try:
                    client, addr = self._server.accept()
                    print(f"[StockMgmt] 连接: {addr}", flush=True)
                    t = threading.Thread(target=self._handle, args=(client, addr), daemon=True)
                    t.start()
                except socket.timeout:
                    pass
            except Exception as e:
                if self._running:
                    print(f"[StockMgmt] accept 错误: {e}", flush=True)

    def stop(self):
        self._running = False
        self.store.stop()
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
        print("[StockMgmt] 服务已停止", flush=True)

    def _handle(self, client: socket.socket, addr: tuple):
        buf = b""
        try:
            client.settimeout(30.0)
            while self._running:
                chunk = client.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    resp = self._process(line.decode("utf-8").strip())
                    client.sendall((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
        except socket.timeout:
            pass
        except ConnectionResetError:
            pass
        except Exception as e:
            print(f"[StockMgmt] 客户端 {addr} 错误: {e}", file=sys.stderr)
        finally:
            try:
                client.close()
            except Exception:
                pass

    def _process(self, line: str) -> dict:
        if not line:
            return {"ok": False, "error": "empty request"}
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            return {"ok": False, "error": f"invalid json: {e}"}

        action = req.get("action", "")
        try:
            if action == "get_levels":
                data = self.store.get_levels(req.get("bin_ids", []))
                return {"ok": True, "data": data}
            elif action == "get_all":
                data = self.store.get_all()
                return {"ok": True, "data": data}
            elif action == "get_bin":
                data = self.store.get_bin(req.get("bin_id", ""))
                return {"ok": True, "data": data}
            elif action == "set_level":
                self.store.set_level(req["bin_id"], req["level_tons"])
                return {"ok": True}
            elif action == "set_consumption":
                self.store.set_consumption_rate(req["bin_id"], req.get("rate", 0.01))
                return {"ok": True}
            elif action == "start_feeding":
                self.store.start_feeding(req["bin_id"])
                return {"ok": True}
            elif action == "stop_feeding":
                self.store.stop_feeding(req["bin_id"])
                return {"ok": True}
            elif action == "randomize":
                self.store.randomize_levels(
                    req.get("lo_pct", 25.0), req.get("hi_pct", 90.0))
                return {"ok": True}
            else:
                return {"ok": False, "error": f"unknown action: {action}"}
        except KeyError as e:
            return {"ok": False, "error": f"missing field: {e}"}
