"""
TCP 诊断服务入口 —— 独立进程，无仿真依赖
"""
import signal
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tcp_diagnosis.server import TcpDiagnosisServer


def main():
    server = TcpDiagnosisServer()
    shutdown_flag = {"count": 0}

    def _shutdown(signum, frame):
        shutdown_flag["count"] += 1
        if shutdown_flag["count"] == 1:
            print("\n正在停止诊断服务...")
            server.stop()
        else:
            print("\n强制退出")
            sys.exit(1)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        server.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
