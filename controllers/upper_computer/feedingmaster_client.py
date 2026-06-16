"""
FeedingMaster 客户端 — Upper Computer 连接 :8896

发送传感器状态，接收控制指令。
"""
import json
import socket
import threading
import sys
from typing import Optional, Callable, Dict, Any, List


FM_HOST = '127.0.0.1'
FM_PORT = 8896


class FeedingMasterClient:
    """Upper Computer → FeedingMaster 通信客户端"""

    def __init__(self, host: str = FM_HOST, port: int = FM_PORT):
        self.host = host
        self.port = port
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._running = False
        self._recv_thread: Optional[threading.Thread] = None

        # 回调
        self._on_commands: Optional[Callable[[List[dict]], None]] = None

    def on_commands(self, callback: Callable[[List[dict]], None]):
        self._on_commands = callback

    def connect(self) -> bool:
        with self._lock:
            if self._sock:
                return True
            try:
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._sock.settimeout(3)
                self._sock.connect((self.host, self.port))
                self._sock.settimeout(None)
                self._running = True
                self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
                self._recv_thread.start()
                print(f"[Upper] 已连接 FeedingMaster {self.host}:{self.port}", flush=True)
                return True
            except Exception as e:
                print(f"[Upper] FeedingMaster 连接失败: {e}", file=sys.stderr)
                self._sock = None
                return False

    def disconnect(self):
        self._running = False
        with self._lock:
            sock = self._sock
            self._sock = None
        if sock:
            try:
                sock.close()
            except Exception:
                pass

    def send_sensor_states(self, data: dict):
        """发送传感器状态给 FeedingMaster"""
        payload = {"type": "sensor_states", "data": data}
        self._send(payload)

    def _send(self, data: dict):
        with self._lock:
            sock = self._sock
        if sock is None:
            return
        try:
            sock.sendall((json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"))
        except Exception:
            pass

    def _recv_loop(self):
        buf = b""
        while self._running:
            try:
                with self._lock:
                    sock = self._sock
                if sock is None:
                    break
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self._process(line.decode("utf-8").strip())
            except (ConnectionResetError, BrokenPipeError, OSError):
                break
            except Exception:
                break
        print("[Upper] FeedingMaster 连接断开", flush=True)
        self.disconnect()

    def _process(self, line: str):
        if not line:
            return
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return

        if msg.get("type") == "command" and self._on_commands:
            self._on_commands(msg)
