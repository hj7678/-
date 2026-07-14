"""
FM 数据源切换脚本

用法:
    py switch_source.py real   → 切换到真实上位机数据 (:8897)
    py switch_source.py sim    → 切换到仿真 HMI 数据 (:8896)
"""
import json
import socket
import sys

HOST = '127.0.0.1'
PORT = 8896  # 统一通过仿真端口发送切换命令

SOURCES = {
    'real': '__switch_real__',
    'sim': '__switch_sim__',
}

def main():
    if len(sys.argv) < 2 or sys.argv[1] not in SOURCES:
        print("用法: py switch_source.py [real|sim]")
        sys.exit(1)

    source = sys.argv[1]
    route_id = SOURCES[source]
    label = {'real': '真实上位机', 'sim': '仿真 HMI'}[source]

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect((HOST, PORT))
        payload = json.dumps({
            "type": "manual_start",
            "bin_id": "",
            "route_id": route_id,
        }, ensure_ascii=False)
        s.sendall((payload + "\n").encode("utf-8"))
        s.close()
        print(f"✓ 已切换为 {label} 数据源")
    except Exception as e:
        print(f"✗ 切换失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()