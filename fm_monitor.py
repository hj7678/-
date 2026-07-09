"""
FM 监听器 —— 仿真真实上位机接收端

连接 FM 服务器的 :8896 端口，接收并打印所有 FM 下行消息。
用于验证 FM 发送给真实上位机的通讯协议是否符合预期。

用法:
    py fm_monitor.py
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
    print(f"FM 监听器启动 → {HOST}:{PORT}")
    print("等待 FM 连接...\n")

    while True:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((HOST, PORT))
            sock.settimeout(None)
            print(f"✓ 已连接 FM ({HOST}:{PORT})\n")
            print("=" * 60)

            buf = b""
            last_ts = time.time()
            msg_count = 0
            last_cmd_count = 0
            last_level_count = 0

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
                        continue

                    msg_count += 1
                    msg_type = msg.get('type', '?')

                    if msg_type == 'command':
                        last_cmd_count += 1
                    elif msg_type == 'level_report':
                        last_level_count += 1

                    # 每秒打印统计摘要
                    now = time.time()
                    if now - last_ts >= 1.0:
                        print(f"[摘要] 1s内: {msg_count}条消息 "
                              f"(command×{last_cmd_count}, level_report×{last_level_count})",
                              end='\r', flush=True)
                        # 每10秒打印一次完整消息
                        if msg_count >= 100:
                            print(f"\n[完整] {format_msg(msg)}")
                            print(json.dumps(msg, ensure_ascii=False, indent=2)[:500])
                            msg_count = 0
                        last_cmd_count = 0
                        last_level_count = 0
                        last_ts = now

                    # 实时打印每条消息摘要
                    summary = format_msg(msg)
                    if msg_type == 'command':
                        print(f"\n{summary}")
                        # 打印前3条指令
                        cmds = msg.get('commands', [])
                        for c in cmds[:3]:
                            print(f"  → {c}")
                        if len(cmds) > 3:
                            print(f"  ... 共{len(cmds)}条")
                        # 打印调度序列
                        if 'schedule' in msg:
                            sched = msg['schedule']
                            exec_bin = sched.get('executing_bin', {})
                            seqs = sched.get('sequences', {})
                            print(f"  调度: executing={exec_bin}")
                            for belt, seq in seqs.items():
                                if seq:
                                    print(f"    {belt}: {seq}")
                    elif msg_type == 'level_report':
                        # 每5秒打印一次料位
                        if last_level_count == 1:
                            print(f"\n{summary}")
                            levels = msg.get('levels', [])
                            for l in levels[:3]:
                                print(f"  {l['bin_id']}: {l['level_pct']}% ({l['capacity']}t)")
                            if len(levels) > 3:
                                print(f"  ... 共{len(levels)}个")
                    else:
                        print(f"\n{summary}")

        except (ConnectionRefusedError, OSError, socket.timeout) as e:
            if sock:
                sock.close()
            print(f"\n✗ FM 不可达 ({e})，{RECONNECT_DELAY}s 后重试...")
            time.sleep(RECONNECT_DELAY)
        except KeyboardInterrupt:
            print("\n\n已停止")
            if sock:
                sock.close()
            sys.exit(0)
        except Exception as e:
            print(f"\n✗ 错误: {e}")
            if sock:
                sock.close()
            time.sleep(RECONNECT_DELAY)


if __name__ == '__main__':
    main()