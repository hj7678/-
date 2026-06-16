"""
上位机 HMI — 基于原有 main_window, 启动即 FM 接管模式

用法: python -m upper_hmi.main
"""
import sys
from views.main_window import MainWindow


def main():
    app = MainWindow._create_app() if hasattr(MainWindow, '_create_app') else None
    if app is None:
        from PyQt5.QtWidgets import QApplication
        app = QApplication(sys.argv)

    window = MainWindow()
    window.setWindowTitle("上位机 HMI — FM接管模式")

    # 自动初始化料位
    window.controller.randomize_bin_levels_percent(25, 90)
    # 自动连接桥接
    window.controller.start_feeding_bridge()
    # 自动启用FM接管 (调度由FM负责)
    window.controller.set_use_feeding_master(True)
    window.controller._auto_feeding_active = True  # 激活FM的调度检测
    # 自动仿真运行
    window.controller.is_running = True
    window.controller._runtime_timer.start()
    window.controller._last_runtime_ms = 0
    window.controller.feed_timer.start(window.controller.feed_interval)

    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()

