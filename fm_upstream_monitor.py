"""
FM 命令监听器 —— 仅打印 FM 发送给上位机的控制命令（变化时打印一次）

用法:
    py fm_upstream_monitor.py [host] [port]

    默认: host=127.0.0.1, port=8896
"""

import json
import socket
import sys
import time

HOST = '127.0.0.1'
PORT = 8896
RECONNECT_DELAY = 3.0


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else PORT

    print(f"FM 命令监听器启动 → {host}:{port}")
    print("等待 FM 连接...")

    last_level_time = 0.0
    last_levels = None
    last_sched = None

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

                    if msg.get('type') != 'command':
                        # level_report 独立定时打印
                        if msg.get('type') == 'level_report':
                            levels = msg.get('levels', [])
                            now = time.time()
                            if levels != last_levels and now - last_level_time >= 10:
                                last_levels = list(levels)
                                last_level_time = now
                                print(f"\n[level_report] {len(levels)}个料仓:")
                                for l in levels[:5]:
                                    print(f"  {l['bin_id']}: {l['level_pct']}% ({l['capacity']}t)")
                                if len(levels) > 5:
                                    print(f"  ... 共{len(levels)}个")
                                sys.stdout.flush()
                        continue

                    cmds = msg.get('commands', [])
                    if not cmds:
                        continue

                    seq = msg.get('seq', '?')
                    print(f"\n[seq={seq}] {len(cmds)}条指令:")
                    for c in cmds:
                        print(f"  {c}")
                    if 'schedule' in msg:
                        sched = msg['schedule']
                        if sched != last_sched:
                            last_sched = sched
                            print(f"\n[schedule]")
                            print(f"  执行中: {sched.get('executing_bin', {})}")
                            for belt, seq in sched.get('sequences', {}).items():
                                if seq:
                                    print(f"    {belt}: {seq}")
                            sys.stdout.flush()
                    if 'diagnosis' in msg:
                        print(f"  诊断: {msg['diagnosis']}")
                    sys.stdout.flush()

        except (ConnectionRefusedError, OSError, socket.timeout):
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