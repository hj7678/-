"""
I/O 抽象总线 — 统一数据访问层

通过标签名(tag)访问所有外部数据，底层驱动负责路由到仿真内存或PLC。
替换仿真对象直接读写，使上层逻辑与数据源解耦。

用法:
    io = IOBus(SimDriver(controller))
    level = io.read("bin.P1-5.level")
    io.write("hopper.hopper1.switch", False)

Tag 命名: <组件类型>.<组件ID>.<属性>
- bin.P1-5.level      料位百分比
- belt.D7.running     皮带运行状态
- hopper.hopper1.switch 中转斗开关
- hopper.hopper1.weight 中转斗称重(t)
- cart.Cart2.position 小车传感器位置
- cart.Cart2.left_divert  左分料
- sensor.S-D7.active  接近开关状态
- laser.feed1_1.has_material 激光传感器
"""

from typing import Any, Dict, Optional


# =============================================================================
# 驱动接口
# =============================================================================

class IODriver:
    """I/O 驱动基类"""
    def read(self, tag: str) -> Any:
        raise NotImplementedError
    def write(self, tag: str, value: Any):
        raise NotImplementedError


# =============================================================================
# 仿真驱动
# =============================================================================

class SimDriver(IODriver):
    """仿真模式：读写仿真内存对象"""

    def __init__(self, controller=None):
        self._ctrl = controller  # SimulationController 引用
        # tag读写缓存（增量同步用）
        self._last_written: Dict[str, Any] = {}

    def set_controller(self, controller):
        self._ctrl = controller

    def read(self, tag: str) -> Any:
        if not self._ctrl:
            return None
        parts = tag.split('.', 2)
        if len(parts) < 3:
            return None
        kind, obj_id, attr = parts[0], parts[1], parts[2]

        if kind == 'bin':
            if obj_id in self._ctrl.small_bins:
                sb = self._ctrl.small_bins[obj_id]
                if attr == 'level':
                    return sb.level_percent
                if attr == 'capacity':
                    return sb.capacity
                if attr == 'current':
                    return sb.current_level
            if obj_id.startswith('S'):
                if hasattr(self._ctrl, 'view') and self._ctrl.view:
                    comp = self._ctrl.view.silo_compartments.get(obj_id, {})
                    cur = comp.get('current_level', 0)
                    cap = comp.get('capacity', 100)
                    if attr == 'level':
                        return cur / cap * 100 if cap > 0 else 0.0
                    if attr == 'current':
                        return cur
                    if attr == 'capacity':
                        return cap

        elif kind == 'belt':
            conv = self._ctrl.conveyors.get(obj_id)
            if conv:
                if attr == 'running':
                    return conv.is_running
                if attr == 'speed':
                    return conv.speed

        elif kind == 'hopper':
            hp = self._ctrl.hoppers.get(obj_id)
            if hp:
                if attr == 'switch':
                    return hp.is_open
                if attr == 'weight':
                    return hp.get_display_weight()
                if attr == 'level':
                    return hp.level_percent

        elif kind == 'cart':
            if attr == 'position':
                if obj_id == 'Cart4':
                    return int(getattr(self._ctrl, 'cart4_sensor_position', 1))
                return self._ctrl.cart_sensor_positions.get(obj_id, 1)
            if attr == 'target':
                if obj_id == 'Cart4':
                    return getattr(self._ctrl, 'cart4_target_position', 1)
                return self._ctrl.cart_target_positions.get(obj_id, 1)
            if attr == 'moving':
                if obj_id == 'Cart4':
                    return getattr(self._ctrl, 'cart4_is_moving', False)
                return self._ctrl.cart_positions.get(obj_id, 1) != self._ctrl.cart_target_positions.get(obj_id, 1)
            if attr == 'left_divert':
                return self._ctrl.cart_divert.get(obj_id, (False, False))[0]
            if attr == 'right_divert':
                return self._ctrl.cart_divert.get(obj_id, (False, False))[1]

        elif kind == 'sensor':
            s = self._ctrl.sensors.get(obj_id)
            if s:
                return s.is_active

        elif kind == 'laser':
            return self._ctrl.laser_sensor_states.get(obj_id, False)

        elif kind == 'feed_point':
            fp = self._ctrl.feed_points.get(obj_id, {})
            return fp.get('has_material', True)

        return None

    def write(self, tag: str, value: Any):
        if not self._ctrl:
            return
        parts = tag.split('.', 2)
        if len(parts) < 3:
            return
        kind, obj_id, attr = parts[0], parts[1], parts[2]

        if kind == 'belt':
            conv = self._ctrl.conveyors.get(obj_id)
            if conv and attr == 'running':
                if value:
                    conv.start(self._ctrl.speed)
                else:
                    conv.stop()

        elif kind == 'hopper':
            hp = self._ctrl.hoppers.get(obj_id)
            if hp and attr == 'switch':
                hp.is_open = value

        elif kind == 'cart':
            if attr == 'position':
                if obj_id == 'Cart4':
                    self._ctrl.set_cart4_target_position(value)
                else:
                    self._ctrl.cart_target_positions[obj_id] = value

        elif kind == 'laser':
            self._ctrl.laser_sensor_states[obj_id] = value

        self._last_written[tag] = value


# =============================================================================
# I/O 总线
# =============================================================================

class IOBus:
    """统一 I/O 总线：切换驱动即可切换数据源"""

    def __init__(self, driver: IODriver = None):
        self._driver = driver
        self._cache: Dict[str, Any] = {}
        self._dirty: set = set()

    def set_driver(self, driver: IODriver):
        self._driver = driver

    def read(self, tag: str) -> Any:
        if not self._driver:
            return None
        value = self._driver.read(tag)
        self._cache[tag] = value
        return value

    def write(self, tag: str, value: Any):
        if not self._driver:
            return
        self._driver.write(tag, value)
        self._cache[tag] = value
        self._dirty.add(tag)

    def get_cached(self, tag: str) -> Any:
        return self._cache.get(tag)
