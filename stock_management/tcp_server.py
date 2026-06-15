"""
Stock Management TCP Server — :8895

纯数据中转：接收仿真端推送的料位，提供给 FeedingMaster 查询。

协议: TCP JSON Lines

请求:
  {"action": "get_all"}
  {"action": "get_levels", "bin_ids": ["P1-1"]}
  {"action": "set_level", "bin_id": "P1-1", "level_tons": 45.0}
  {"action": "set_levels_batch", "data": {"P1-1": 45.0, "P1-2": 38.5}}
  {"action": "randomize", "lo_pct": 25.0, "hi_pct": 90.0}
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
        print(f"[StockMgmt] 服务已启动 {self.host}:{self.port}", flush=True)

        loop_count = 0
        while self._running:
            loop_count += 1
            try:
                self._server.settimeout(1.0)
                try:
                    client, addr = self._server.accept()
                    t = threading.Thread(target=self._handle, args=(client, addr), daemon=True)
                    t.start()
                except socket.timeout:
                    pass
            except Exception as e:
                if self._running:
                    print(f"[StockMgmt] accept 错误: {e}", file=sys.stderr)
            # 每30秒详细心跳
            if loop_count % 30 == 0:
                s = self.store.get_status_summary()
                print(f"[StockMgmt] ══ 30s心跳 ══", flush=True)
                print(f"  总料位: {s['total_tons']:.0f}t (40仓)", flush=True)
                lo = ', '.join(f'{b}={p:.0f}%({r:.2f}t/s)' for b, p, r in s['lowest'])
                hi = ', '.join(f'{b}={p:.0f}%({r:.2f}t/s)' for b, p, r in s['highest'])
                print(f"  最低5仓: {lo}", flush=True)
                print(f"  最高5仓: {hi}", flush=True)
                if s['feeding']:
                    print(f"  补料中: {', '.join(s['feeding'])}", flush=True)
                if s['discharging']:
                    print(f"  出料中: {', '.join(s['discharging'])}", flush=True)

    def stop(self):
        self._running = False
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
        except (socket.timeout, ConnectionResetError):
            pass
        except Exception as e:
            print(f"[StockMgmt] 客户端错误: {e}", file=sys.stderr)
        finally:
            try:
                client.close()
            except Exception:
                pass

    def _process(self, line: str) -> dict:
        if not line:
            return {"ok": False, "error": "empty"}
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            return {"ok": False, "error": str(e)}

        action = req.get("action", "")
        try:
            if action == "get_all":
                return {"ok": True, "data": self.store.get_all()}
            elif action == "get_levels":
                return {"ok": True, "data": self.store.get_levels(req.get("bin_ids", []))}
            elif action == "get_bin":
                return {"ok": True, "data": self.store.get_bin(req.get("bin_id", ""))}
            elif action == "set_level":
                self.store.set_level(req["bin_id"], req["level_tons"])
                return {"ok": True}
            elif action == "set_consumption":
                self.store.set_consumption_rate(req["bin_id"], req.get("rate", 0.01))
                return {"ok": True}
            elif action == "set_consumption_batch":
                for bid, rate in req.get("rates", {}).items():
                    self.store.set_consumption_rate(bid, float(rate))
                return {"ok": True}
            elif action == "set_levels_batch":
                self.store.set_levels_batch(req.get("data", {}))
                return {"ok": True}
            elif action == "randomize":
                self.store.randomize_levels(
                    req.get("lo_pct", 25.0), req.get("hi_pct", 90.0))
                return {"ok": True}
            elif action == "mark_feeding":
                self.store.mark_feeding(req["bin_id"])
                return {"ok": True}
            elif action == "unmark_feeding":
                self.store.unmark_feeding(req["bin_id"])
                return {"ok": True}
            elif action == "mark_discharging":
                self.store.mark_discharging(req["bin_id"])
                return {"ok": True}
            elif action == "unmark_discharging":
                self.store.unmark_discharging(req["bin_id"])
                return {"ok": True}
            elif action == "get_status":
                return {"ok": True, "data": self.store.get_status_summary()}
            else:
                return {"ok": False, "error": f"unknown action: {action}"}
        except KeyError as e:
            return {"ok": False, "error": f"missing field: {e}"}
