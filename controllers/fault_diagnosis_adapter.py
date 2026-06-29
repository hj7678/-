"""
Simulation to diagnosis engine adapter.

Converts simulation-internal objects (Sensor, TransferHopper, Conveyor) into
the diagnosis engine's standard input format (SystemSnapshot), enabling zero-coupling bridging.
"""

from typing import Dict, List, Any, Optional, TYPE_CHECKING
import config
from tcp_diagnosis.diagnosis_types import (
    RouteState,
    ProximitySensorSnapshot,
    HopperSnapshot,
    ConveyorSnapshot,
    CartSnapshot,
    RouteSnapshot,
    SystemSnapshot,
    DiagnosisResult,
)
from tcp_diagnosis.engine import DiagnosisEngine

if TYPE_CHECKING:
    from controllers.simulation_controller import Sensor, TransferHopper, Conveyor


_ROUTE_STATE_MAP = {
    'idle': RouteState.IDLE,
    'moving_to_target': RouteState.MOVING_TO_TARGET,
    'feeding': RouteState.FEEDING,
    'clearing': RouteState.CLEARING,
    'waiting': RouteState.WAITING,
}


def _map_route_state(sim_state) -> RouteState:
    if hasattr(sim_state, 'value'):
        return _ROUTE_STATE_MAP.get(sim_state.value, RouteState.IDLE)
    return _ROUTE_STATE_MAP.get(str(sim_state), RouteState.IDLE)


class FaultDiagnosisAdapter:
    def __init__(self, engine: Optional[DiagnosisEngine] = None):
        self.engine = engine or DiagnosisEngine()

    def build_snapshot(
        self,
        sensors: Dict[str, 'Sensor'],
        hoppers: Dict[str, 'TransferHopper'],
        conveyors: Dict[str, 'Conveyor'],
        active_routes: set,
        route_state_manager,
        cart_data: Dict[str, Dict[str, Any]],
        speed_data: Dict[str, int],
        total_runtime: float,
    ) -> SystemSnapshot:
        active_route_list = list(active_routes) if active_routes else []

        routes: Dict[str, RouteSnapshot] = {}
        for route_id, route_cfg in config.FEED_ROUTES.items():
            ctx = route_state_manager.get_route_context(route_id)
            sim_state = ctx.state if ctx else 'idle'
            state = _map_route_state(sim_state)

            prox_ids = []
            for conv_id in route_cfg['conveyors']:
                for sid, s in sensors.items():
                    if s.conveyor == conv_id:
                        prox_ids.append(sid)

            strategy = getattr(ctx, 'clearing_strategy', 'reverse')
            feed_point = route_cfg.get('feed_point', '')
            cart_target = getattr(ctx, 'cart_target_position', 0) if ctx else 0
            early_moved = getattr(ctx, 'early_moved_from_clearing', False) if ctx else False
            routes[route_id] = RouteSnapshot(
                route_id=route_id,
                state=state,
                conveyor_ids=list(route_cfg['conveyors']),
                hopper_ids=[h for h in route_cfg.get('hoppers', []) if h],
                proximity_sensor_ids=prox_ids,
                clearing_strategy=strategy,
                feed_point=feed_point,
                cart_target_position=cart_target,
                early_moved_from_clearing=early_moved,
            )

        proximity_sensors: Dict[str, ProximitySensorSnapshot] = {}
        for sid, sensor in sensors.items():
            proximity_sensors[sid] = ProximitySensorSnapshot(
                sensor_id=sid,
                state=sensor.is_active,
                conveyor_id=sensor.conveyor,
            )

        hopper_snapshots: Dict[str, HopperSnapshot] = {}
        for hid, hopper in hoppers.items():
            hopper_config = config.TRANSFER_HOPPERS.get(hid, {})
            input_cons = hopper_config.get('input_conveyor', [])
            if not isinstance(input_cons, list):
                input_cons = [input_cons]
            output_cons = hopper_config.get('output_conveyor', [])
            if not isinstance(output_cons, list):
                output_cons = [output_cons]
            hopper_snapshots[hid] = HopperSnapshot(
                hopper_id=hid,
                switch_open=hopper.get_effective_switch_state(),
                weight=hopper.get_display_weight(),
                input_conveyor_ids=input_cons,
                output_conveyor_ids=output_cons,
            )

        conveyor_snapshots: Dict[str, ConveyorSnapshot] = {}
        for cid, conv in conveyors.items():
            speed = 0
            speed_sid = config.CONVEYOR_SPEED_SENSORS.get(cid)
            if speed_sid:
                speed = speed_data.get(speed_sid, 0)
            conveyor_snapshots[cid] = ConveyorSnapshot(
                conveyor_id=cid,
                is_running=conv.is_running,
                speed=speed,
            )

        cart_snapshots: Dict[str, CartSnapshot] = {}
        for cart_id in ['Cart1', 'Cart2', 'Cart3', 'Cart4']:
            cart = cart_data.get(cart_id, {})
            cart_snapshots[cart_id] = CartSnapshot(
                cart_id=cart_id,
                position=cart.get('position', 1),
                left_limit=cart.get('left_limit', False),
                right_limit=cart.get('right_limit', False),
                left_divert=cart.get('left_divert', False),
                right_divert=cart.get('right_divert', False),
            )

        return SystemSnapshot(
            timestamp=total_runtime,
            active_route_ids=active_route_list,
            routes=routes,
            proximity_sensors=proximity_sensors,
            hoppers=hopper_snapshots,
            conveyors=conveyor_snapshots,
            carts=cart_snapshots,
        )

    def run_diagnosis(
        self,
        sensors: Dict[str, 'Sensor'],
        hoppers: Dict[str, 'TransferHopper'],
        conveyors: Dict[str, 'Conveyor'],
        active_routes: set,
        route_state_manager,
        cart_data: Dict[str, Dict[str, Any]],
        speed_data: Dict[str, int],
        total_runtime: float,
    ) -> List[DiagnosisResult]:
        snapshot = self.build_snapshot(
            sensors, hoppers, conveyors,
            active_routes, route_state_manager,
            cart_data, speed_data, total_runtime,
        )
        return self.engine.diagnose(snapshot)
