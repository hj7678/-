"""
纯HMI主窗口 — 显示仿真画布 + 状态信息

复用现有 SimulationView 做皮带动画, 新增状态面板显示料位/传感器/路线。
"""
import sys
import signal
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QStatusBar,
    QTextEdit, QGroupBox, QGridLayout, QScrollArea,
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont

from upper_hmi.physics_engine import PhysicsEngine
import config
import pos


class HmiMainWindow(QMainWindow):
    """纯HMI主窗口"""

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

        # 主体: 画布 + 右侧状态
        body = QHBoxLayout()

        # 画布
        from views.simulation_view import SimulationView
        self.canvas = SimulationView()
        self.canvas.setMinimumWidth(800)
        body.addWidget(self.canvas, 2)

        # 右侧面板
        right = QVBoxLayout()
        right.setSpacing(6)

        # 料位
        grp_bins = QGroupBox("料仓料位 (P仓)")
        gl = QGridLayout()
        self._bin_labels = {}
        for col_i, col in enumerate(['P1', 'P2', 'P3', 'P4']):
            for row in range(7, 0, -1):
                bid = f"{col}-{row}"
                lbl = QLabel(f"{bid}: 0t")
                lbl.setStyleSheet("color:#8B949E;font-size:10px")
                gl.addWidget(lbl, 7 - row, col_i)
                self._bin_labels[bid] = lbl
        grp_bins.setLayout(gl)
        right.addWidget(grp_bins)

        # S仓
        grp_silo = QGroupBox("高位储料仓 (S仓)")
        gl2 = QGridLayout()
        self._silo_labels = {}
        for i in range(1, 13):
            bid = f"S{i}"
            lbl = QLabel(f"{bid}: 0t")
            lbl.setStyleSheet("color:#8B949E;font-size:10px")
            gl2.addWidget(lbl, (i - 1) // 4, (i - 1) % 4)
            self._silo_labels[bid] = lbl
        grp_silo.setLayout(gl2)
        right.addWidget(grp_silo)

        # 路线状态
        grp_routes = QGroupBox("路线状态")
        rl = QVBoxLayout()
        self._route_labels = {}
        for rid in config.FEED_ROUTES:
            lbl = QLabel(f"{rid}: idle")
            lbl.setStyleSheet("color:#8B949E;font-size:10px")
            rl.addWidget(lbl)
            self._route_labels[rid] = lbl
        grp_routes.setLayout(rl)
        right.addWidget(grp_routes)

        # 传感器
        grp_sensors = QGroupBox("接近开关 (激活=绿)")
        sl = QVBoxLayout()
        self._sensor_labels = {}
        for sid in config.SENSORS:
            lbl = QLabel(f"{sid}: OFF")
            lbl.setStyleSheet("color:#484F58;font-size:9px")
            sl.addWidget(lbl)
            self._sensor_labels[sid] = lbl
        grp_sensors.setLayout(sl)
        scr = QScrollArea()
        scr.setWidget(grp_sensors)
        scr.setMaximumHeight(200)
        right.addWidget(scr)

        # 指令日志
        grp_cmd = QGroupBox("FM指令日志")
        self.cmd_log = QTextEdit()
        self.cmd_log.setReadOnly(True)
        self.cmd_log.setMaximumHeight(150)
        self.cmd_log.setStyleSheet("background-color:#0D1117;color:#C0C8D0;font-size:10px")
        grp_cmd.setLayout(QVBoxLayout())
        grp_cmd.layout().addWidget(self.cmd_log)
        right.addWidget(grp_cmd)

        body.addLayout(right, 1)
        layout.addLayout(body)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

        # 定时器
        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(50)

        # 初始化
        self.engine.set_view(self.canvas)
        self._init_silo_view()

        # 启动桥接
        self.engine.bridge.start()
        self.lbl_status.setText("FM接管已激活")

    def _init_silo_view(self):
        for i in range(1, 13):
            bid = f'S{i}'
            self.canvas.silo_compartments[bid] = {
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
            self._refresh_display()
        self.canvas.update()

    def _refresh_display(self):
        if not self.engine.is_running:
            return
        # 料位
        for bid, lbl in self._bin_labels.items():
            sb = self.engine.small_bins.get(bid)
            if sb:
                pct = sb.level_percent
                color = "#2ECC71" if pct > 80 else "#F39C12" if pct > 30 else "#E74C3C"
                lbl.setText(f"{bid}: {sb.current_level:.0f}t ({pct:.0f}%)")
                lbl.setStyleSheet(f"color:{color};font-size:10px")
        # S仓
        if self.engine.view:
            for bid, lbl in self._silo_labels.items():
                silo = self.engine.view.silo_compartments.get(bid, {})
                cur = silo.get('current_level', 0)
                cap = silo.get('capacity', 420)
                pct = cur / cap * 100 if cap else 0
                lbl.setText(f"{bid}: {cur:.0f}t ({pct:.0f}%)")
        # 路线
        for rid, lbl in self._route_labels.items():
            ctx = self.engine.route_manager.get_route_context(rid)
            if ctx and rid in self.engine.active_routes:
                lbl.setText(f"{rid}: {ctx.state.value} → {ctx.target_bin or '?'}")
                lbl.setStyleSheet("color:#2ECC71;font-size:10px;font-weight:bold")
            else:
                lbl.setText(f"{rid}: idle")
                lbl.setStyleSheet("color:#8B949E;font-size:10px")
        # 传感器
        for sid, lbl in self._sensor_labels.items():
            s = self.engine.sensors.get(sid)
            if s:
                active = s.is_active
                lbl.setText(f"{sid}: {'ON' if active else 'OFF'}")
                lbl.setStyleSheet(f"color:{'#2ECC71' if active else '#484F58'};font-size:9px")


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet("QMainWindow{background-color:#161B22} QGroupBox{color:#C0C8D0;border:1px solid #30363D;margin-top:8px;padding-top:8px} QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 5px}")
    window = HmiMainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
