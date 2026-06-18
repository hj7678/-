"""
FM接管模式一键启动器
"""
import subprocess
import sys
import time
import os

SERVICES = [
    ("Stock Management", "stock_management.main"),
    ("Scheduling", "scheduling.main"),
    ("Fault Diagnosis", "tcp_diagnosis.main"),
    ("FeedingMaster", "feeding_master.main"),
    ("Upper HMI", "upper_hmi.main"),
]

def main():
    print("=" * 50)
    print(" FM 接管模式 — 一键启动")
    print("=" * 50)
    processes = []
    for name, module in SERVICES:
        title = f"FM-{name}"
        print(f"\n>>> 启动: {name} ({module})")
        proc = subprocess.Popen(
            [sys.executable, "-m", module],
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0,
        )
        processes.append((name, proc))
        if name != "Upper HMI":
            time.sleep(2)  # 等服务就绪
    print("\n" + "=" * 50)
    print(" 全部已启动! 关闭此窗口不影响服务.")
    print("=" * 50)
    try:
        for name, proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        print("\n正在关闭所有服务...")
        for name, proc in processes:
            proc.terminate()

if __name__ == "__main__":
    main()
