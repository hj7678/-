#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/influxdb_client.py — InfluxDB v2 客户端封装

传感器高频时序数据写入与查询。

写入模式: 批量异步写入（accumulate → flush），避免逐点 HTTP 开销。
查询模式: 同步查询最新值。

用法:
    from core.influxdb_client import InfluxDBClient

    client = InfluxDBClient.from_config(cfg)
    client.write_sensor("S-E1", "proximity", bool_value=True, unit="bool")
    client.write_sensor("S-CV-D7", "speed", int_value=500, unit="sint")
    client.flush()  # 批量提交

    latest = client.query_latest_sensors()  # → {sensor_id: {value, unit, time}}
"""

import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from influxdb_client import InfluxDBClient as _InfluxDB, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS, ASYNCHRONOUS, WriteOptions
    INFLUX_AVAILABLE = True
except ImportError:
    INFLUX_AVAILABLE = False
    _InfluxDB = None
    Point = None
    WritePrecision = None
    SYNCHRONOUS = None
    ASYNCHRONOUS = None
    WriteOptions = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class InfluxDBClient:
    """InfluxDB v2 时序数据客户端。

    Attributes:
        _batch: 待写入缓冲区 [(measurement, tags, fields, timestamp), ...]
        _lock: 线程安全锁
        _flush_interval: 自动刷新间隔（秒）
    """

    def __init__(
        self,
        url: str = "http://localhost:8086",
        token: str = "",
        org: str = "sany",
        bucket: str = "sensor_data",
        batch_size: int = 1000,
        flush_interval_sec: float = 1.0,
    ):
        if not INFLUX_AVAILABLE:
            raise ImportError("influxdb-client not installed. pip install influxdb-client")

        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.batch_size = batch_size
        self.flush_interval_sec = flush_interval_sec

        self._client = _InfluxDB(url=self.url, token=self.token, org=self.org)
        # 使用异步写入：write() 立即返回，由 InfluxDB 客户端后台线程批量提交，
        # 避免 SYNCHRONOUS 模式下 flush 阻塞调用线程（尤其是 sensor_data_receiver 高频路径）。
        self._write_api = self._client.write_api(write_options=WriteOptions(write_type=ASYNCHRONOUS))
        self._query_api = self._client.query_api()

        self._batch: List[Point] = []
        self._lock = threading.Lock()
        self._last_flush = time.time()
        self._running = True
        self._flush_timer: Optional[threading.Timer] = None
        self._write_errors = 0
        self._last_error_log = 0.0
        self._start_auto_flush()

    @classmethod
    def from_config(cls, cfg) -> "InfluxDBClient":
        """从 SystemConfig 创建客户端。"""
        db = getattr(cfg, "db", None)
        if db:
            return cls(
                url=f"http://{db.influxdb_host}:{db.influxdb_port}",
                token=getattr(db, "influxdb_token", ""),
                org="sany",
                bucket=getattr(db, "influxdb_db", "sensor_data"),
            )
        return cls()

    # ── 写入 ─────────────────────────────────────────────────

    def write_sensor(
        self,
        sensor_id: str,
        category: str,
        *,
        bool_value: Optional[bool] = None,
        float_value: Optional[float] = None,
        int_value: Optional[int] = None,
        unit: str = "",
        timestamp: Optional[str] = None,
    ):
        """写入单条传感器读数（累积到缓冲区，达到 batch_size 后自动 flush）。

        Args:
            sensor_id: 传感器 ID（如 "S-E1", "S-CV-D7", "Cart1"）
            category: 类别标签（proximity/speed/hopper_switch/hopper_weight/
                      cart_position/cart_limit/cart_divert/level/laser/feed_signal）
        """
        p = Point("sensor_data") \
            .tag("sensor_id", sensor_id) \
            .tag("category", category)

        if bool_value is not None:
            p = p.field("value_bool", bool_value)
        if float_value is not None:
            p = p.field("value_float", float_value)
        if int_value is not None:
            p = p.field("value_int", int_value)
        if unit:
            p = p.field("unit", unit)
        if timestamp:
            p = p.field("_ts", timestamp)

        with self._lock:
            self._batch.append(p)

        if len(self._batch) >= self.batch_size:
            self.flush()

    def write_batch(self, points: List[dict]):
        """批量写入传感器读数。

        Args:
            points: [{"sensor_id": str, "category": str, "bool_value": bool, ...}, ...]
        """
        ts = _now_iso()
        for pt in points:
            self.write_sensor(
                sensor_id=pt["sensor_id"],
                category=pt["category"],
                bool_value=pt.get("bool_value"),
                float_value=pt.get("float_value"),
                int_value=pt.get("int_value"),
                unit=pt.get("unit", ""),
                timestamp=pt.get("timestamp", ts),
            )

    def flush(self):
        """提交缓冲区数据到 InfluxDB（异步模式，非阻塞）。"""
        with self._lock:
            if not self._batch:
                # 仍触发底层 flush，确保异步队列中的数据被发送
                try:
                    self._write_api.flush()
                except Exception:
                    pass
                return
            batch = self._batch
            self._batch = []
        try:
            # ASYNCHRONOUS 模式下 write() 立即返回，不会阻塞当前线程
            self._write_api.write(bucket=self.bucket, record=batch)
        except Exception as e:
            # 异步模式下此处通常只捕获参数/序列化错误；网络错误由后台线程处理
            print(f"[InfluxDB] async write enqueue failed ({len(batch)} pts dropped): {e}", flush=True)
            self._write_errors += 1

    # ── 查询 ─────────────────────────────────────────────────

    def query_latest_sensors(self, lookback_sec: float = 1.0) -> Dict[str, dict]:
        """查询所有传感器的最新值（过去 lookback_sec 秒内）。

        Returns:
            {sensor_id: {"category": str, "value": Any, "unit": str, "time": str}}
        """
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{lookback_sec}s)
          |> filter(fn: (r) => r["_measurement"] == "sensor_data")
          |> last()
        '''
        try:
            tables = self._query_api.query(query=query, org=self.org)
        except Exception:
            return {}

        result: Dict[str, dict] = {}
        for table in tables:
            for record in table.records:
                sid = record.values.get("sensor_id", "")
                cat = record.values.get("category", "")
                field = record.get_field()
                val = record.get_value()
                t = record.get_time()

                if sid not in result:
                    result[sid] = {"category": cat, "time": str(t) if t else ""}
                result[sid][field] = val
        return result

    def query_latest_by_category(self, category: str, lookback_sec: float = 1.0) -> Dict[str, dict]:
        """查询指定类别传感器的最新值。

        Returns:
            {sensor_id: {"value": Any, "unit": str, "time": str}}
        """
        query = f'''
        from(bucket: "{self.bucket}")
          |> range(start: -{lookback_sec}s)
          |> filter(fn: (r) => r["_measurement"] == "sensor_data"
                         and r["category"] == "{category}")
          |> last()
        '''
        try:
            tables = self._query_api.query(query=query, org=self.org)
        except Exception:
            return {}

        result: Dict[str, dict] = {}
        for table in tables:
            for record in table.records:
                sid = record.values.get("sensor_id", "")
                field = record.get_field()
                val = record.get_value()
                t = record.get_time()

                if sid not in result:
                    result[sid] = {"category": category, "time": str(t) if t else ""}
                result[sid][field] = val
        return result

    # ── 生命周期 ─────────────────────────────────────────────

    def _start_auto_flush(self):
        """启动定时自动刷新。"""
        def _tick():
            if self._running:
                self.flush()
                self._flush_timer = threading.Timer(self.flush_interval_sec, _tick)
                self._flush_timer.daemon = True
                self._flush_timer.start()

        self._flush_timer = threading.Timer(self.flush_interval_sec, _tick)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def close(self):
        """关闭客户端，flush 剩余数据。"""
        self._running = False
        if self._flush_timer:
            self._flush_timer.cancel()
        self.flush()
        self._client.close()
