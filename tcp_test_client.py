"""
TCP传感器数据发送客户端（测试用）
用于测试 TCP 连接和数据接收
"""
import socket
import json
import time
import random


def test_connection():
    """测试TCP连接"""
    # 注意：请修改为实际要连接的服务器IP
    host = '172.16.16.108'
    port = 8888

    # 测试数据
    test_data = {
        "timestamp": "2026-05-07 10:20:00.000000",
        "sensors": {
            "S-E6": {"type": "proximity", "unit": "bool", "value": True},
            "S-E7": {"type": "proximity", "unit": "bool", "value": False}
        },
        "conveyor_sensors": {
            "S-CV-E6": {"type": "speed", "unit": "sint", "value": 500}
        }
    }

    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(5.0)
        client.connect((host, port))
        print(f"已连接到 {host}:{port}")

        data_str = json.dumps(test_data, ensure_ascii=False)
        client.sendall(data_str.encode('utf-8'))
        print(f"已发送数据: {data_str[:100]}...")

        client.close()
        print("连接已关闭")
        return True

    except ConnectionRefusedError:
        print(f"连接被拒绝，请确认服务器已启动")
        return False

    except ConnectionRefusedError:
        print(f"连接被拒绝，请确认服务器已启动")
        return False
    except Exception as e:
        print(f"错误: {e}")
        return False


def continuous_test(interval: float = 1.0):
    """持续发送测试数据"""
    # 注意：请修改为实际要连接的服务器IP
    host = '172.16.16.108'
    port = 8888

    print(f"开始持续发送测试数据，间隔 {interval} 秒...")
    print("按 Ctrl+C 停止")

    try:
        while True:
            test_data = {
                "timestamp": time.strftime('%Y-%m-%d %H:%M:%S') + f".{int(time.time() % 1000):03d}",
                "sensors": {
                    "S-E6": {"type": "proximity", "unit": "bool", "value": random.choice([True, False])},
                    "S-E7": {"type": "proximity", "unit": "bool", "value": random.choice([True, False])}
                },
                "conveyor_sensors": {
                    "S-CV-E6": {"type": "speed", "unit": "sint", "value": random.randint(0, 500)}
                }
            }

            try:
                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client.settimeout(5.0)
                client.connect((host, port))

                data_str = json.dumps(test_data, ensure_ascii=False)
                client.sendall(data_str.encode('utf-8'))
                print(f"[{test_data['timestamp']}] 发送成功")

                client.close()
            except Exception as e:
                print(f"发送失败: {e}")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n已停止发送")


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--continuous':
        interval = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
        continuous_test(interval)
    else:
        test_connection()
