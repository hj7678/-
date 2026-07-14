"""
TCP 数据 → SystemSnapshot 适配器

将上位机发来的 JSON 传感器数据（与 generate_data.json 同格式）转换为诊断引擎标准输入。
"""
import time
from typing import Dict, List, Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tcp_diagnosis.diagnosis_types import (
    RouteState,
    ProximitySensorSnapshot,
    HopperSnapshot,
    ConveyorSnapshot,
    CartSnapshot,
    RouteSnapshot,
    SystemSnapshot,
)
from tcp_diagnosis.config import (
    FEED_ROUTES,
    FEED_SIGNAL_TO_ROUTES,
    TRANSFER_HOPPER_IO,
    SPEED_SENSOR_TO_CONVEYOR,
)

# 接近开关 → 所属皮带（从 pos.py SENSORS 提取）
SENSOR_TO_CONVEYOR = {
    'S-E1': 'E1', 'S-E2': 'E2', 'S-E4': 'E4', 'S-E5': 'E5',
    'S-E6': 'E6', 'S-E7': 'E7', 'S-E8': 'E8', 'S-E9': 'E9', 'S-E10': 'E10',
    'S-D1': 'D1', 'S-D2': 'D2', 'S-D2-2': 'D2',
    'S-D3': 'D3', 'S-D4': 'D4', 'S-D5': 'D5',
    'S-D6': 'D6', 'S-D7': 'D7', 'S-D8': 'D8', 'S-D9': 'D9', 'S-D13': 'D13',
}


def _val(v, default=None):
    """兼容两种格式：裸值(bool/int/float) 或 {'value': ...} 包装"""
    if isinstance(v, dict):
        return v.get('value', default)
    return v if v is not None else default


class TcpDataAdapter:
    """将上位机 JSON 数据转换为 SystemSnapshot"""

    def build_snapshot(self, data: dict) -> SystemSnapshot:
        ts = self._parse_timestamp(data.get('timestamp', ''))
        conveyor_states = self._parse_conveyor_states(data.get('conveyor_sensors', {}))
        route_states_raw: Dict[str, str] = data.get('route_states', {})
        active_route_ids = self._infer_active_routes(data.get('feed_signals', {}), route_states_raw)

        routes: Dict[str, RouteSnapshot] = {}
        early_moved = data.get('early_moved_routes', {})
        for route_id, route_cfg in FEED_ROUTES.items():
            state = self._resolve_route_state(
                route_id, route_cfg, route_states_raw,
                active_route_ids, conveyor_states,
            )

            routes[route_id] = RouteSnapshot(
                route_id=route_id,
                state=state,
                conveyor_ids=list(route_cfg['conveyors']),
                hopper_ids=[h for h in route_cfg.get('hoppers', []) if h],
                proximity_sensor_ids=list(route_cfg.get('proximity_sensors', [])),
                feed_point=route_cfg.get('feed_point', ''),
                cart_target_position=route_cfg.get('cart_target_position', 0),
                early_moved_from_clearing=early_moved.get(route_id, False),
            )

        proximity_sensors: Dict[str, ProximitySensorSnapshot] = {}
        for sid, sdata in data.get('sensors', {}).items():
            proximity_sensors[sid] = ProximitySensorSnapshot(
                sensor_id=sid,
                state=bool(_val(sdata, False)),
                conveyor_id=SENSOR_TO_CONVEYOR.get(sid, sid),
            )

        hopper_snapshots: Dict[str, HopperSnapshot] = {}
        for hid, hdata in data.get('hoppers', {}).items():
            io = TRANSFER_HOPPER_IO.get(hid, {})
            switch_val = hdata.get('switch', {})
            weight_val = hdata.get('weight', {})
            hopper_snapshots[hid] = HopperSnapshot(
                hopper_id=hid,
                switch_open=bool(_val(switch_val, True)),
                weight=float(_val(weight_val, 0)),
                input_conveyor_ids=io.get('input', []),
                output_conveyor_ids=io.get('output', []),
            )

        conveyor_snapshots: Dict[str, ConveyorSnapshot] = {}
        speed_data = data.get('conveyor_sensors', {})
        for cid in conveyor_states.keys():
            speed_sid = self._conv_to_speed_sid(cid)
            speed = 0
            if speed_sid and speed_sid in speed_data:
                speed = int(_val(speed_data[speed_sid], 0))
            conveyor_snapshots[cid] = ConveyorSnapshot(
                conveyor_id=cid,
                is_running=conveyor_states.get(cid, False),
                speed=speed,
            )

        cart_snapshots: Dict[str, CartSnapshot] = {}
        for cart_id in ['Cart1', 'Cart2', 'Cart3', 'Cart4']:
            cart = data.get('cart_sensors', {}).get(cart_id, {})
            cart_snapshots[cart_id] = CartSnapshot(
                cart_id=cart_id,
                position=int(_val(cart.get('position', {}), 1)),
                left_limit=bool(_val(cart.get('left_limit', {}), False)),
                right_limit=bool(_val(cart.get('right_limit', {}), False)),
                left_divert=bool(_val(cart.get('left_divert', {}), False)),
                right_divert=bool(_val(cart.get('right_divert', {}), False)),
            )

        snapshot = SystemSnapshot(
            timestamp=ts,
            active_route_ids=active_route_ids,
            routes=routes,
            proximity_sensors=proximity_sensors,
            hoppers=hopper_snapshots,
            conveyors=conveyor_snapshots,
            carts=cart_snapshots,
        )
        snapshot.clearing_strategies = data.get('clearing_strategies', {})
        return snapshot

    def _parse_timestamp(self, ts_str: str) -> float:
        """解析时间戳字符串为 float（秒），失败则用当前时间"""
        if not ts_str:
            return time.time()
        try:
            import datetime
            dt = datetime.datetime.strptime(ts_str[:19], '%Y-%m-%d %H:%M:%S')
            return dt.timestamp()
        except (ValueError, IndexError):
            return time.time()

    def _parse_conveyor_states(self, converter_data: dict) -> Dict[str, bool]:
        """从转速传感器数据推断皮带运行状态"""
        states: Dict[str, bool] = {}
        for speed_sid, sdata in converter_data.items():
            cid = SPEED_SENSOR_TO_CONVEYOR.get(speed_sid)
            if cid:
                speed = int(_val(sdata, 0))
                states[cid] = speed > 0
        # 确保所有已知皮带都有状态
        for route_cfg in FEED_ROUTES.values():
            for cid in route_cfg['conveyors']:
                if cid not in states:
                    states[cid] = False
        return states

    def _infer_active_routes(self, feed_signals: dict, route_states: dict) -> List[str]:
        """从上料信号+路线状态推断活跃路线"""
        active: List[str] = []
        for signal_id, sdata in feed_signals.items():
            if _val(sdata, False):
                route_ids = FEED_SIGNAL_TO_ROUTES.get(signal_id, [])
                active.extend(route_ids)
        # 从route_states中补充(feed_signals为空时用状态推断)
        for route_id, state in route_states.items():
            if state and state not in ('idle', '') and route_id not in active:
                active.append(route_id)
        return list(dict.fromkeys(active))

    @staticmethod
    def _resolve_route_state(route_id: str, route_cfg: dict,
                             route_states_raw: Dict[str, str],
                             active_route_ids: List[str],
                             conveyor_states: Dict[str, bool]) -> RouteState:
        # 优先使用下位机发送的真实路线状态
        raw = route_states_raw.get(route_id, '')
        if raw:
            # 显式匹配确保正确解析
            if raw == 'moving_to_target':
                return RouteState.MOVING_TO_TARGET
            if raw == 'feeding':
                return RouteState.FEEDING
            try:
                return RouteState(raw)
            except ValueError:
                pass

        # 回退：从数据推断
        is_active = route_id in active_route_ids
        all_running = all(conveyor_states.get(cid, False) for cid in route_cfg['conveyors'])
        all_stopped = all(not conveyor_states.get(cid, True) for cid in route_cfg['conveyors'])

        if is_active and all_running:
            return RouteState.FEEDING
        elif not is_active and all_stopped:
            return RouteState.IDLE
        elif not is_active and any(conveyor_states.get(cid, False) for cid in route_cfg['conveyors']):
            return RouteState.CLEARING
        return RouteState.IDLE

    @staticmethod
    def _conv_to_speed_sid(conv_id: str) -> Optional[str]:
        """皮带 ID → 转速传感器 ID"""
        from tcp_diagnosis.config import CONVEYOR_TO_SPEED_SENSOR
        return CONVEYOR_TO_SPEED_SENSOR.get(conv_id)
