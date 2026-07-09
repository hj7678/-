"""
上游监听器 —— 代替 FM 接收真实上位机发送的数据

监听端口，接收真实上位机连接并打印所有上行数据。
用于验证真实上位机发送的传感器状态是否符合协议。

用法:
    py fm_upstream_monitor.py [port]

    默认: port=8888（真实上位机 IP: 172.16.16.106）
"""

import json
import socket
import sys
import time

LISTEN_PORT = 8888
PRINT_INTERVAL = 2.0  # sensor_states 打印间隔（秒）


def handle_client(sock: socket.socket, addr: tuple):
    buf = b""
    last_print = 0.0
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    msg = json.loads(line.decode('utf-8').strip())
                except json.JSONDecodeError:
                    print(f"非JSON: {line[:200]}")
                    continue

                msg_type = msg.get('type', '?')
                now = time.time()
                if msg_type == 'sensor_states':
                    if now - last_print < PRINT_INTERVAL:
                        continue
                    last_print = now
                    data = msg.get('data', {})
                    print(f"\n[{msg_type}] from {addr}")
                    print(json.dumps(data, ensure_ascii=False, indent=2))
                else:
                    print(f"\n[{msg_type}] from {addr}")
                    print(json.dumps(msg, ensure_ascii=False, indent=2))

                sys.stdout.flush()
    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        try:
            sock.close()
        except Exception:
            pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else LISTEN_PORT

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', port))
    server.listen(5)
    print(f"上游监听器启动 → 监听 0.0.0.0:{port}")
    print(f"等待真实上位机连接...")
    print(f"sensor_states 打印间隔: {PRINT_INTERVAL}s")
    print()

    try:
        while True:
            client, addr = server.accept()
            print(f"\n✓ 真实上位机已连接: {addr}")
            print("=" * 60)
            handle_client(client, addr)
            print(f"\n✗ 真实上位机断开: {addr}")
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.close()


if __name__ == '__main__':
    main()