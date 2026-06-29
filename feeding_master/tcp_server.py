"""
FeedingMaster TCP Server — :8896

接收 Upper Computer 发来的传感器状态，推送控制指令回去。

协议: TCP JSON Lines

接收 (Upper → FM):
  {"type": "sensor_states", "data": {...}}
  {"type": "heartbeat"}

发送 (FM → Upper):
  {"type": "command", "commands": [...]}
"""
import json
import socket
import threading
import sys
from typing import Optional, Callable, Dict, Any


HOST = '127.0.0.1'
PORT = 8896


class FeedingMasterServer:
    """FeedingMaster 与 Upper Computer 之间的 TCP 通信"""

    def __init__(self, host: str = HOST, port: int = PORT):
        self.host = host
        self.port = port
        self._server: Optional[socket.socket] = None
        self._running = False
        self._seq = 0  # 消息序列号

        # 连接的 Upper Computer
        self._upper_socket: Optional[socket.socket] = None
        self._upper_lock = threading.Lock()

        # 接收回调
        self._on_sensor_states: Optional[Callable[[dict], None]] = None
        self._on_manual_start: Optional[Callable[[str, str], None]] = None
        self._on_manual_stop: Optional[Callable[[str], None]] = None
        self._on_emergency_stop: Optional[Callable[[], None]] = None
        self._on_belt_active: Optional[Callable[[str, bool], None]] = None

    # ── 回调注册 ──

    def on_sensor_states(self, callback: Callable[[dict], None]):
        self._on_sensor_states = callback

    def on_manual_start(self, callback):
        self._on_manual_start = callback

    def on_manual_stop(self, callback):
        self._on_manual_stop = callback

    def on_emergency_stop(self, callback):
        self._on_emergency_stop = callback

    def on_belt_active(self, callback):
        self._on_belt_active = callback

    # ── 发送控制指令 ──

    def send_commands(self, commands: list, route_info: dict = None, sched_info: dict = None, diag: list = None):
        """推送控制指令给 Upper Computer"""
        self._seq += 1
        payload = {
            "type": "command",
            "seq": self._seq,
            "commands": commands,
        }
        if route_info:
            payload["route_states"] = route_info
        if sched_info:
            payload["schedule"] = sched_info
        if diag:
            payload["diagnosis"] = diag
        self._send(payload)

    def send_state_snapshot(self, snapshot: dict):
        """推送状态快照 (也通过这个通道转发给诊断模块的话可另开端口)"""
        payload = {
            "type": "state_snapshot",
            "data": snapshot,
        }
        self._send(payload)

    def _send(self, data: dict):
        with self._upper_lock:
            sock = self._upper_socket
        if sock is None:
            return
        try:
            sock.sendall((json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            print(f"[FeedingMaster] 发送失败: {e}", file=sys.stderr)
            self._close_upper()

    # ── 服务生命周期 ──

    def start(self):
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self.host, self.port))
        self._server.listen(1)  # 只接受一个上位机连接
        self._running = True
        print(f"[FeedingMaster] 服务已启动 {self.host}:{self.port}", flush=True)

        while self._running:
            try:
                self._server.settimeout(1.0)
                try:
                    client, addr = self._server.accept()
                    print(f"[FeedingMaster] Upper Computer 已连接: {addr}", flush=True)
                    self._close_upper()  # 断开旧连接
                    with self._upper_lock:
                        self._upper_socket = client
                    self._handle_upper(client, addr)
                except socket.timeout:
                    pass
            except Exception as e:
                if self._running:
                    print(f"[FeedingMaster] accept 错误: {e}", file=sys.stderr)

    def stop(self):
        self._running = False
        self._close_upper()
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
        print("[FeedingMaster] 服务已停止", flush=True)

    def _close_upper(self):
        with self._upper_lock:
            sock = self._upper_socket
            self._upper_socket = None
        if sock:
            try:
                sock.close()
            except Exception:
                pass

    def _handle_upper(self, client: socket.socket, addr: tuple):
        buf = b""
        try:
            client.settimeout(None)  # 不超时, 等桥接推送
            while self._running:
                chunk = client.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self._process_upper_msg(line.decode("utf-8").strip())
        except socket.timeout:
            pass
        except ConnectionResetError:
            print(f"[FeedingMaster] Upper Computer 断开: {addr}", flush=True)
        except Exception as e:
            print(f"[FeedingMaster] Upper 通信错误: {e}", file=sys.stderr)
        finally:
            self._close_upper()
            try:
                client.close()
            except Exception:
                pass

    def _process_upper_msg(self, line: str):
        if not line:
            return
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type", "")
        if msg_type == "sensor_states" and self._on_sensor_states:
            self._on_sensor_states(msg.get("data", {}))
        elif msg_type == "manual_start" and self._on_manual_start:
            self._on_manual_start(msg.get("bin_id", ""), msg.get("route_id", ""))
        elif msg_type == "manual_stop" and self._on_manual_stop:
            self._on_manual_stop(msg.get("route_id", ""))
        elif msg_type == "emergency_stop" and self._on_emergency_stop:
            self._on_emergency_stop()
            # 发送 ACK 确认急停已执行
            ack_id = msg.get("ack_id")
            if ack_id is not None:
                self._send({"type": "ack", "ack_id": ack_id, "action": "emergency_stop"})
        elif msg_type == "belt_active" and self._on_belt_active:
            self._on_belt_active(msg.get("belt_id", ""), msg.get("active", False))
        elif msg_type == "heartbeat":
            pass  # 心跳忽略
