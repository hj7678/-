"""
Fault Diagnosis TCP Server — :8897

接收 FeedingMaster 发来的状态快照，运行诊断，回传结果给 Upper Computer。

协议:
  FeedingMaster → :8897: 状态快照 JSON
  Upper Computer → :8897: 查询诊断结果

状态快照格式见 feeding-master-plan.md §2.3
"""
import json
import socket
import threading
import sys
import time
from typing import Optional, Dict, List


HOST = '127.0.0.1'
PORT = 8897


class DiagnosisServer:
    """故障诊断 TCP 服务"""

    def __init__(self, host: str = HOST, port: int = PORT):
        self.host = host
        self.port = port
        self._server: Optional[socket.socket] = None
        self._running = False

        # 真实诊断引擎
        from fault_diagnosis.engine import DiagnosisEngine
        self._engine = DiagnosisEngine()

        # 最新诊断结果缓存
        self._latest_results: List[dict] = []
        self._results_lock = threading.Lock()

    def start(self):
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self.host, self.port))
        self._server.listen(5)
        self._running = True
        print(f"[Diagnosis] 服务已启动 {self.host}:{self.port}", flush=True)

        while self._running:
            try:
                self._server.settimeout(1.0)
                try:
                    client, addr = self._server.accept()
                    print(f"[Diagnosis] 连接: {addr}", flush=True)
                    t = threading.Thread(target=self._handle, args=(client, addr), daemon=True)
                    t.start()
                except socket.timeout:
                    pass
            except Exception as e:
                if self._running:
                    print(f"[Diagnosis] accept 错误: {e}", file=sys.stderr)

    def stop(self):
        self._running = False
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
        print("[Diagnosis] 服务已停止", flush=True)

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
                    if resp is not None:
                        client.sendall((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
        except socket.timeout:
            pass
        except ConnectionResetError:
            pass
        except Exception as e:
            print(f"[Diagnosis] 客户端 {addr} 错误: {e}", file=sys.stderr)
        finally:
            try:
                client.close()
            except Exception:
                pass

    def _process(self, line: str) -> Optional[dict]:
        if not line:
            return None
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return {"ok": False, "error": "invalid json"}

        msg_type = msg.get("type", "")

        if msg_type == "state_snapshot":
            # 接收状态快照，运行诊断
            results = self._run_diagnosis(msg.get("data", {}))
            with self._results_lock:
                self._latest_results = results
            # 不返回（Fire and forget）
            return None

        elif msg_type == "get_results":
            # 查询最新诊断结果
            with self._results_lock:
                return {
                    "ok": True,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "results": list(self._latest_results),
                }

        return {"ok": False, "error": f"unknown type: {msg_type}"}

    def _run_diagnosis(self, snapshot: dict) -> List[dict]:
        """运行真实诊断引擎"""
        from fault_diagnosis.types import SystemSnapshot

        # 构建 SystemSnapshot
        sys_snap = SystemSnapshot()

        # 路线状态
        for route_id, info in snapshot.get("active_routes", {}).items():
            sys_snap.route_states[route_id] = info.get("state", "idle")

        # 皮带
        for b in snapshot.get("belts", []):
            cid = b["id"]
            sys_snap.conveyors[cid] = type('obj', (), {
                'is_running': b.get("is_running", False),
                'speed': b.get("speed", 0),
            })()

        # 接近开关
        for s in snapshot.get("sensors", []):
            sid = s["id"]
            sys_snap.sensors[sid] = type('obj', (), {
                'is_active': s.get("is_active", False),
                'conveyor': s.get("conveyor", ""),
            })()

        # 中转斗
        for h in snapshot.get("hoppers", []):
            hid = h["id"]
            sys_snap.hoppers[hid] = type('obj', (), {
                'is_open': h.get("is_open", False),
                'weight': h.get("weight", 0),
                'stored_materials': [None] * h.get("stored_count", 0),
            })()

        # 小车
        for c in snapshot.get("carts", []):
            cid = c["id"]
            sys_snap.carts[cid] = type('obj', (), {
                'position': c.get("position", 1),
                'target': c.get("target", 1),
                'moving': c.get("moving", False),
                'divert': c.get("divert", [False, False]),
            })()

        # 运行诊断
        try:
            results = self._engine.diagnose(sys_snap)
            return [
                {
                    "sensor_id": r.sensor_id if hasattr(r, 'sensor_id') else "",
                    "fault_type": r.fault_type if hasattr(r, 'fault_type') else "unknown",
                    "confidence": r.confidence if hasattr(r, 'confidence') else 0.0,
                    "description": r.description if hasattr(r, 'description') else str(r),
                }
                for r in results
            ]
        except Exception as e:
            return [{"fault_type": "error", "description": str(e), "confidence": 0.0}]
