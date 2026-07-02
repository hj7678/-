"""上料点原料状态 — 独立监控终端
连接主进程的 FeedMaterialService TCP 服务端，实时显示状态。
"""
import json
import socket
import time
import sys

HOST = '127.0.0.1'
PORT = 9010


def main():
    print(f"[上料点原料服务] 监控终端已启动，连接 {HOST}:{PORT}")
    print("  等待主进程服务端就绪...")

    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((HOST, PORT))
            s.sendall(json.dumps({'type': 'get_states'}).encode('utf-8'))
            data = s.recv(4096).decode('utf-8')
            s.close()
            resp = json.loads(data)
            states = resp.get('states', {})
            items = [f"{k}={v}" for k, v in sorted(states.items())]
            print(f"[{time.strftime('%H:%M:%S')}] {', '.join(items)}", flush=True)
        except (ConnectionRefusedError, socket.timeout, OSError):
            print(".", end='', flush=True)
        except Exception as e:
            print(f"  [错误] {e}", flush=True)
        time.sleep(10)


if __name__ == '__main__':
    main()