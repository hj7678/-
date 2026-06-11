"""FeedingMaster — 上料主控独立进程

启动: python -m feeding_master.main
"""
import sys
import signal
import time
from feeding_master.tcp_server import FeedingMasterServer, HOST, PORT
from feeding_master.master_controller import FeedingMasterController
from feeding_master.stock_client import StockClient


def main():
    server = FeedingMasterServer(HOST, PORT)
    controller = FeedingMasterController(server)
    stock = controller.stock

    def _shutdown(*_):
        print("\n[FeedingMaster] 收到终止信号...", flush=True)
        controller.stop()
        server.stop()
        stock.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # 连接 Stock Management
    print("[FeedingMaster] 正在连接 Stock Management...", flush=True)
    for _ in range(10):
        if stock.connect():
            break
        time.sleep(1)
    else:
        print("[FeedingMaster] 警告: 无法连接 Stock Management, 料位数据不可用", flush=True)

    # 启动控制循环
    controller.start()

    # 启动 TCP Server (阻塞)
    try:
        server.start()
    except KeyboardInterrupt:
        _shutdown()


if __name__ == '__main__':
    main()
