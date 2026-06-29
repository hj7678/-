"""
纯物理引擎 — 物料运动、传感器检测、斗物理，零决策逻辑

从 simulation_controller 提取纯物理方法。
FM 接管模式下由 FM 指令驱动执行器，本模块只跑物理。
"""
import math
import random
import sys
import time
from typing import Dict, List, Optional, Set, Tuple

from PyQt5.QtCore import QObject, QTimer, QElapsedTimer, pyqtSignal

import config
import pos
from models.material import Material, MaterialFactory, MaterialType
from shared.plc_runtime.models import (
    Conveyor, Sensor, TransferHopper, SmallBin,
    _FallbackSensor, _FALLBACK_SENSOR,
)
from shared.route_state_manager import (
    RouteState, RouteStateManager, get_route_state_manager,
)
from controllers.simulation_feeding_bridge import SimulationFeedingBridge


class PhysicsEngine(QObject):
    """纯物理引擎 — 物料运动 + 传感器 + 斗，零决策"""

    # 信号 (UI 刷新用)
    material_spawned = pyqtSignal(object)
    material_moved = pyqtSignal(object)
    material_arrived = pyqtSignal(object, str)
    sensor_triggered = pyqtSignal(str, bool)
    state_changed = pyqtSignal(str, dict)

    _ENDPOINT_BASE = {'D7': 22.1, 'D8': 17.4, 'D9': 12.1}
    _LINE_SPACING = 5.4
    _ENDPOINT_SENSORS = {'D7': 'S-D7', 'D8': 'S-D8', 'D9': 'S-D9', 'D6': 'S-D6'}
    _HOPPER_BELT_TIMEOUTS = {
        ('route1', 'S-E1'): 8.4, ('route1', 'S-E4'): 34.4,
        ('route2', 'S-E2'): 9.6, ('route2', 'S-E4'): 34.4,
        ('route3', 'S-E5'): 12.3,
        ('route1', 'S-E8'): 24.7, ('route2', 'S-E8'): 24.7, ('route3', 'S-E8'): 24.7,
        ('route1', 'S-E10'): 15.3, ('route2', 'S-E10'): 15.3, ('route3', 'S-E10'): 15.3,
        ('route4', 'S-E6'): 10.6, ('route4', 'S-E7'): 23.3, ('route4', 'S-E9'): 20.2,
        ('route5', 'S-E6'): 10.6, ('route5', 'S-E7'): 23.3, ('route5', 'S-E9'): 20.2,
        ('route5', 'S-D5'): 12.3,
        ('route6', 'S-D13'): 8.0, ('route6', 'S-D2'): 27.0, ('route6', 'S-D4'): 9.6,
        ('route7', 'S-D1'): 27.0, ('route7', 'S-D3'): 15.9,
        ('route8', 'S-D4'): 9.6, ('route8', 'S-D2-2'): 7.3,
    }

    def __init__(self):
        super().__init__()

        # 设备
        self.conveyors: Dict[str, Conveyor] = {}
        self.sensors: Dict[str, Sensor] = {}
        self.hoppers: Dict[str, TransferHopper] = {}
        self.small_bins: Dict[str, SmallBin] = {}

        # 物料
        self.materials: List[Material] = []
        self.active_materials: List[Material] = []
        self.route_material_map: Dict[str, List[Material]] = {}

        # 路线
        self.active_routes: Set[str] = set()
        self.route_to_bin: Dict[str, str] = {}
        self.route_manager = get_route_state_manager()
        self.route_state_manager = self.route_manager  # 别名 (bridge 用)

        # 小车
        self.cart_positions: Dict[str, int] = {
            'Cart1': 1, 'Cart2': 1, 'Cart3': 1,
        }
        self.cart_target_positions = dict(self.cart_positions)
        self.cart_sensor_positions = dict(self.cart_positions)
        self.cart_divert: Dict[str, tuple] = {
            'Cart1': (False, False), 'Cart2': (False, False),
            'Cart3': (False, False), 'Cart4': (False, False),
        }
        self.cart4_position = 1
        self.cart4_target_position = 1
        self.cart4_sensor_position = 1

        # 仿真状态
        self.speed = config.DEFAULT_SPEED
        self.is_running = False
        self.total_runtime = 0.0
        self.total_materials_sent = 0
        self.feed_rate = config.FEED_RATE
        self.material_types = ['stone_powder']

        # 上料点
        self.feed_points = config.FEED_POINTS.copy()

        # 消耗速率
        self._consumption_rates: Dict[str, float] = {}
        self._maintenance_bins: Set[str] = set()

        # 计时器
        self.feed_timer = QTimer()
        self.feed_timer.timeout.connect(self._spawn_materials)
        self.feed_interval = 500
        self._runtime_timer = QElapsedTimer()
        self._last_runtime_ms = 0

        # 桥接 (自动启动)
        self.bridge = SimulationFeedingBridge(self)
        self.bridge.command_received.connect(self._on_bridge_commands)

        # 参考 (view 引用用于高位仓显示)
        self.view = None

        # 物料类型缓存
        self.route_material_cache: Dict[str, str] = {}

        self._init_components()

    def _init_components(self):
        """初始化所有设备"""
        # 皮带
        for conv_id, conv_config in config.CONVEYORS.items():
            self.conveyors[conv_id] = Conveyor(conv_id, conv_config)

        # 传感器
        for sensor_id, sensor_config in config.SENSORS.items():
            self.sensors[sensor_id] = Sensor(sensor_id, sensor_config)

        # 中转斗
        for hp_id, hp_config in config.TRANSFER_HOPPERS.items():
            self.hoppers[hp_id] = TransferHopper(hp_id, hp_config)

        # 小仓
        bs = config.BATCHING_STATION
        columns = bs.get('columns', 4)
        rows = bs.get('rows', 7)
        col_names = bs.get('col_names', ['P1', 'P2', 'P3', 'P4'])
        target_conveyors = ['D7', 'D8', 'D9', 'D7']
        for row in range(rows):
            for col in range(columns):
                bid = f"{col_names[col]}-{row + 1}"
                self.small_bins[bid] = SmallBin(bid, {
                    'name': bid, 'column': col, 'row': row,
                    'target_conveyor': target_conveyors[col % 4],
                    'capacity': config.BATCHING_BIN_CAPACITY,
                })

        # 消耗速率
        for bid in self.small_bins:
            self._consumption_rates[bid] = 0.01

    # ── 生命周期 ──

    def start(self):
        self.is_running = True
        self._runtime_timer.start()
        self._last_runtime_ms = 0
        self.feed_timer.start(self.feed_interval)
        self.bridge.start()
        self.state_changed.emit('simulation', {'running': True})
        print("[HMI] 物理引擎已启动 (FM接管模式)", flush=True)

    def stop(self):
        self.is_running = False
        self.feed_timer.stop()
        self.bridge.stop()
        self.state_changed.emit('simulation', {'running': False})
        print("[HMI] 物理引擎已停止", flush=True)

    def update(self, delta_time_ms: int):
        """每帧更新 (50ms timer)"""
        if not self.is_running:
            return

        current_ms = self._runtime_timer.elapsed()
        delta_runtime_ms = current_ms - self._last_runtime_ms
        self._last_runtime_ms = current_ms
        delta_seconds = delta_runtime_ms / 1000.0
        self.total_runtime += delta_seconds

        # 桥接推送
        self.bridge.tick()

        # 纯物理
        self._update_hoppers(delta_seconds)
        self._update_materials(delta_seconds)
        self._update_sensors()
        self._update_bin_consumption(delta_seconds)

    # ── Bridge 指令 ──

    def _on_bridge_commands(self, commands: list):
        """FM 指令 → 直接执行"""
        if commands:
            kinds = set(c.get('device','') for c in commands)
            print(f"[HMI] 收到FM指令: {len(commands)}条 ({', '.join(kinds)})", flush=True)
        self.bridge.apply_commands(commands)

    # ── 物料生成 ──

    def _spawn_materials(self):
        """上料点生成物料"""
        if not self.is_running:
            return
        for route_id in list(self.active_routes):
            ctx = self.route_manager.get_route_context(route_id)
            if not ctx or ctx.state != RouteState.FEEDING:
                continue
            if not ctx.target_bin:
                continue

            route = config.FEED_ROUTES.get(route_id, {})
            first_conv = route.get('conveyors', [''])[0]
            if not first_conv or first_conv not in self.conveyors:
                continue

            mat_type = self.route_material_cache.get(route_id)
            if mat_type is None:
                types = route.get('material_types', ['stone_powder']) or ['stone_powder']
                mat_type = random.choice(types)
                self.route_material_cache[route_id] = mat_type

            conv = self.conveyors[first_conv]
            if not conv.is_running:
                continue

            material = Material.create(mat_type, conv.start_pos)
            material.current_conveyor = first_conv
            material.distance_on_conveyor = 0.0
            material.is_active = True
            conv.materials_on_belt.append(material)
            self.materials.append(material)
            self.active_materials.append(material)
            if route_id not in self.route_material_map:
                self.route_material_map[route_id] = []
            self.route_material_map[route_id].append(material)
            self.material_spawned.emit(material)
            self.total_materials_sent += 1

    # ── 斗更新 ──

    def _update_hoppers(self, delta_seconds: float):
        for hp_id, hopper in self.hoppers.items():
            if not hopper.is_active:
                continue
            eff = hopper.get_effective_switch_state()
            if not eff:
                continue

            output_conv = hopper.output_conveyor
            if not output_conv or output_conv not in self.conveyors:
                continue
            next_conv = self.conveyors[output_conv]
            if not next_conv.is_running:
                continue

            mat = hopper.release_material()
            if mat:
                mat.current_conveyor = output_conv
                mat.distance_on_conveyor = 0.0
                mat.is_active = True
                next_conv.materials_on_belt.append(mat)
                self.active_materials.append(mat)

    # ── 物料运动 ──

    def _update_materials(self, delta_seconds: float):
        for material in self.active_materials[:]:
            if not material.is_active or not material.current_conveyor:
                continue
            conv = self.conveyors.get(material.current_conveyor)
            if not conv or not conv.is_running:
                continue

            speed_mult = getattr(material, 'belt_speed_multiplier', 1.0)
            pixel_distance = conv.current_speed_pps * speed_mult * delta_seconds
            material.distance_on_conveyor += pixel_distance

            if material.distance_on_conveyor >= conv.pixel_length:
                material.distance_on_conveyor = conv.pixel_length
                self._handle_conveyor_end(material)

            self.material_moved.emit(material)

    def _handle_conveyor_end(self, material: Material):
        conv_id = material.current_conveyor
        conv = self.conveyors.get(conv_id)
        if not conv:
            return

        # 从当前皮带移除
        if material in conv.materials_on_belt:
            conv.materials_on_belt.remove(material)
        if material in self.active_materials:
            self.active_materials.remove(material)

        # 找路线 → 找下一个目标
        for route_id in list(self.active_routes):
            route = config.FEED_ROUTES.get(route_id, {})
            conveyors = route.get('conveyors', [])
            hoppers = route.get('hoppers', [])
            if conv_id not in conveyors:
                continue
            idx = conveyors.index(conv_id)

            # 终点皮带 → 到达料仓
            if idx == len(conveyors) - 1:
                target_bin = self.route_to_bin.get(route_id)
                if target_bin and target_bin in self.small_bins:
                    self.small_bins[target_bin].receive_material(config.MATERIAL_WEIGHT)
                    self.material_arrived.emit(material, target_bin)
                material.is_active = False
                return

            # 有中转斗
            if hoppers and idx < len(hoppers) and hoppers[idx]:
                hp_id = hoppers[idx]
                if hp_id in self.hoppers:
                    hopper = self.hoppers[hp_id]
                    if hopper.get_effective_switch_state():
                        hopper.receive_material_direct()
                        material.is_active = False
                    else:
                        hopper.store_material(material, self.total_runtime)
                        material.is_active = False
                    return

            # 下一皮带
            if idx + 1 < len(conveyors):
                next_cid = conveyors[idx + 1]
                if next_cid in self.conveyors and self.conveyors[next_cid].is_running:
                    material.current_conveyor = next_cid
                    material.distance_on_conveyor = 0.0
                    material.is_active = True
                    self.conveyors[next_cid].materials_on_belt.append(material)
                    self.active_materials.append(material)
                    return

        material.is_active = False

    # ── 传感器 ──

    def _update_sensors(self):
        for sid, sensor in self.sensors.items():
            sensor.is_active = sensor.real_state
            if not sensor.real_state:
                sensor.hold_timer = max(0, sensor.hold_timer - 50)

    # ── 料仓消耗 ──

    def _update_bin_consumption(self, delta_seconds: float):
        for bid, sb in self.small_bins.items():
            if bid in self._maintenance_bins:
                continue
            rate = self._consumption_rates.get(bid, 0.01)
            consumed = rate * delta_seconds
            sb.current_level = max(0.0, sb.current_level - consumed)

    # ── 初始化 ──

    def randomize_bin_levels(self, lo: float = 25.0, hi: float = 90.0):
        for sb in self.small_bins.values():
            pct = random.uniform(lo, hi)
            sb.current_level = round(pct * sb.capacity / 100.0, 2)
        self.bridge.randomize_stock_levels(lo, hi)

    _auto_feeding_active = True  # FM接管 = 始终自动上料

    @property
    def _use_feeding_master(self):
        return True

    # status_panel 需要的属性
    laser_sensor_states: Dict[str, bool] = {}

    # SimulationView 需要的属性
    @property
    def cart4_is_moving(self):
        return False
    route_silo_bin: Dict[str, str] = {}
    route_material_cache: Dict[str, str] = {}

    # StatusPanel 需要的桩方法
    def get_faulty_sensors(self): return set()
    def get_diagnosis_result(self): return []
    def get_laser_sensor_state(self, lid): return True
    def get_all_level_sensors(self): return {}
    def is_conveyor_on_route(self, conv_id):
        for rid in self.active_routes:
            r = config.FEED_ROUTES.get(rid, {})
            if conv_id in r.get('conveyors', []):
                return True
        return False
    def get_hopper_switch_state(self, hid):
        h = self.hoppers.get(hid)
        return h.get_effective_switch_state() if h else False
    def is_hopper_active(self, hid):
        h = self.hoppers.get(hid)
        return h.is_active if h else False
    def get_sensor_state(self, sid):
        s = self.sensors.get(sid)
        return s.is_active if s else False
    def get_conveyor_state(self, cid):
        c = self.conveyors.get(cid)
        return {'is_running': c.is_running, 'speed': c.current_speed, 'on_route': self.is_conveyor_on_route(cid)} if c else {'is_running': False, 'speed': 0, 'on_route': False}
    def get_hopper_level(self, hid):
        h = self.hoppers.get(hid)
        return h.get_display_weight() if h else 0
    def get_status(self):
        return {
            'total_runtime': self.total_runtime,
            'total_feed_weight': self.total_materials_sent * config.MATERIAL_WEIGHT,
            'active_routes': list(self.active_routes),
        }
    def is_dirty(self): return True
    def get_level_sensor(self, bid):
        sb = self.small_bins.get(bid)
        return sb.current_level if sb else 0

    def set_view(self, view):
        self.view = view
