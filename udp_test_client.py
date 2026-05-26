"""
UDP 二进制帧测试客户端
监听指定端口，解析并打印二进制帧内容，用于验证 udp_binary_sender.py 的输出正确性。
"""
import socket
import struct
import argparse

FRAME_SIZE = 57
FRAME_MAGIC = 0xA55A

_SENSOR_IDS = [
    'S-E1', 'S-E2', 'S-E4', 'S-E5', 'S-E6', 'S-E7', 'S-E8', 'S-E9', 'S-E10',
    'S-D1', 'S-D2', 'S-D2-2', 'S-D3', 'S-D4', 'S-D5', 'S-D6', 'S-D7',
    'S-D8', 'S-D9', 'S-D13',
]

_HOPPER_IDS = ['hopper1', 'hopper2', 'hopper3', 'hopper4', 'hopper5', 'hopper6', 'hopper7']

_CART_IDS = ['Cart1', 'Cart2', 'Cart3', 'Cart4']
_CART_FIELDS = ['left_limit', 'right_limit', 'left_divert', 'right_divert']

_CSV_IDS = [
    'S-CV-E1', 'S-CV-E2', 'S-CV-E4', 'S-CV-E5', 'S-CV-E6',
    'S-CV-E7', 'S-CV-E8', 'S-CV-E9', 'S-CV-E10',
    'S-CV-D1', 'S-CV-D2', 'S-CV-D3', 'S-CV-D4', 'S-CV-D5',
    'S-CV-D6', 'S-CV-D7', 'S-CV-D8', 'S-CV-D9', 'S-CV-D13',
]


def _calc_crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def _get_bit(buf: bytes, byte_offset: int, bit: int) -> bool:
    return bool((buf[byte_offset] >> bit) & 0x01)


def parse_frame(data: bytes) -> dict:
    """解析 57 字节二进制帧，返回可读字典"""
    if len(data) < FRAME_SIZE:
        return {"error": f"帧长度不足: {len(data)} < {FRAME_SIZE}"}

    magic = struct.unpack_from('>H', data, 0)[0]
    if magic != FRAME_MAGIC:
        return {"error": f"帧头不匹配: 0x{magic:04X} != 0x{FRAME_MAGIC:04X}"}

    version = data[2]
    seq = data[3]
    timestamp = struct.unpack_from('>I', data, 4)[0]

    # 解析布尔量位域
    bools = {}
    # 接近开关 (20个)
    for i, sid in enumerate(_SENSOR_IDS):
        byte_off = 8 + (i // 8)
        bit = i % 8
        bools[sid] = _get_bit(data, byte_off, bit)

    # 中转斗开关 (7个)
    for i, hid in enumerate(_HOPPER_IDS):
        bit_idx = 20 + i
        byte_off = 8 + (bit_idx // 8)
        bit = bit_idx % 8
        bools[hid] = _get_bit(data, byte_off, bit)

    # 小车限位/分料 (16个)
    for ci, cart_id in enumerate(_CART_IDS):
        for fi, field in enumerate(_CART_FIELDS):
            bit_idx = 27 + ci * 4 + fi
            byte_off = 8 + (bit_idx // 8)
            bit = bit_idx % 8
            bools[f"{cart_id}_{field}"] = _get_bit(data, byte_off, bit)

    # 皮带转速 (sint8, 偏移 14~32)
    speeds = {}
    for i, sid in enumerate(_CSV_IDS):
        val = data[14 + i]
        if val > 127:
            val -= 256  # 转有符号
        speeds[sid] = val

    # 中转斗称重 (uint16 大端, 偏移 33~46)
    weights = {}
    for i, hid in enumerate(_HOPPER_IDS):
        weights[hid] = struct.unpack_from('>H', data, 33 + i * 2)[0]

    # 小车位置 (uint8, 偏移 47~50)
    positions = {}
    for i, cart_id in enumerate(_CART_IDS):
        positions[cart_id] = data[47 + i]

    # CRC16 校验
    expected_crc = struct.unpack_from('>H', data, 55)[0]
    actual_crc = _calc_crc16(data[:55])
    crc_ok = (expected_crc == actual_crc)

    return {
        "magic": f"0x{magic:04X}",
        "version": version,
        "seq": seq,
        "timestamp": timestamp,
        "bools": bools,
        "speeds": speeds,
        "weights": weights,
        "positions": positions,
        "crc": f"0x{expected_crc:04X}",
        "crc_ok": crc_ok,
    }


def main():
    parser = argparse.ArgumentParser(description="UDP 二进制帧测试客户端")
    parser.add_argument("--port", type=int, default=8889, help="监听端口 (默认 8889)")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认 0.0.0.0)")
    parser.add_argument("--count", type=int, default=0, help="接收帧数后退出 (0=无限)")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))
    sock.settimeout(5)

    print(f"监听 UDP {args.host}:{args.port} ...")
    print(f"帧大小: {FRAME_SIZE} 字节")
    print("-" * 50)

    received = 0
    try:
        while args.count == 0 or received < args.count:
            try:
                data, addr = sock.recvfrom(1024)
                received += 1
                result = parse_frame(data)

                if "error" in result:
                    print(f"[{received}] 错误: {result['error']}")
                    continue

                print(f"\n{'='*60}")
                print(f"[第 {received} 帧] 来自 {addr}")
                print(f"  帧头: {result['magic']}  版本: {result['version']}  序号: {result['seq']}")
                print(f"  时间戳: {result['timestamp']}  CRC: {result['crc']} {'✓' if result['crc_ok'] else '✗'}")

                # --- 接近开关 (20个) ---
                print(f"\n  接近开关 (20个):")
                for i, sid in enumerate(_SENSOR_IDS):
                    state = "■ ON " if result['bools'][sid] else "□ OFF"
                    sep = "\n    " if (i + 1) % 5 == 0 and i < len(_SENSOR_IDS) - 1 else ""
                    print(f"    {sid}: {state}", end=sep)

                # --- 皮带转速 (19个) ---
                print(f"\n\n  皮带转速传感器 (19个, sint8):")
                for i, sid in enumerate(_CSV_IDS):
                    v = result['speeds'][sid]
                    sep = "\n    " if (i + 1) % 5 == 0 and i < len(_CSV_IDS) - 1 else ""
                    print(f"    {sid}: {v}", end=sep)

                # --- 中转斗 (7个) ---
                print(f"\n\n  中转斗开关及称重 (7个):")
                for hid in _HOPPER_IDS:
                    switch = "开" if result['bools'][hid] else "关"
                    w = result['weights'][hid]
                    print(f"    {hid}: 开关={switch}, 称重={w}kg")

                # --- 小车传感器 (4个) ---
                print(f"\n  小车传感器 (4个):")
                for cart_id in _CART_IDS:
                    pos = result['positions'][cart_id]
                    ll = "■" if result['bools'][cart_id + '_left_limit'] else "□"
                    rl = "■" if result['bools'][cart_id + '_right_limit'] else "□"
                    ld = "■" if result['bools'][cart_id + '_left_divert'] else "□"
                    rd = "■" if result['bools'][cart_id + '_right_divert'] else "□"
                    print(f"    {cart_id}: 位置={pos}  左限={ll} 右限={rl} 左分={ld} 右分={rd}")

                print(f"\n{'='*60}")

            except socket.timeout:
                if args.count == 0:
                    continue
                else:
                    print(f"\n超时：收到 {received}/{args.count} 帧")
                    break
    except KeyboardInterrupt:
        print(f"\n\n已停止。共收到 {received} 帧。")
    finally:
        sock.close()


if __name__ == '__main__':
    main()
