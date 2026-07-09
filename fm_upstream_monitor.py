"""
上游监听器 —— 仿真真实上位机发送端

连接 FM 服务器 :8896，接收并打印 FM 广播的上行回显消息。
用于验证仿真 HMI 发送给 FM 的传感器状态是否符合协议。

用法:
    py fm_upstream_monitor.py [host] [port]

    默认: host=127.0.0.1, port=8896
    示例: py fm_upstream_monitor.py 192.168.3.222 8896
"""

import json
import socket
import time
import sys

HOST = '127.0.0.1'
PORT = 8896
RECONNECT_DELAY = 3.0
PRINT_INTERVAL = 2.0  # 打印间隔（秒），避免 sensor_states 刷屏


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else PORT

    print(f"上游监听器启动 → {host}:{port}")
    print("等待 FM 连接...")

    while True:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, port))
            sock.settimeout(None)
            print(f"\n✓ 已连接 FM ({host}:{port})")
            print("=" * 60)

            buf = b""
            last_print = 0.0

            while True:
                try:
                    chunk = sock.recv(4096)
                except (ConnectionResetError, ConnectionAbortedError, OSError):
                    break
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        msg = json.loads(line.decode('utf-8').strip())
                    except json.JSONDecodeError:
                        continue

                    msg_type = msg.get('type', '')
                    if not msg_type.startswith('echo_'):
                        continue  # 忽略下行消息，只看上行

                    # 限频打印 sensor_states
                    now = time.time()
                    if msg_type == 'echo_sensor_states':
                        if now - last_print < PRINT_INTERVAL:
                            continue
                        last_print = now
                        data = msg.get('data', {})
                        print(f"\n{msg_type}")
                        print(json.dumps(data, ensure_ascii=False, indent=2))
                    else:
                        print(f"\n{msg_type}")
                        print(json.dumps(msg.get('data', {}), ensure_ascii=False, indent=2))

        except (ConnectionRefusedError, OSError, socket.timeout) as e:
            if sock:
                sock.close()
            print(f"\r✗ FM 不可达，{RECONNECT_DELAY}s后重试...", end='', flush=True)
            time.sleep(RECONNECT_DELAY)
        except KeyboardInterrupt:
            print("\n\n已停止")
            if sock:
                sock.close()
            sys.exit(0)
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass


if __name__ == '__main__':
    main()