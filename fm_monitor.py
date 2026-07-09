"""
FM 监听器 —— 仿真真实上位机接收端

连接 FM 服务器的 :8896 端口，接收并打印所有 FM 下行消息。
用于验证 FM 发送给真实上位机的通讯协议是否符合预期。

用法:
    py fm_monitor.py [host] [port]

    默认: host=127.0.0.1, port=8896
    示例: py fm_monitor.py 192.168.3.222 8896
"""

import json
import socket
import time
import sys

HOST = '127.0.0.1'
PORT = 8896
RECONNECT_DELAY = 3.0


def format_msg(msg: dict) -> str:
    """格式化输出消息摘要"""
    msg_type = msg.get('type', '?')
    if msg_type == 'command':
        seq = msg.get('seq', '?')
        cmds = msg.get('commands', [])
        cmd_summary = [f"{c['device']}:{c['id']}→{c['action']}" for c in cmds]
        has_schedule = 'schedule' in msg
        has_diag = 'diagnosis' in msg
        has_route = 'route_states' in msg
        extras = []
        if has_schedule: extras.append('schedule')
        if has_diag: extras.append('diagnosis')
        if has_route: extras.append('route_states')
        extra_str = f" +{','.join(extras)}" if extras else ''
        return f"[command] seq={seq} | {len(cmds)}条指令{extra_str}"
    elif msg_type == 'level_report':
        levels = msg.get('levels', [])
        return f"[level_report] {len(levels)}个料仓料位"
    elif msg_type == 'ack':
        return f"[ack] ack_id={msg.get('ack_id')} action={msg.get('action')}"
    else:
        return f"[{msg_type}]"


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else PORT

    print(f"FM 监听器启动 → {host}:{port}")
    print("等待 FM 连接...")

    while True:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, port))
            sock.settimeout(None)
            print(f"\n✓ 已连接 FM ({HOST}:{PORT})")
            print("=" * 60)

            buf = b""
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
                    print(json.dumps(msg, ensure_ascii=False))
                    sys.stdout.flush()

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