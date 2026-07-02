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
    ("Feed Material", "feed_material_service.main"),
    ("Upper HMI", "upper_hmi.main"),
]

def main():
    print("=" * 50)
    print(" FM 接管模式 — 一键启动")
    print("=" * 50)
    for name, module in SERVICES:
        print(f"\n>>> 启动: {name}")
        if os.name == 'nt':
            subprocess.Popen(
                f'start "{name}" cmd /k "title {name} && py -m {module}"',
                shell=True,
            )
        else:
            subprocess.Popen(
                [sys.executable, "-m", module],
            )
        if name != "Upper HMI":
            time.sleep(2)
    print("\n" + "=" * 50)
    print(" 全部已启动! 关闭此窗口不影响服务.")
    print("=" * 50)
    input("按 Enter 退出此窗口...")

if __name__ == "__main__":
    main()
