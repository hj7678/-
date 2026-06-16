"""
纯HMI主窗口 — 复用现有 SimulationView + StatusPanel
"""
import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QStatusBar,
    QScrollArea,
)
from PyQt5.QtCore import QTimer, Qt

from upper_hmi.physics_engine import PhysicsEngine
from views.simulation_view import SimulationView
from views.status_panel import StatusPanel
import config


class HmiMainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("上位机 HMI — FM接管模式")
        self.resize(1400, 850)

        self.engine = PhysicsEngine()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # 顶栏
        top = QHBoxLayout()
        top.addWidget(QLabel("上位机 HMI (FM接管)"))
        top.addStretch()

        self.btn_random = QPushButton("随机料位")
        self.btn_random.clicked.connect(lambda: self.engine.randomize_bin_levels(25, 90))
        top.addWidget(self.btn_random)

        self.btn_start = QPushButton("启动仿真")
        self.btn_start.setCheckable(True)
        self.btn_start.clicked.connect(self._toggle_run)
        top.addWidget(self.btn_start)

        self.lbl_status = QLabel("等待FM连接...")
        self.lbl_status.setStyleSheet("color:#2ECC71;font-weight:bold")
        top.addWidget(self.lbl_status)
        layout.addLayout(top)

        # 主体: 画布 + StatusPanel
        body = QHBoxLayout()

        self.canvas = SimulationView()
        self.canvas.setMinimumWidth(900)
        self.canvas.set_simulator(self.engine)
        body.addWidget(self.canvas, 2)

        right = QVBoxLayout()
        self.status_panel = StatusPanel()
        right.addWidget(self.status_panel, 1)
        body.addLayout(right, 1)

        layout.addLayout(body)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(50)

        self.engine.set_view(self.canvas)
        self._init_silo_view()
        self.engine.bridge.start()
        self.lbl_status.setText("FM接管已激活")

    def _init_silo_view(self):
        for i in range(1, 13):
            self.canvas.silo_compartments[f'S{i}'] = {
                'capacity': config.HIGH_SILO_BIN_CAPACITY,
                'current_level': config.HIGH_SILO_BIN_CAPACITY * 0.85,
                'is_target': False,
            }

    def _toggle_run(self, checked):
        if checked:
            self.engine.start()
            self.btn_start.setText("停止仿真")
        else:
            self.engine.stop()
            self.btn_start.setText("启动仿真")

    def _tick(self):
        if self.engine.is_running:
            self.engine.update(50)
            self.status_panel.update_all_status(self.engine)
        self.canvas.update()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(
        "QMainWindow{background-color:#161B22}"
        "QGroupBox{color:#C0C8D0;border:1px solid #30363D;margin-top:8px;padding-top:8px}"
        "QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 5px}"
    )
    window = HmiMainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
