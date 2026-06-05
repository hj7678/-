"""
TCP 调度服务端 —— 接收料仓数据，运行调度优化，回传上料顺序
"""
import socket
import threading
import json
import logging
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scheduling.engine import SchedulingEngine
from scheduling.sched_types import BinState, ScheduleResult, StepDetail
from scheduling.config import SCHEDULER_PORTS, TCP_HOST
from scheduling.bin_config import BELT_COL_COUNT

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _step_to_dict(s: StepDetail) -> dict:
    return {
        "seq": s.seq,
        "bin_id": s.bin_id,
        "line_name": s.line_name,
        "mode": s.mode,
        "remain_stock": s.remain_stock,
        "survival_time": s.survival_time,
        "stock_status": s.stock_status,
        "move_time": s.move_time,
        "wait_time": s.wait_time,
        "fill_time": s.fill_time,
        "stop_time": s.stop_time,
        "total_time": s.total_time,
    }


def _result_to_json(result: ScheduleResult, ts: str) -> dict:
    return {
        "timestamp": ts,
        "belt_id": result.belt_id,
        "sequence": result.sequence,
        "is_feasible": result.is_feasible,
        "summary": {
            "total_move": result.total_move,
            "total_wait": result.total_wait,
            "total_fill": result.total_fill,
            "total_stop": result.total_stop,
        },
        "steps": [_step_to_dict(s) for s in result.steps],
    }


class SchedulingServer:

    def __init__(self, belt_id: str, host: str = TCP_HOST, port: int = None):
        self.belt_id = belt_id
        self.host = host
        self.port = port if port is not None else SCHEDULER_PORTS.get(belt_id, 8891)
        self.engine = SchedulingEngine(col_count=BELT_COL_COUNT[belt_id], belt_id=belt_id)
        self._server_socket = None
        self._running = False

    def start(self):
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(5)
        self._running = True
        logger.info(f"[{self.belt_id}] 调度服务已启动，监听 {self.host}:{self.port}")
        print(f"[{self.belt_id}] 进入 accept 循环，等待连接...", flush=True)

        loop_count = 0
        while self._running:
            loop_count += 1
            if loop_count % 300 == 0:
                print(f"[{self.belt_id}] 等待中... ({loop_count // 60}分钟)", flush=True)
            try:
                self._server_socket.settimeout(1.0)
                try:
                    client_socket, client_address = self._server_socket.accept()
                    msg = f"[{self.belt_id}] 收到连接: {client_address}"
                    logger.info(msg)
                    print(msg, flush=True)
                    thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, client_address),
                        daemon=True,
                    )
                    thread.start()
                except socket.timeout:
                    pass  # 每秒超时，静默继续
            except Exception as e:
                if self._running:
                    logger.error(f"[{self.belt_id}] 接受连接时出错: {e}")

    def stop(self):
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
        logger.info(f"[{self.belt_id}] 调度服务已停止")

    def _handle_client(self, client_socket: socket.socket, client_address: tuple):
        try:
            client_socket.settimeout(None)  # 事件驱动模式，不设超时
            buf = b""

            while self._running:
                chunk = client_socket.recv(4096)
                if not chunk:
                    logger.info(f"[{self.belt_id}] 客户端 {client_address} 断开连接")
                    return
                buf += chunk

                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        json_str = line.decode("utf-8")
                        response_str = self._process_request(json_str)
                        client_socket.sendall((response_str + "\n").encode("utf-8"))
                    except Exception as e:
                        logger.error(f"[{self.belt_id}] 处理请求出错: {e}")
                        error_resp = json.dumps({
                            "error": str(e),
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
                            "belt_id": self.belt_id,
                        }, ensure_ascii=False)
                        client_socket.sendall((error_resp + "\n").encode("utf-8"))

        except socket.timeout:
            logger.warning(f"[{self.belt_id}] 客户端 {client_address} 读超时")
        except ConnectionResetError:
            logger.info(f"[{self.belt_id}] 客户端 {client_address} 重置连接")
        except Exception as e:
            logger.error(f"[{self.belt_id}] 处理客户端 {client_address} 时出错: {e}")
        finally:
            try:
                client_socket.close()
            except Exception:
                pass

    def _process_request(self, json_str: str) -> str:
        data = json.loads(json_str)
        ts = data.get("timestamp", "") or datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        boost = data.get("boost_mode", False)

        bins = []
        for bd in data.get("bins", []):
            bins.append(BinState(
                bin_id=bd["bin_id"],
                stock=float(bd.get("stock", 0)),
                consumption_rate=float(bd.get("consumption_rate", 0.01)),
                maintenance=bool(bd.get("maintenance", False)),
                has_future_order=bool(bd.get("has_future_order", False)),
            ))

        cart_position = data.get("cart_position", None)
        left_divert = data.get("left_divert", False)
        right_divert = data.get("right_divert", False)

        # 所有皮带：cart_position 转换为调度引擎 wh_id（底行→小号）
        if cart_position is not None and self.belt_id != 'D6':
            from scheduling.bin_config import d8_bin_id_to_wh, bin_id_to_wh, BELT_TO_COL_PREFIX
            if self.belt_id == 'D8':
                col = 'P3' if (right_divert and not left_divert) else 'P2'
                cart_position = d8_bin_id_to_wh(f'{col}-{cart_position}')
            else:
                prefix = BELT_TO_COL_PREFIX.get(self.belt_id, 'P1')
                cart_position = bin_id_to_wh(f'{prefix}-{cart_position}')

        stock_summary = ", ".join(f"{b.bin_id}={b.stock:.1f}t" for b in bins[:3])
        if len(bins) > 3:
            stock_summary += f"... (共{len(bins)}仓)"
        logger.info(f"[{self.belt_id}] 收到调度请求: {stock_summary} | cart_pos={cart_position} | boost={boost}")
        print(f"[{self.belt_id}] 收到调度请求: {stock_summary} | cart_pos={cart_position}", flush=True)

        result = self.engine.solve(bins, boost, cart_position=cart_position)

        if result.sequence:
            logger.info(f"[{self.belt_id}] 调度结果: sequence={result.sequence} | feasible={result.is_feasible}")
            print(f"[{self.belt_id}] 调度结果: sequence={result.sequence}", flush=True)
        else:
            logger.info(f"[{self.belt_id}] 调度结果: 无需补料 (无仓低于触发阈值)")
            print(f"[{self.belt_id}] 调度结果: 无需补料", flush=True)

        response = _result_to_json(result, ts)
        return json.dumps(response, ensure_ascii=False)
