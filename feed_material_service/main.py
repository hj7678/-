"""上料点原料状态服务端 — 独立 TCP 服务
存储上料点各物料的有料/无料状态。
HMI 控制面板和 FM 均通过 TCP 通信，完全解耦。
"""
import json
import socket
import threading
import time

from feed_material_service import FeedMaterialService

HOST = '127.0.0.1'
PORT = 9010


def main():
    svc = FeedMaterialService.instance()
    print(f"[上料点原料服务] 已启动, 端口 {PORT}")
    print(f"  当前状态: {json.dumps(svc.get_all_states(), indent=2)}")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)

    try:
        while True:
            conn, addr = server.accept()
            t = threading.Thread(target=_handle_client, args=(conn, addr, svc), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("\n[上料点原料服务] 已停止")
    finally:
        server.close()


def _handle_client(conn, addr, svc):
    try:
        data = conn.recv(4096).decode('utf-8')
        msg = json.loads(data) if data.strip() else {}
        msg_type = msg.get('type', '')

        if msg_type == 'get_states':
            resp = {'type': 'feed_material_rsp', 'states': svc.get_all_states()}
        elif msg_type == 'set_state':
            key = msg.get('key', '')
            value = msg.get('value', True)
            svc.set_state(key, value)
            resp = {'type': 'ok'}
        elif msg_type == 'has_material':
            feed_point = msg.get('feed_point', '')
            bin_prefix = msg.get('bin_prefix', '')
            result = svc.has_material(feed_point, bin_prefix)
            resp = {'type': 'has_material_rsp', 'result': result}
        else:
            resp = {'type': 'error', 'message': f'unknown: {msg_type}'}

        conn.sendall(json.dumps(resp).encode('utf-8'))
    except Exception as e:
        print(f"  [错误] {e}", flush=True)
    finally:
        conn.close()


if __name__ == '__main__':
    main()