"""上料点原料状态服务端入口
仿真实模式下，状态由 UI 控制面板设置，存储于内存。
FM 通过桥接的 feed_material_states 推送获取状态。
本模块作为独立终端运行，方便监控状态变化。
"""
import json
import socket
import threading
import sys
import os

from feed_material_service import FeedMaterialService

HOST = '127.0.0.1'
PORT = 9010


def main():
    svc = FeedMaterialService.instance()
    print(f"[上料点原料服务] 已启动, 端口 {PORT}")
    print(f"  当前状态: {json.dumps(svc.get_all_states(), indent=2)}")
    print("  等待 FM 查询或 UI 更新...")

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
            print(f"  [更新] {key} → {'有料' if value else '无料'}")
            resp = {'type': 'ok'}
        elif msg_type == 'has_material':
            feed_point = msg.get('feed_point', '')
            bin_prefix = msg.get('bin_prefix', '')
            result = svc.has_material(feed_point, bin_prefix)
            resp = {'type': 'has_material_rsp', 'result': result}
        else:
            resp = {'type': 'error', 'message': f'unknown type: {msg_type}'}

        conn.sendall(json.dumps(resp).encode('utf-8'))
    except Exception as e:
        print(f"  [错误] {e}")
    finally:
        conn.close()


if __name__ == '__main__':
    main()