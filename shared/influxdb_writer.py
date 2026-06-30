"""
influxdb_writer.py — 独立守护线程，定时从仿真控制器读取传感器快照写入 InfluxDB

与 FeedingMaster 桥接解耦，即使桥接断开也能持续记录。

用法:
    from shared.influxdb_writer import InfluxDBWriter
    writer = InfluxDBWriter(controller, interval_sec=0.5)
    writer.start()
    ...
    writer.stop()
"""

import threading
import time
from typing import Optional

from shared.influxdb_client import InfluxDBClient as _InfluxDB, INFLUX_AVAILABLE


class InfluxDBWriter:
    """独立守护线程：定时读取传感器快照 → InfluxDB"""

    def __init__(
        self,
        controller,
        *,
        url: str = "http://localhost:8086",
        token: str = "",
        org: str = "sany",
        bucket: str = "sensor_data",
        interval_sec: float = 0.5,
    ):
        self._ctrl = controller
        self._interval = interval_sec
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._client: Optional[_InfluxDB] = None

        if INFLUX_AVAILABLE:
            self._client = _InfluxDB(
                url=url, token=token, org=org, bucket=bucket,
                batch_size=500, flush_interval_sec=1.0,
            )
        else:
            print("[InfluxDB] influxdb-client 未安装，数据写入已禁用", flush=True)

    @classmethod
    def from_config(cls, controller, cfg) -> "InfluxDBWriter":
        """从配置创建。config.json 中 influxdb 段:
        {
            "influxdb": {
                "enabled": true,
                "host": "localhost",
                "port": 8086,
                "token": "",
                "org": "sany",
                "bucket": "sensor_data",
                "interval_sec": 0.5
            }
        }
        """
        db = cfg.get("influxdb", {})
        if not db.get("enabled", False):
            return cls(controller, interval_sec=0)  # disabled
        return cls(
            controller,
            url=f"http://{db.get('host', 'localhost')}:{db.get('port', 8086)}",
            token=db.get("token", ""),
            org=db.get("org", "sany"),
            bucket=db.get("bucket", "sensor_data"),
            interval_sec=db.get("interval_sec", 0.5),
        )

    @property
    def enabled(self) -> bool:
        return self._client is not None and self._interval > 0

    def start(self):
        if not self.enabled:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="influxdb-writer")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._client:
            self._client.close()

    def _loop(self):
        while self._running:
            try:
                self._write_snapshot()
            except Exception as e:
                print(f"[InfluxDB] 写入失败: {e}", flush=True)
            time.sleep(self._interval)

    def _write_snapshot(self):
        ctrl = self._ctrl
        if not ctrl or not self._client:
            return

        batch = []

        # 接近开关传感器
        for sid, sensor in ctrl.sensors.items():
            batch.append({"sensor_id": sid, "category": "proximity", "bool_value": sensor.is_active})

        # 中转斗状态
        for hid, hopper in ctrl.hoppers.items():
            batch.append({"sensor_id": hid, "category": "hopper_switch", "bool_value": hopper.is_open})
            batch.append({"sensor_id": hid, "category": "hopper_weight", "float_value": hopper.get_display_weight()})

        # 皮带状态
        for cid, conv in ctrl.conveyors.items():
            batch.append({"sensor_id": cid, "category": "belt_state", "bool_value": conv.is_running})
            batch.append({"sensor_id": cid, "category": "belt_speed", "float_value": conv.current_speed})

        # 小车位置
        for cart_id in ('Cart1', 'Cart2', 'Cart3'):
            pos = ctrl.cart_positions.get(cart_id, 1)
            batch.append({"sensor_id": cart_id, "category": "cart_position", "int_value": pos})
        batch.append({"sensor_id": "Cart4", "category": "cart_position", "int_value": ctrl.cart4_position})

        # 小车移动状态
        batch.append({"sensor_id": "Cart1", "category": "cart_moving", "bool_value": getattr(ctrl, '_cart1_is_moving', False)})
        batch.append({"sensor_id": "Cart2", "category": "cart_moving", "bool_value": getattr(ctrl, '_cart2_is_moving', False)})
        batch.append({"sensor_id": "Cart3", "category": "cart_moving", "bool_value": getattr(ctrl, '_cart3_is_moving', False)})
        batch.append({"sensor_id": "Cart4", "category": "cart_moving", "bool_value": ctrl.cart4_is_moving})

        # 小车分料
        for cart_id in ('Cart1', 'Cart2', 'Cart3', 'Cart4'):
            divert = ctrl.cart_divert.get(cart_id, (True, False))
            batch.append({"sensor_id": cart_id, "category": "cart_divert", "int_value": divert[0] if divert else 0})

        # 料仓料位
        for bid, sb in ctrl.small_bins.items():
            batch.append({"sensor_id": bid, "category": "bin_level", "float_value": sb.current_level})

        # 路线状态
        for rid, ctx in ctrl.route_state_manager.routes.items():
            batch.append({"sensor_id": rid, "category": "route_state", "int_value": _route_state_int(ctx.state)})

        # 活跃路线
        for rid in ctrl.active_routes:
            batch.append({"sensor_id": rid, "category": "route_active", "bool_value": True})

        self._client.write_batch(batch)


def _route_state_int(state) -> int:
    """路线状态 → 整数编码"""
    mapping = {"idle": 0, "feeding": 1, "clearing": 2, "waiting": 3, "standby": 4, "moving_to_target": 5}
    return mapping.get(state.value if hasattr(state, 'value') else str(state), 0)