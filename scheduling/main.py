"""
调度服务入口 —— 独立进程，支持单服务和全服务两种模式

    python -m scheduling.main              # 启动全部 3 个调度服务
    python -m scheduling.main --belt D8    # 仅启动 D8 调度服务
"""
import sys
import os
import signal
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scheduling.server import SchedulingServer
from scheduling.config import SCHEDULER_PORTS, TCP_HOST


def _run_server(belt_id: str):
    port = SCHEDULER_PORTS[belt_id]
    server = SchedulingServer(belt_id=belt_id, host=TCP_HOST, port=port)
    shutdown_flag = {"count": 0}

    def _shutdown(signum, frame):
        shutdown_flag["count"] += 1
        if shutdown_flag["count"] == 1:
            print(f"\n正在停止 [{belt_id}] 调度服务...")
            server.stop()
        else:
            print(f"\n强制退出 [{belt_id}]")
            sys.exit(1)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        server.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


def main():
    parser = argparse.ArgumentParser(description="调度算法服务")
    parser.add_argument("--belt", type=str, default=None,
                        choices=["D7", "D8", "D9", "D6"],
                        help="仅启动指定皮带的调度服务（默认启动全部）")
    args = parser.parse_args()

    if args.belt:
        _run_server(args.belt)
    else:
        import multiprocessing
        print(f"启动全部 4 个调度服务 (D6:{SCHEDULER_PORTS['D6']}, D7:{SCHEDULER_PORTS['D7']}, D8:{SCHEDULER_PORTS['D8']}, D9:{SCHEDULER_PORTS['D9']})")
        processes = []
        for belt_id in ['D6', 'D7', 'D8', 'D9']:
            p = multiprocessing.Process(target=_run_server, args=(belt_id,))
            p.start()
            processes.append(p)
            print(f"  [{belt_id}] PID={p.pid}")

        try:
            for p in processes:
                p.join()
        except KeyboardInterrupt:
            print("\n正在停止所有调度服务...")
            for p in processes:
                p.terminate()
            for p in processes:
                p.join()
            print("所有调度服务已停止")


if __name__ == "__main__":
    main()
