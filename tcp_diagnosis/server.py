"""
TCP 诊断服务端 —— 接收上位机传感器数据，运行诊断，回传结果
"""
import socket
import threading
import json
import logging
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tcp_diagnosis.engine import DiagnosisEngine
from tcp_diagnosis.adapter import TcpDataAdapter
from tcp_diagnosis.config import TCP_HOST, TCP_PORT

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


_CATEGORY_CN = {
    "proximity": "接近开关",
    "hopper_switch": "中转斗开关",
    "hopper_weight": "中转斗称重",
    "cart": "小车传感器",
    "conveyor": "皮带转速",
    "cross_sensor": "跨传感器",
    "feeding_anomaly": "上料异常",
    "cart_movement": "小车移动",
}


def _format_diagnosis_results(results) -> str:
    """将诊断结果格式化为文本，与 UI 状态面板输出一致"""
    if not results:
        return "无传感器故障"

    high_conf = [r for r in results if r.confidence >= 0.7]
    low_conf = [r for r in results if 0.5 <= r.confidence < 0.7]
    all_shown = high_conf + low_conf

    if not all_shown:
        return "无传感器故障"

    lines = [f"检测到 {len(all_shown)} 个故障"]
    for r in high_conf:
        cat = _CATEGORY_CN.get(r.category, r.category)
        conf_pct = int(r.confidence * 100)
        lines.append(f"[{cat}] {r.sensor_id}: {r.description} (置信度{conf_pct}%)")
    for r in low_conf:
        cat = _CATEGORY_CN.get(r.category, r.category)
        conf_pct = int(r.confidence * 100)
        lines.append(f"[{cat}·低] {r.sensor_id}: {r.description} (置信度{conf_pct}%)")

    return "\n".join(lines)


class TcpDiagnosisServer:

    def __init__(self, host: str = TCP_HOST, port: int = TCP_PORT):
        self.host = host
        self.port = port
        self.engine = DiagnosisEngine()
        self.adapter = TcpDataAdapter()
        self._server_socket = None
        self._running = False

    def start(self):
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(5)
        self._running = True
        logger.info(f"TCP 诊断服务已启动，监听 {self.host}:{self.port}")

        while self._running:
            try:
                self._server_socket.settimeout(1.0)
                try:
                    client_socket, client_address = self._server_socket.accept()
                    logger.info(f"收到连接: {client_address}")
                    thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, client_address),
                        daemon=True,
                    )
                    thread.start()
                except socket.timeout:
                    continue
            except Exception as e:
                if self._running:
                    logger.error(f"接受连接时出错: {e}")

    def stop(self):
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
        logger.info("TCP 诊断服务已停止")

    def _handle_client(self, client_socket: socket.socket, client_address: tuple):
        try:
            client_socket.settimeout(60.0)
            buf = b""

            while self._running:
                chunk = client_socket.recv(4096)
                if not chunk:
                    logger.info(f"客户端 {client_address} 断开连接")
                    return
                buf += chunk

                # 按换行分割帧，每帧一个完整 JSON
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        json_str = line.decode("utf-8")
                        response_str = self._process_frame(json_str)
                        client_socket.sendall((response_str + "\n").encode("utf-8"))
                    except Exception as e:
                        logger.error(f"处理帧出错: {e}")
                        error_resp = json.dumps({
                            "error": str(e),
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
                            "diagnosis_results": [],
                        }, ensure_ascii=False)
                        client_socket.sendall((error_resp + "\n").encode("utf-8"))

        except socket.timeout:
            logger.warning(f"客户端 {client_address} 读超时")
        except ConnectionResetError:
            logger.info(f"客户端 {client_address} 重置连接")
        except Exception as e:
            logger.error(f"处理客户端 {client_address} 时出错: {e}")
        finally:
            try:
                client_socket.close()
            except Exception:
                pass

    def _process_frame(self, json_str: str) -> str:
        data = json.loads(json_str)
        snapshot = self.adapter.build_snapshot(data)
        results = self.engine.diagnose(snapshot)

        # 诊断结果日志
        if results:
            logger.info(f"诊断: {len(results)}个故障 — {[(r.sensor_id, r.fault_type) for r in results[:5]]}")
        else:
            active = [(rid, r.state.value) for rid, r in snapshot.routes.items() if r.state.value != 'idle']
            if active:
                logger.info(f"活跃路线状态: {active}")
        ts = data.get("timestamp", "") or datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        diagnosis_text = _format_diagnosis_results(results)
        response = {
            "timestamp": ts,
            "diagnosis_text": diagnosis_text,
            "diagnosis_results": [
                {
                    "sensor_id": r.sensor_id,
                    "fault_type": r.fault_type,
                    "confidence": r.confidence,
                    "description": r.description,
                    "category": r.category,
                    "related_sensors": r.related_sensors,
                }
                for r in results
            ],
        }
        return json.dumps(response, ensure_ascii=False)
