"""
配置加载器 — 外部 JSON 配置 + 代码默认值合并

加载顺序: pos.py 默认值 → config.json 覆盖 → 程序使用

用法:
    loader = ConfigLoader()
    loader.load('config.json')  # 可选，不传则只用默认值
    conveyors = loader.get_conveyors()
    sensors = loader.get_sensors()
"""

import json
import os
from typing import Any, Dict


class ConfigLoader:
    """统一配置加载器"""

    def __init__(self):
        self._overrides: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------

    def load(self, filepath: str = None) -> bool:
        """加载外部 JSON 配置文件，合并到默认值上"""
        if filepath is None:
            filepath = os.path.join(os.path.dirname(__file__), 'config.json')
        if not os.path.exists(filepath):
            print(f"[Config] 配置文件不存在: {filepath}，使用默认值")
            return False
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self._overrides = json.load(f)
            print(f"[Config] 已加载外部配置: {filepath}")
            return True
        except Exception as e:
            print(f"[Config] 加载失败: {e}，使用默认值")
            return False

    # ------------------------------------------------------------------
    # 皮带配置
    # ------------------------------------------------------------------

    def get_conveyors(self) -> dict:
        """获取皮带配置（默认值 + 覆盖）"""
        import pos
        result = {}
        for cid, c in pos.CONVEYORS.items():
            entry = dict(c)
            # 应用用户覆盖
            override = self._overrides.get('conveyors', {}).get(cid, {})
            for key in ('length', 'x1', 'y1', 'x2', 'y2'):
                if key in override:
                    entry[key] = override[key]
            result[cid] = entry
        return result

    # ------------------------------------------------------------------
    # 传感器配置
    # ------------------------------------------------------------------

    def get_sensors(self) -> dict:
        """获取传感器配置"""
        import pos
        result = {}
        for sid, s in pos.SENSORS.items():
            entry = dict(s)
            override = self._overrides.get('sensors', {}).get(sid, {})
            if 'distance_from_start' in override:
                entry['distance_from_start'] = override['distance_from_start']
            if 'x' in override:
                entry['x'] = override['x']
            if 'y' in override:
                entry['y'] = override['y']
            result[sid] = entry
        return result

    # ------------------------------------------------------------------
    # 中转斗配置
    # ------------------------------------------------------------------

    def get_hoppers(self) -> dict:
        """获取中转斗配置"""
        import pos
        result = {}
        for hid, h in pos.TRANSFER_HOPPERS.items():
            entry = dict(h)
            override = self._overrides.get('hoppers', {}).get(hid, {})
            for key in ('x', 'y', 'width', 'height'):
                if key in override:
                    entry[key] = override[key]
            result[hid] = entry
        return result

    # ------------------------------------------------------------------
    # 仿真参数
    # ------------------------------------------------------------------

    def get_simulation_params(self) -> dict:
        """获取仿真参数"""
        import config as cfg
        defaults = {
            'belt_speed': cfg.DEFAULT_SPEED,
            'min_speed': cfg.MIN_SPEED,
            'max_speed': cfg.MAX_SPEED,
            'material_weight': cfg.MATERIAL_WEIGHT,
            'feed_rate': cfg.FEED_RATE,
            'hopper_capacity_tons': 8.5,
            'cart_move_interval': 18.0,
            'clearing_tolerance': 2.0,
            'sensor_off_delay': cfg.SENSOR_OFF_DELAY,
        }
        override = self._overrides.get('simulation', {})
        defaults.update(override)
        return defaults

    # ------------------------------------------------------------------
    # 调度参数
    # ------------------------------------------------------------------

    def get_scheduling_params(self) -> dict:
        """获取调度参数"""
        defaults = {
            'emergency_threshold_tons': 11.0,     # < 10% = 11t
            'idle_threshold_tons': 70.0,          # D7/D8/D9 < 70t
            'd6_idle_threshold_tons': 336.0,      # D6 < 80% of 420t
            'pre_emptive_level_pct': 80.0,        # 预请求阈值
            'cooldown_seconds': 120.0,            # 冷却时间
            'scheduling_host': '127.0.0.1',
            'scheduling_ports': {'D7': 8891, 'D8': 8892, 'D9': 8893, 'D6': 8894},
        }
        override = self._overrides.get('scheduling', {})
        defaults.update(override)
        return defaults

    # ------------------------------------------------------------------
    # I/O 模式
    # ------------------------------------------------------------------

    def get_io_mode(self) -> str:
        """获取 I/O 模式: 'simulation' 或 'modbus'"""
        return self._overrides.get('io_mode', 'simulation')

    def get_modbus_params(self) -> dict:
        """获取 Modbus 连接参数"""
        defaults = {'host': '127.0.0.1', 'port': 502}
        defaults.update(self._overrides.get('modbus', {}))
        return defaults

    # ------------------------------------------------------------------
    # 清空传感器超时覆盖
    # ------------------------------------------------------------------

    def get_clearing_timeouts(self) -> dict:
        """获取清空传感器超时覆盖（格式: {(route_id, sensor_id): seconds}）"""
        raw = self._overrides.get('clearing_timeouts', {})
        result = {}
        for key, val in raw.items():
            # key: "route1:S-E4" → ('route1', 'S-E4')
            parts = key.split(':')
            if len(parts) == 2:
                result[(parts[0], parts[1])] = float(val)
        return result


# 全局单例
_loader: ConfigLoader = None


def get_config_loader() -> ConfigLoader:
    global _loader
    if _loader is None:
        _loader = ConfigLoader()
    return _loader
