"""Stock Management — 料仓库存管理独立进程

启动: python -m stock_management.main
"""
import sys
import signal
from stock_management.tcp_server import StockServer, HOST, PORT


def main():
    server = StockServer(HOST, PORT)

    def _shutdown(*_):
        print("\n[StockMgmt] 收到终止信号...", flush=True)
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        server.start()
    except KeyboardInterrupt:
        _shutdown()


if __name__ == '__main__':
    main()
