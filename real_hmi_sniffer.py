"""
真实上位机数据监听器 —— TCP 服务器模式

启动后监听指定端口，真实上位机连接到此端口发送数据，脚本打印所有收到的消息。

用法:
    py real_hmi_sniffer.py [port]

    默认: host=0.0.0.0, port=8898
    真实上位机改为连接 <本机IP>:8898 即可
"""
import json
import socket
import sys
import time
import threading

HOST = '0.0.0.0'
PORT = 8898


def format_msg(data: dict) -> str:
    """格式化输出消息摘要"""
    msg_type = data.get('type', '?')
    if msg_type == 'sensor_states':
        inner = data.get('data', {})
        carts = inner.get('cart_positions', {})
        moving = inner.get('cart_moving', {})
        laser = inner.get('laser_sensor_states', {})
        prox = inner.get('proximity', {})
        belts = inner.get('belt_states', {})
        parts = []
        if carts:
            parts.append(f"小车: {', '.join(f'{k}={v}' for k,v in carts.items())}")
        if moving:
            moving_ids = [k for k, v in moving.items() if v]
            if moving_ids:
                parts.append(f"移动中: {moving_ids}")
        active_laser = [k for k, v in laser.items() if v]
        if active_laser:
            parts.append(f"激光: {active_laser}")
        active_prox = [k for k, v in prox.items() if v]
        if active_prox:
            parts.append(f"接近开关: {active_prox[:5]}{'...' if len(active_prox)>5 else ''}")
        running_belts = [k for k, v in belts.items() if v]
        if running_belts:
            parts.append(f"运行皮带: {len(running_belts)}条")
        return f"[sensor_states] {' | '.join(parts)}"
    elif msg_type == 'level_report':
        return f"[level_report] {len(data.get('levels', []))}仓"
    else:
        return f"[{msg_type}]"


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    print(f"真实上位机监听器 → 监听 {HOST}:{port}")
    print(f"请将真实上位机连接到 {HOST}:{port}\n")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, port))
    server.listen(1)
    print(f"等待真实上位机连接...\n")

    msg_count = 0
    last_ts = time.time()
    last_sensor_ts = 0.0

    while True:
        try:
            server.settimeout(1.0)
            try:
                client, addr = server.accept()
                print(f"✓ 真实上位机已连接: {addr}\n")
                print("=" * 60)

                buf = b""
                client.settimeout(None)
                while True:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        try:
                            msg = json.loads(line.decode('utf-8').strip())
                        except json.JSONDecodeError:
                            print(f"[raw] {line[:200]}")
                            continue

                        msg_count += 1
                        msg_type = msg.get('type', '?')

                        # sensor_states: 每2s打印一次摘要
                        if msg_type == 'sensor_states':
                            now = time.time()
                            if now - last_sensor_ts >= 2.0:
                                last_sensor_ts = now
                                print(format_msg(msg))
                                sys.stdout.flush()
                        else:
                            print(format_msg(msg))
                            sys.stdout.flush()

                        # 每秒统计
                        now = time.time()
                        if now - last_ts >= 5.0:
                            print(f"--- 5s内收到 {msg_count} 条消息 ---")
                            msg_count = 0
                            last_ts = now

                print(f"\n✗ 真实上位机断开: {addr}")
                print("等待重新连接...\n")
                client.close()
            except socket.timeout:
                pass
        except KeyboardInterrupt:
            print("\n已停止")
            server.close()
            sys.exit(0)
        except Exception as e:
            print(f"\n✗ 错误: {e}")
            time.sleep(3)


if __name__ == "__main__":
    main()