"""
纯HMI上位机 — 启动入口

用法: python -m upper_hmi.main

前置依赖:
  python -m stock_management.main    # :8895
  python -m feeding_master.main      # :8896
  python -m scheduling.main          # :8891-8894 (可选)

启动自动连接FM, 零手动操作。
"""
import sys
import signal
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QStatusBar, QSplitter,
)
from PyQt5.QtCore import QTimer, Qt

from upper_hmi.physics_engine import PhysicsEngine
import config
import pos


class HmiMainWindow(QMainWindow):
    """纯HMI主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("上位机 HMI — FM接管模式")
        self.setGeometry(100, 50, 1400, 850)

        # 物理引擎
        self.engine = PhysicsEngine()

        # 主布局
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)

        # 顶栏
        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("上位机 HMI"))
        top_bar.addStretch()

        self.btn_randomize = QPushButton("随机初始化料位")
        self.btn_randomize.clicked.connect(self._on_randomize)
        top_bar.addWidget(self.btn_randomize)

        self.btn_start = QPushButton("启动仿真")
        self.btn_start.setCheckable(True)
        self.btn_start.clicked.connect(self._on_start_toggled)
        top_bar.addWidget(self.btn_start)

        layout.addLayout(top_bar)

        # 画布 (复用现有 simulation_view)
        from views.simulation_view import SimulationView
        self.canvas = SimulationView()
        self.canvas.setMinimumHeight(550)
        layout.addWidget(self.canvas, 1)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪 — 等待FM连接...")

        # 定时器
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(50)

        # 桥接状态
        self._bridge_ready = False

        # 启动桥接
        self._start_bridge()

    def _start_bridge(self):
        self.engine.bridge.start()
        self.engine._use_feeding_master = True
        self.status_bar.showMessage("FM接管模式 — 桥接已连接")
        self._bridge_ready = True
        print("[HMI] FM接管模式已激活", flush=True)

    def _on_randomize(self):
        self.engine.randomize_bin_levels(25.0, 90.0)
        self.status_bar.showMessage("料位已随机初始化 (25-90%)")

    def _on_start_toggled(self, checked: bool):
        if checked:
            self.engine.start()
            self.btn_start.setText("停止仿真")
            self.status_bar.showMessage("仿真运行中 — FM接管")
        else:
            self.engine.stop()
            self.btn_start.setText("启动仿真")
            self.status_bar.showMessage("仿真已停止")

    def _tick(self):
        if self.engine.is_running:
            self.engine.update(50)
        self.canvas.update()


def main():
    app = QApplication(sys.argv)

    # 设置引擎view引用
    window = HmiMainWindow()
    window.engine.set_view(window.canvas)

    # 同步高位仓初始数据到view
    for i in range(1, 13):
        bid = f'S{i}'
        capacity = config.HIGH_SILO_BIN_CAPACITY
        window.canvas.silo_compartments[bid] = {
            'capacity': capacity,
            'current_level': capacity * 0.85,
            'is_target': False,
        }

    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
