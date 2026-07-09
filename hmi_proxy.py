"""
HMI 代理 —— 截获真实上位机与 FM 之间的通讯

在真实上位机和 FM 之间插入一个代理，监听端口，打印所有双向数据。
用于验证真实上位机发送的传感器状态是否符合协议。

用法:
    py hmi_proxy.py [listen_port] [fm_port]

    默认: listen_port=8897, fm_port=8896

    真实上位机连接 → 127.0.0.1:8897
    代理转发 → 127.0.0.1:8896 (FM)
"""

import json
import socket
import threading
import sys
import time

LISTEN_PORT = 8897
FM_HOST = '127.0.0.1'
FM_PORT = 8896

UPSTREAM_INTERVAL = 2.0  # 上行打印间隔（秒）


def forward(src: socket.socket, dst: socket.socket, label: str, direction: str):
    """转发数据并打印"""
    last_print = 0.0
    try:
        while True:
            chunk = src.recv(4096)
            if not chunk:
                break
            dst.sendall(chunk)

            now = time.time()
            for line in chunk.decode('utf-8', errors='replace').split('\n'):
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    print(f"[{label}] {direction} 非JSON: {line[:200]}")
                    continue

                msg_type = msg.get('type', '?')
                if direction == '上行' and msg_type == 'sensor_states':
                    if now - last_print < UPSTREAM_INTERVAL:
                        continue
                    last_print = now
                print(f"\n[{label}] {direction} {msg_type}")
                print(json.dumps(msg, ensure_ascii=False, indent=2))
                sys.stdout.flush()
    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        try:
            src.close()
        except Exception:
            pass
        try:
            dst.close()
        except Exception:
            pass


def handle_client(client_sock: socket.socket, addr: tuple):
    """处理真实上位机连接"""
    print(f"\n[{addr}] 真实上位机已连接")
    try:
        fm_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        fm_sock.connect((FM_HOST, FM_PORT))
        print(f"[{addr}] 已连接 FM {FM_HOST}:{FM_PORT}")
        print("=" * 60)

        t1 = threading.Thread(target=forward, args=(client_sock, fm_sock, addr, '上行'), daemon=True)
        t2 = threading.Thread(target=forward, args=(fm_sock, client_sock, addr, '下行'), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    except ConnectionRefusedError:
        print(f"[{addr}] FM 不可达 {FM_HOST}:{FM_PORT}")
    except Exception as e:
        print(f"[{addr}] 错误: {e}")
    finally:
        print(f"\n[{addr}] 断开")
        try:
            client_sock.close()
        except Exception:
            pass


def main():
    listen_port = int(sys.argv[1]) if len(sys.argv) > 1 else LISTEN_PORT
    fm_port = int(sys.argv[2]) if len(sys.argv) > 2 else FM_PORT

    print(f"HMI 代理启动")
    print(f"  监听: 0.0.0.0:{listen_port}  ← 真实上位机连接此端口")
    print(f"  转发: {FM_HOST}:{fm_port}  → FM")
    print(f"  上行打印间隔: {UPSTREAM_INTERVAL}s")
    print()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', listen_port))
    server.listen(5)
    print(f"代理已就绪，等待真实上位机连接...")

    try:
        while True:
            client, addr = server.accept()
            threading.Thread(target=handle_client, args=(client, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.close()


if __name__ == '__main__':
    main()