"""
TCP传感器数据接收服务
监听 172.16.16.108:8888，接收传感器数据并更新 sensor_data.json
"""
import socket
import threading
import json
import logging
from datetime import datetime
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 配置
HOST = '172.16.16.108'
PORT = 8888
SENSOR_DATA_PATH = Path(__file__).parent / 'data' / 'sensor_data.json'
RESPONSE_SUCCESS = "RECEIVED"
RESPONSE_ERROR = "ERROR"


class SensorDataReceiver:
    def __init__(self, host: str, port: int, data_path: Path):
        self.host = host
        self.port = port
        self.data_path = data_path
        self.server_socket = None
        self.running = False
        self.lock = threading.Lock()

    def start(self):
        """启动TCP服务器"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True
        logger.info(f"TCP传感器数据接收服务已启动，监听 {self.host}:{self.port}")

        while self.running:
            try:
                self.server_socket.settimeout(1.0)
                try:
                    client_socket, client_address = self.server_socket.accept()
                    logger.info(f"收到连接: {client_address}")
                    thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, client_address)
                    )
                    thread.daemon = True
                    thread.start()
                except socket.timeout:
                    continue
            except Exception as e:
                if self.running:
                    logger.error(f"接受连接时出错: {e}")

    def stop(self):
        """停止TCP服务器"""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        logger.info("TCP传感器数据接收服务已停止")

    def _handle_client(self, client_socket: socket.socket, client_address: tuple):
        """处理客户端连接"""
        try:
            logger.info(f"收到来自 {client_address} 的连接请求")
            client_socket.settimeout(60.0)

            while self.running:
                data = b''
                while True:
                    chunk = client_socket.recv(4096)
                    if not chunk:
                        logger.info(f"客户端 {client_address} 断开连接")
                        return
                    data += chunk
                    try:
                        message = data.decode('utf-8').strip()
                        if not message:
                            continue
                        json.loads(message)
                        logger.info(f"收到数据: {message[:200]}...")
                        success, response = self._process_data(message)
                        response_msg = (response + "\n").encode('utf-8')
                        client_socket.sendall(response_msg)
                        logger.info(f"已发送响应: {response}")
                        break
                    except json.JSONDecodeError:
                        continue

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

    def _process_data(self, message: str) -> tuple:
        """
        处理接收到的数据并更新 sensor_data.json
        返回: (成功标志, 响应消息)
        """
        try:
            data = json.loads(message)
            if not isinstance(data, dict):
                return False, f"{RESPONSE_ERROR}: Invalid data format"

            with self.lock:
                if self.data_path.exists():
                    with open(self.data_path, 'r', encoding='utf-8') as f:
                        current_data = json.load(f)
                else:
                    current_data = {
                        "timestamp": "",
                        "sensors": {},
                        "hoppers": {},
                        "conveyor_sensors": {},
                        "cart_sensors": {}
                    }

                if 'timestamp' in data:
                    current_data['timestamp'] = data['timestamp']
                else:
                    current_data['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')

                self._update_sensors(current_data, data, 'sensors')
                self._update_sensors(current_data, data, 'hoppers')
                self._update_sensors(current_data, data, 'conveyor_sensors')
                self._update_sensors(current_data, data, 'cart_sensors')

                self.data_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.data_path, 'w', encoding='utf-8') as f:
                    json.dump(current_data, f, indent=4, ensure_ascii=False)

                logger.info(f"已更新 sensor_data.json，时间戳: {current_data['timestamp']}")
                return True, RESPONSE_SUCCESS

        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {e}")
            return False, f"{RESPONSE_ERROR}: Invalid JSON - {str(e)}"
        except Exception as e:
            logger.error(f"处理数据时出错: {e}")
            return False, f"{RESPONSE_ERROR}: {str(e)}"

    def _update_sensors(self, current_data: dict, new_data: dict, key: str):
        """更新指定类型的传感器数据"""
        if key in new_data and isinstance(new_data[key], dict):
            if key not in current_data:
                current_data[key] = {}
            current_data[key].update(new_data[key])


def main():
    """主函数"""
    receiver = SensorDataReceiver(HOST, PORT, SENSOR_DATA_PATH)
    try:
        receiver.start()
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止服务...")
        receiver.stop()


if __name__ == '__main__':
    main()
