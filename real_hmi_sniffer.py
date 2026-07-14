"""
真实上位机数据监听器 —— TCP 服务器模式，打印完整原始数据

用法:
    py real_hmi_sniffer.py [port]

    默认: host=0.0.0.0, port=8898
    真实上位机改为连接 <本机IP>:8898 即可
"""
import json
import socket
import sys
import time

HOST = '0.0.0.0'
PORT = 8898


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    print(f"真实上位机监听器 → 监听 {HOST}:{port}")
    print(f"请将真实上位机连接到 {HOST}:{port}\n")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, port))
    server.listen(1)
    print("等待真实上位机连接...\n")

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
                        text = line.decode('utf-8').strip()
                        if not text:
                            continue
                        try:
                            msg = json.loads(text)
                            print(json.dumps(msg, ensure_ascii=False, indent=2))
                        except json.JSONDecodeError:
                            print(f"[raw] {text[:500]}")
                        print("---")
                        sys.stdout.flush()

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