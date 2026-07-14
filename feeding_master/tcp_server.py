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
PORT = 8896       # 仿真 HMI 端口（全量发送）
REAL_PORT = 8897  # 真实上位机端口（增量发送）


class FeedingMasterServer:
    """FeedingMaster 与 Upper Computer 之间的 TCP 通信（双端口：仿真全量 + 真实增量）"""

    def __init__(self, host: str = HOST, port: int = PORT, real_port: int = REAL_PORT):
        self.host = host
        self.port = port
        self.real_port = real_port
        self._server: Optional[socket.socket] = None
        self._real_server: Optional[socket.socket] = None
        self._running = False
        self._seq = 0
        self._real_seq = 0  # 真实上位机独立序号，不与仿真 HMI 共享

        # 仿真 HMI 连接（全量发送）
        self._upper_sockets: list = []
        self._upper_lock = threading.Lock()

        # 真实上位机连接（增量发送）
        self._real_sockets: list = []
        self._real_lock = threading.Lock()

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
        """推送控制指令给仿真 HMI（:8896，全量发送）"""
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

    def send_commands_real(self, commands: list, route_info: dict = None, sched_info: dict = None, diag: list = None):
        """推送增量控制指令给真实上位机（仅 :8897）"""
        self._real_seq += 1
        payload = {
            "type": "command",
            "seq": self._real_seq,
            "commands": commands,
        }
        if route_info:
            payload["route_states"] = route_info
        if sched_info:
            payload["schedule"] = sched_info
        if diag:
            payload["diagnosis"] = diag
        self._send_real(payload)

    def send_state_snapshot(self, snapshot: dict):
        """推送状态快照 (也通过这个通道转发给诊断模块的话可另开端口)"""
        payload = {
            "type": "state_snapshot",
            "data": snapshot,
        }
        self._send(payload)

    def send_levels(self, levels: dict):
        """推送料位数据给上位机 (每5s)"""
        payload = {
            "type": "level_report",
            "levels": levels,
        }
        self._send(payload)

    def send_diagnosis(self, diag: list):
        """推送诊断结果（变化时）"""
        if not diag:
            return
        payload = {
            "type": "diagnosis",
            "data": diag,
        }
        self._send(payload)

    def _send(self, data: dict):
        """广播消息给所有仿真 HMI 连接（:8896）"""
        with self._upper_lock:
            sockets = list(self._upper_sockets)
        payload = (json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8")
        for sock in sockets:
            try:
                sock.sendall(payload)
            except (BrokenPipeError, ConnectionResetError, OSError):
                self._remove_upper(sock)

    def _send_real(self, data: dict):
        """广播消息给所有真实上位机连接（:8897）"""
        with self._real_lock:
            sockets = list(self._real_sockets)
        payload = (json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8")
        for sock in sockets:
            try:
                sock.sendall(payload)
            except (BrokenPipeError, ConnectionResetError, OSError):
                self._remove_real(sock)

    # ── 服务生命周期 ──

    def start(self):
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self.host, self.port))
        self._server.listen(5)  # 支持多客户端同时连接
        self._running = True
        print(f"[FeedingMaster] 服务已启动 {self.host}:{self.port}", flush=True)

        # 启动真实上位机端口 accept 线程
        self._real_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._real_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._real_server.bind((self.host, self.real_port))
        self._real_server.listen(5)
        threading.Thread(target=self._real_accept_loop, daemon=True).start()
        print(f"[FeedingMaster] 真实上位机端口 {self.host}:{self.real_port} (增量发送)", flush=True)

        while self._running:
            try:
                self._server.settimeout(1.0)
                try:
                    client, addr = self._server.accept()
                    print(f"[FeedingMaster] 上位机已连接: {addr}", flush=True)
                    with self._upper_lock:
                        self._upper_sockets.append(client)
                    threading.Thread(target=self._handle_upper, args=(client, addr), daemon=True).start()
                except socket.timeout:
                    pass
            except Exception as e:
                if self._running:
                    print(f"[FeedingMaster] accept 错误: {e}", file=sys.stderr)

    def stop(self):
        self._running = False
        self._close_all()
        self._close_all_real()
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
        if self._real_server:
            try:
                self._real_server.close()
            except Exception:
                pass
        print("[FeedingMaster] 服务已停止", flush=True)

    def _remove_upper(self, sock: socket.socket):
        with self._upper_lock:
            if sock in self._upper_sockets:
                self._upper_sockets.remove(sock)
        try:
            sock.close()
        except Exception:
            pass

    def _close_all(self):
        with self._upper_lock:
            sockets = list(self._upper_sockets)
            self._upper_sockets.clear()
        for sock in sockets:
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
                    self._process_upper_msg(line.decode("utf-8").strip(), 'sim')
        except socket.timeout:
            pass
        except ConnectionResetError:
            print(f"[FeedingMaster] 上位机断开: {addr}", flush=True)
        except Exception as e:
            print(f"[FeedingMaster] 上位机通信错误: {e}", file=sys.stderr)
        finally:
            self._remove_upper(client)
            try:
                client.close()
            except Exception:
                pass

    # ── 真实上位机端口 (:8897) ──

    def _real_accept_loop(self):
        """独立线程 accept 真实上位机连接"""
        while self._running:
            try:
                self._real_server.settimeout(1.0)
                try:
                    client, addr = self._real_server.accept()
                    print(f"[FeedingMaster] 真实上位机已连接: {addr}", flush=True)
                    with self._real_lock:
                        self._real_sockets.append(client)
                    threading.Thread(target=self._handle_real, args=(client, addr), daemon=True).start()
                except socket.timeout:
                    pass
            except Exception as e:
                if self._running:
                    print(f"[FeedingMaster] 真实端口 accept 错误: {e}", file=sys.stderr)

    def _handle_real(self, client: socket.socket, addr: tuple):
        """处理真实上位机连接（上行数据接收，与仿真 HMI 共用回调）"""
        buf = b""
        try:
            client.settimeout(None)
            while self._running:
                chunk = client.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self._process_upper_msg(line.decode("utf-8").strip(), 'real')
        except socket.timeout:
            pass
        except ConnectionResetError:
            print(f"[FeedingMaster] 真实上位机断开: {addr}", flush=True)
        except Exception as e:
            print(f"[FeedingMaster] 真实上位机通信错误: {e}", file=sys.stderr)
        finally:
            self._remove_real(client)
            try:
                client.close()
            except Exception:
                pass

    def _remove_real(self, sock: socket.socket):
        with self._real_lock:
            if sock in self._real_sockets:
                self._real_sockets.remove(sock)
        try:
            sock.close()
        except Exception:
            pass

    def _close_all_real(self):
        with self._real_lock:
            sockets = list(self._real_sockets)
            self._real_sockets.clear()
        for sock in sockets:
            try:
                sock.close()
            except Exception:
                pass

    def _process_upper_msg(self, line: str, source: str = 'sim'):
        if not line:
            return
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type", "")
        # 广播上游消息给所有监听客户端（用于 fm_monitor 查看完整通讯）
        if msg_type == "sensor_states":
            self._send({"type": "echo_sensor_states", "data": msg.get("data", {})})
        elif msg_type in ("manual_start", "manual_stop", "belt_active", "emergency_stop"):
            self._send({"type": f"echo_{msg_type}", "data": msg})

        if msg_type == "sensor_states" and self._on_sensor_states:
            self._on_sensor_states(msg.get("data", {}), source)
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
