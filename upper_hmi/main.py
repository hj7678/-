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

    # 自动初始化料位 + 桥接 + FM接管
    window.controller.randomize_bin_levels_percent(25, 90)
    window.controller.start_feeding_bridge()
    window.controller.set_use_feeding_master(True)
    # 调度由UI"调度服务"按钮控制(FM接管下不启动仿真调度, 只设_auto_feeding_active)
    window.controller._auto_feeding_active = False  # 初始关闭, 等用户点击
    # 自动仿真运行
    window.controller.is_running = True
    window.controller._runtime_timer.start()
    window.controller._last_runtime_ms = 0
    window.controller.feed_timer.start(window.controller.feed_interval)
    # 隐藏不需要的按钮(FM接管+桥接已默认启用)
    if hasattr(window, 'top_bridge_btn'): window.top_bridge_btn.hide()
    if hasattr(window, 'top_fm_btn'): window.top_fm_btn.hide()
    # FM接管: 诊断结果由FM推送
    if hasattr(window.control_panel, 'diag_mode_layout'):
        for i in range(window.control_panel.diag_mode_layout.count()):
            w = window.control_panel.diag_mode_layout.itemAt(i).widget()
            if w: w.hide()

    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()

