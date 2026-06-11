"""PLC 模拟器 — Modbus TCP 从站模拟实际 PLC 的 I/O 行为

启动: python -m plc_simulator.main [--port 1502]
"""
import sys
import signal
import threading
from plc_simulator.modbus_server import PlcSimulatorServer, HOST, PORT
from plc_simulator.physics_engine import PhysicsEngine


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else PORT

    server = PlcSimulatorServer(HOST, port)
    physics = PhysicsEngine(server.mem)

    def _shutdown(*_):
        print("\n[PLC Sim] 收到终止信号...", flush=True)
        physics.stop()
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    physics.start()
    print("[PLC Sim] ======================================", flush=True)
    print("[PLC Sim]  PLC 模拟器已就绪", flush=True)
    print(f"[PLC Sim]  Modbus TCP: {HOST}:{port}", flush=True)
    print("[PLC Sim]  线圈:      1001-1019 (皮带) + 2001-2007 (斗) + 3001-3013 (小车/上料)", flush=True)
    print("[PLC Sim]  离散输入:  1001-1020 (接近开关) + 2001-2007 (斗到位) + 3001-4004 (小车)", flush=True)
    print("[PLC Sim]  保持寄存器: 40051-40057 (称重) + 40101-40104 (小车位置) + 40201-40219 (皮带速度)", flush=True)
    print("[PLC Sim] ======================================", flush=True)

    try:
        server.start()
    except KeyboardInterrupt:
        _shutdown()


if __name__ == '__main__':
    main()
