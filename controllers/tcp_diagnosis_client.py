"""
TCP 诊断客户端 —— 向 tcp_diagnosis 服务发送传感器数据、接收诊断结果

QThread + QTimer 模式，与 TcpDataSender 一致，不阻塞 UI 线程。
"""
import json
import socket
import time
from typing import Any, Dict, Optional

from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal, QMutex, QMutexLocker

import config

DIAGNOSIS_HOST = '127.0.0.1'
DIAGNOSIS_PORT = 8890
DIAGNOSIS_INTERVAL_MS = 500


class DiagnosisWorker(QObject):
    """工作线程：TCP 连接、发送传感器数据、接收诊断结果"""

    results_received = pyqtSignal(list)
    connection_changed = pyqtSignal(bool)
    send_error = pyqtSignal(str)

    def __init__(self, host: str, port: int, interval_ms: int):
        super().__init__()
        self.host = host
        self.port = port
        self.interval_ms = interval_ms
        self._socket: Optional[socket.socket] = None
        self._connected = False
        self._data: Dict[str, Any] = {}
        self._mutex = QMutex()
        self._reconnect_backoff = 0
        self._timer: Optional[QTimer] = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def update_data(self, data: Dict[str, Any]):
        with QMutexLocker(self._mutex):
            self._data = data

    def start_work(self):
        self._timer = QTimer()
        self._timer.timeout.connect(self._on_tick)
        self._timer.setInterval(self.interval_ms)
        self._try_connect()
        self._timer.start()

    def stop_work(self):
        if self._timer:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        self._disconnect()

    def _on_tick(self):
        if self._connected:
            self._send_and_receive()
        elif self._reconnect_backoff <= 0:
            self._try_connect()
            self._reconnect_backoff = 10
        else:
            self._reconnect_backoff -= 1

    def _get_data(self) -> Dict[str, Any]:
        with QMutexLocker(self._mutex):
            return dict(self._data)

    def _send_and_receive(self):
        data = self._get_data()
        if not data:
            return
        payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "sensors": data.get("sensors", {}),
            "hoppers": data.get("hoppers", {}),
            "conveyor_sensors": data.get("conveyor_sensors", {}),
            "cart_sensors": data.get("cart_sensors", {}),
            "feed_signals": data.get("feed_signals", {}),
            "route_states": data.get("route_states", {}),
            "clearing_strategies": data.get("clearing_strategies", {}),
            "early_moved_routes": data.get("early_moved_routes", {}),
        }
        try:
            json_str = json.dumps(payload, ensure_ascii=False)
            self._socket.sendall((json_str + "\n").encode("utf-8"))

            # 接收响应
            buf = b""
            self._socket.settimeout(2.0)
            while b"\n" not in buf:
                chunk = self._socket.recv(4096)
                if not chunk:
                    break
                buf += chunk
            self._socket.settimeout(None)

            if buf:
                response = json.loads(buf.decode("utf-8").strip())
                raw_results = response.get("diagnosis_results", [])
                results = []
                for r in raw_results:
                    from tcp_diagnosis.diagnosis_types import DiagnosisResult
                    results.append(DiagnosisResult(
                        sensor_id=r.get("sensor_id", ""),
                        fault_type=r.get("fault_type", ""),
                        confidence=r.get("confidence", 0.0),
                        description=r.get("description", ""),
                        category=r.get("category", ""),
                        related_sensors=r.get("related_sensors", []),
                    ))
                self.results_received.emit(results)
        except (BrokenPipeError, ConnectionResetError, OSError, json.JSONDecodeError) as e:
            self._connected = False
            self._disconnect()
            self.send_error.emit(str(e))
            self.connection_changed.emit(False)

    def _try_connect(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            sock.connect((self.host, self.port))
            sock.settimeout(None)
            self._socket = sock
            self._connected = True
            self._reconnect_backoff = 0
            self.connection_changed.emit(True)
        except (ConnectionRefusedError, socket.timeout, OSError):
            self._connected = False
            self._socket = None

    def _disconnect(self):
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        self._connected = False


class TcpDiagnosisClient(QObject):
    """TCP 诊断客户端（主线程 facade）"""

    results_received = pyqtSignal(list)
    connection_changed = pyqtSignal(bool)
    send_error = pyqtSignal(str)

    def __init__(self, host: str = None, port: int = None):
        super().__init__()
        self.host = host or DIAGNOSIS_HOST
        self.port = port or DIAGNOSIS_PORT
        self._worker: Optional[DiagnosisWorker] = None
        self._thread: Optional[QThread] = None
        self._connected = False
        self._active = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def update_data(self, data: Dict[str, Any]):
        if self._worker:
            self._worker.update_data(data)

    def start(self):
        if self._active:
            return
        self._active = True
        self._thread = QThread()
        self._worker = DiagnosisWorker(self.host, self.port, DIAGNOSIS_INTERVAL_MS)
        self._worker.moveToThread(self._thread)
        self._worker.results_received.connect(self._on_results)
        self._worker.connection_changed.connect(self._on_connection_changed)
        self._worker.send_error.connect(self._on_send_error)
        self._thread.started.connect(self._worker.start_work)
        self._thread.start()

    def stop(self):
        self._active = False
        self._connected = False
        if self._worker:
            self._worker.stop_work()
            self._worker.deleteLater()
            self._worker = None
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread.deleteLater()
            self._thread = None

    def _on_results(self, results):
        self.results_received.emit(results)

    def _on_connection_changed(self, connected: bool):
        self._connected = connected
        self.connection_changed.emit(connected)

    def _on_send_error(self, msg: str):
        self.send_error.emit(msg)
