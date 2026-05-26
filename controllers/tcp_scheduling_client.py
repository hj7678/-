"""
TCP 调度客户端 —— 向 scheduling 服务发送料仓数据、接收上料顺序

事件驱动模式：仅在有需求时（皮带空闲、上料完成）请求调度，不轮询。
Python 原生线程 + socket，通过 pyqtSignal 跨线程通信。
"""
import json
import socket
import sys
import threading
import time
from typing import Any, Dict, Optional, List

from PyQt5.QtCore import QObject, pyqtSignal

SCHEDULING_HOST = '127.0.0.1'
SCHEDULING_PORTS = {'D7': 8891, 'D8': 8892, 'D9': 8893, 'D6': 8894}


class TcpSchedulingClient(QObject):
    """TCP 调度客户端 —— 事件驱动，信号通知主线程"""

    schedule_received = pyqtSignal(str, object)   # belt_id, dict
    connection_changed = pyqtSignal(str, bool)    # belt_id, connected
    send_error = pyqtSignal(str, str)             # belt_id, error_msg

    def __init__(self, host: str = None):
        super().__init__()
        self.host = host or SCHEDULING_HOST
        self._sockets: Dict[str, Optional[socket.socket]] = {}
        self._connected: Dict[str, bool] = {}
        self._bins_lock = threading.Lock()
        self._bins_data: Dict[str, dict] = {}
        self._pending_requests: set = set()
        self._request_lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @property
    def is_connected(self, belt_id: str = None) -> bool:
        if belt_id:
            return self._connected.get(belt_id, False)
        return any(self._connected.values())

    def update_bins(self, belt_id: str, bins: List[Dict], cart_position: int = None,
                    left_divert: bool = False, right_divert: bool = False):
        with self._bins_lock:
            self._bins_data[belt_id] = {
                'bins': bins, 'cart_position': cart_position,
                'left_divert': left_divert, 'right_divert': right_divert,
            }

    def request_schedule(self, belt_id: str):
        """请求一次调度计算（由控制器在需要时调用）"""
        with self._request_lock:
            self._pending_requests.add(belt_id)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        for belt_id in list(self._sockets.keys()):
            self._disconnect(belt_id)
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def _run(self):
        print("[SchedClient] 事件驱动线程启动", file=sys.stderr)
        while self._running:
            # 维护连接
            for belt_id in list(SCHEDULING_PORTS.keys()):
                if not self._running:
                    break
                if not self._connected.get(belt_id):
                    self._try_connect(belt_id)

            # 处理待处理的调度请求
            with self._request_lock:
                pending = list(self._pending_requests)
                self._pending_requests.clear()

            for belt_id in pending:
                if not self._running:
                    break
                if self._connected.get(belt_id):
                    if not self._send_and_receive(belt_id):
                        # 发送失败，重新加入待处理队列，等重连后重试
                        with self._request_lock:
                            self._pending_requests.add(belt_id)

            time.sleep(0.5)

    def _try_connect(self, belt_id: str):
        port = SCHEDULING_PORTS.get(belt_id)
        if not port:
            return
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((self.host, port))
            sock.settimeout(None)
            self._sockets[belt_id] = sock
            self._connected[belt_id] = True
            print(f"[SchedClient] {belt_id} 已连接 {self.host}:{port}", file=sys.stderr)
            self.connection_changed.emit(belt_id, True)
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            self._connected[belt_id] = False
            print(f"[SchedClient] {belt_id} 连接失败 {self.host}:{port} — {e}", file=sys.stderr)

    def _disconnect(self, belt_id: str):
        sock = self._sockets.pop(belt_id, None)
        if sock:
            try:
                sock.close()
            except OSError:
                pass
        self._connected[belt_id] = False

    def _send_and_receive(self, belt_id: str) -> bool:
        with self._bins_lock:
            data = self._bins_data.get(belt_id, {})
        bins = data.get('bins', []) if isinstance(data, dict) else []
        cart_position = data.get('cart_position', None) if isinstance(data, dict) else None
        left_divert = data.get('left_divert', False) if isinstance(data, dict) else False
        right_divert = data.get('right_divert', False) if isinstance(data, dict) else False

        payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "belt_id": belt_id,
            "boost_mode": False,
            "bins": bins,
        }
        if cart_position is not None:
            payload["cart_position"] = cart_position
        payload["left_divert"] = left_divert
        payload["right_divert"] = right_divert

        sock = self._sockets.get(belt_id)
        if not sock:
            return False
        try:
            json_str = json.dumps(payload, ensure_ascii=False)
            sock.sendall((json_str + "\n").encode("utf-8"))

            buf = b""
            sock.settimeout(30.0)
            while b"\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
            sock.settimeout(None)

            if buf:
                line = buf.decode("utf-8").strip()
                if line:
                    response = json.loads(line)
                    self.schedule_received.emit(belt_id, response)
            return True
        except (BrokenPipeError, ConnectionResetError, OSError, json.JSONDecodeError) as e:
            print(f"[SchedClient] {belt_id} 通信错误: {e}", file=sys.stderr)
            self._disconnect(belt_id)
            self.connection_changed.emit(belt_id, False)
            return False
