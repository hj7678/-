"""
控制策略数据生成器 - Control Strategy Data Generator
根据路线状态机生成传感器数据

功能：
1. 根据各路线状态生成接近开关数据
2. 根据各路线状态生成中转斗开关和称重数据
3. 生成料位传感器数据
4. 生成上料控制信号数据
5. 生成小车传感器数据

故障优先级：故障模拟 > 控制逻辑
"""

from typing import Dict, Any, List, Optional, Set
import random

import config
from controllers.route_state_manager import RouteState, get_route_state_manager, RouteStateManager
from sensor_data_manager import SensorDataManager, get_data_manager


class ControlStrategyGenerator:
    """
    控制策略数据生成器

    根据路线状态机生成传感器数据：
    1. 接近开关：根据路线状态确定（FEEDING=true, CLEARING脉冲, WAITING=false）
    2. 中转斗开关：根据路线状态确定（FEEDING=开, CLEARING=关, WAITING=关）
    3. 称重传感器：FEEDING=0, CLEARING=累计余料, WAITING=保持最终值
    4. 料位传感器：实时反映料仓料位百分比
    5. 上料控制信号：根据路线状态确定（FEEDING=true, 其他=false）
    6. 小车传感器：根据目标料仓确定位置和分料方向
    """

    # 满仓阈值（有中转斗）
    FULL_THRESHOLD_WITH_HOPPER = 95.0  # 95%
    # 满仓阈值（无中转斗）
    FULL_THRESHOLD_WITHOUT_HOPPER = 90.0  # 90%

    def __init__(self, data_manager: SensorDataManager = None):
        self.data_manager = data_manager or get_data_manager()
        self.route_state_manager = get_route_state_manager()

        # 料位传感器数据
        self.level_sensors: Dict[str, float] = {}

        # 故障覆盖数据（最高优先级）
        self.fault_overrides: Dict[str, Any] = {}

        # 小车传感器ID列表（供外部查询）
        self.cart_sensor_ids: List[str] = ['Cart1', 'Cart2', 'Cart3', 'Cart4']

        # 上次更新时间（秒），用于计算CLEARING状态的增量
        self.last_update_time: float = 0.0

        # 控制器引用（用于获取传感器位置）
        self.controller = None

        # 初始化料位传感器
        self._initialize_level_sensors()

    def set_controller(self, controller):
        """设置控制器引用，用于获取传感器位置"""
        self.controller = controller

    def _initialize_level_sensors(self):
        """初始化料位传感器数据"""
        # 高位配料站料仓
        col_names = ['P1', 'P2', 'P3', 'P4']
        for col in range(4):
            for row in range(1, 8):
                bin_id = f"{col_names[col]}-{row}"
                self.level_sensors[bin_id] = 85.0  # 默认85%

        # 高位储料仓
        for i in range(1, 13):
            bin_id = f"S{i}"
            self.level_sensors[bin_id] = 85.0  # 默认85%

    def set_level_sensor(self, bin_id: str, value: float):
        """设置料位传感器值"""
        if bin_id in self.level_sensors:
            self.level_sensors[bin_id] = max(0.0, min(100.0, value))

    def get_level_sensor(self, bin_id: str) -> float:
        """获取料位传感器值"""
        return self.level_sensors.get(bin_id, 0.0)

    def set_fault_override(self, sensor_id: str, value: Any):
        """设置故障覆盖值"""
        self.fault_overrides[sensor_id] = value

    def clear_fault_override(self, sensor_id: str):
        """清除故障覆盖值"""
        self.fault_overrides.pop(sensor_id, None)

    def clear_all_fault_overrides(self):
        """清除所有故障覆盖"""
        self.fault_overrides.clear()

    def generate_all_data(self,
                         active_routes: Set[str],
                         hoppers: Dict[str, Any],
                         conveyors: Dict[str, Any],
                         materials: List[Any],
                         cart_positions: Dict[str, int],
                         small_bins: Dict[str, Any] = None,
                         silo_compartments: Dict[str, Any] = None,
                         delta_seconds: float = 0.0):
        """
        生成所有传感器数据

        Args:
            active_routes: 活跃路线集合
            hoppers: 中转斗字典
            conveyors: 皮带字典
            materials: 物料列表
            cart_positions: 小车位置字典 {cart_id: position}
            small_bins: 小仓字典（用于更新料位）
            silo_compartments: 高位储料仓小仓字典（用于更新料位）
            delta_seconds: 时间增量（秒），用于计算CLEARING状态的增量
        """
        # 更新时间增量
        self.last_update_interval = delta_seconds

        # 更新料位传感器（如果有小仓数据）
        if small_bins:
            self._update_level_sensors_from_bins(small_bins)

        # 更新高位储料仓料位传感器
        if silo_compartments:
            self._update_level_sensors_from_silo(silo_compartments)

        # 生成接近开关数据
        self._generate_proximity_sensor_data(active_routes, conveyors, materials)

        # 生成中转斗数据
        self._generate_hopper_data(active_routes, hoppers, conveyors, materials)

        # 生成上料控制信号数据
        self._generate_feed_signals(active_routes)

        # 生成小车传感器数据
        self._generate_cart_sensor_data(active_routes, cart_positions)

        # 生成料位传感器数据
        self._generate_level_sensor_data()

        # 生成皮带转速传感器数据
        self._generate_conveyor_speed_data(active_routes, conveyors)

        # 更新路线状态机的余料总量
        self._update_route_residual_materials(active_routes, conveyors, materials)

    def _update_level_sensors_from_bins(self, small_bins: Dict[str, Any]):
        """从料仓数据更新料位传感器（使用百分比 0-100）"""
        for bin_id, bin_data in small_bins.items():
            # 使用料位百分比（0-100）
            if hasattr(bin_data, 'capacity') and hasattr(bin_data, 'current_level'):
                self.level_sensors[bin_id] = (bin_data.current_level / bin_data.capacity * 100) if bin_data.capacity > 0 else 0
            elif hasattr(bin_data, 'level_percent'):
                self.level_sensors[bin_id] = bin_data.level_percent
            elif isinstance(bin_data, dict) and 'current_level' in bin_data and 'capacity' in bin_data:
                self.level_sensors[bin_id] = (bin_data['current_level'] / bin_data['capacity'] * 100) if bin_data['capacity'] > 0 else 0

    def _update_level_sensors_from_silo(self, silo_compartments: Dict[str, Any]):
        """从高位储料仓数据更新料位传感器（使用百分比 0-100）"""
        for bin_id, compartment in silo_compartments.items():
            if isinstance(compartment, dict) and 'current_level' in compartment and 'capacity' in compartment:
                self.level_sensors[bin_id] = (compartment['current_level'] / compartment['capacity'] * 100) if compartment['capacity'] > 0 else 0
            elif hasattr(compartment, 'current_level') and hasattr(compartment, 'capacity'):
                self.level_sensors[bin_id] = (compartment.current_level / compartment.capacity * 100) if compartment.capacity > 0 else 0

    def _generate_proximity_sensor_data(self,
                                      active_routes: Set[str],
                                      conveyors: Dict[str, Any],
                                      materials: List[Any]):
        """生成接近开关传感器数据"""
        # 初始化所有传感器为False
        all_sensors = list(config.SENSORS.keys())
        sensor_values: Dict[str, bool] = {sid: False for sid in all_sensors}

        # 根据物料位置计算传感器状态
        for material in materials:
            if not material.is_active or not material.current_conveyor:
                continue

            conveyor_id = material.current_conveyor
            conveyor = conveyors.get(conveyor_id)
            if not conveyor or not conveyor.is_running:
                continue

            # 获取该皮带上的传感器
            for sensor_id, sensor_config in config.SENSORS.items():
                if sensor_config.get('conveyor') != conveyor_id:
                    continue

                # distance_from_start 是 0-1 的比例值，需要转换为像素距离
                sensor_distance_ratio = sensor_config.get('distance_from_start', 0)
                sensor_pixel_distance = conveyor.pixel_length * sensor_distance_ratio
                material_distance = getattr(material, 'distance_on_conveyor', 0)

                # 物料在传感器位置±10%皮带长度范围内触发（至少5像素误差范围）
                error_threshold = max(conveyor.pixel_length * 0.10, 5)
                if abs(material_distance - sensor_pixel_distance) < error_threshold:
                    sensor_values[sensor_id] = True

        # 根据路线状态调整传感器值
        for route_id in active_routes:
            ctx = self.route_state_manager.get_route_context(route_id)
            if not ctx:
                continue

            state = ctx.state
            route_sensors = RouteStateManager.ROUTE_PROXIMITY_SENSORS.get(route_id, [])

            if state == RouteState.FEEDING:
                # FEEDING状态：传感器状态由物料位置决定，不强制触发
                # 只在物料实际到达传感器位置时才触发（已在上面根据物料位置设置）
                pass

            elif state == RouteState.MOVING_TO_TARGET:
                # 小车移动中：无料，传感器全部为false
                for sensor_id in route_sensors:
                    sensor_values[sensor_id] = False

            elif state == RouteState.CLEARING:
                # 清空中，物料经过时true，通过后false
                # 已在上面根据物料位置设置，这里保持
                pass

            elif state == RouteState.WAITING:
                # 无料
                for sensor_id in route_sensors:
                    sensor_values[sensor_id] = False

            elif state == RouteState.IDLE:
                # 空闲
                for sensor_id in route_sensors:
                    sensor_values[sensor_id] = False

        # 应用故障覆盖（最高优先级）
        final_values = self._apply_fault_overrides(sensor_values)

        # 写入数据
        self.data_manager.write_all_sensors(final_values)

    def _generate_hopper_data(self,
                             active_routes: Set[str],
                             hoppers: Dict[str, Any],
                             conveyors: Dict[str, Any],
                             materials: List[Any]):
        """生成中转斗数据（开关和称重）"""
        if not hasattr(self, '_hopper_debug_counter'):
            self._hopper_debug_counter = 0
        self._hopper_debug_counter += 1

        # 每隔1秒打印一次详细日志（或者状态变化时）
        should_print = (self._hopper_debug_counter == 1 or
                       (hasattr(self, '_last_printed_state') and
                        self._last_printed_state != self._current_hopper_states_str(active_routes)))

        # 收集所有 hopper 的称重数据，最后批量写入
        hopper_weights: Dict[str, float] = {}
        hopper_switches: Dict[str, bool] = {}

        for hopper_id, hopper in hoppers.items():
            # 确定该中转斗属于哪条路线
            route_id = self._get_hopper_route(hopper_id, active_routes)

            if route_id:
                ctx = self.route_state_manager.get_route_context(route_id)
                state = ctx.state if ctx else RouteState.IDLE
            else:
                # 非活跃路线：中转斗保持开状态
                ctx = None
                state = None

            # 根据状态确定开关值
            if state == RouteState.MOVING_TO_TARGET:
                # 小车移动中（阶段一）：所有中转斗关闭
                switch_value = False
                weight_value = self._get_weight_for_moving_phase(ctx, hopper_id)
            elif state == RouteState.FEEDING:
                # 正常上料阶段（阶段二）：先判断余料，若有余料以0.2t/s释放
                switch_value = True
                weight_value = self._get_weight_for_feeding_phase(ctx, hopper_id)
            elif state == RouteState.CLEARING:
                # 清空余料阶段（阶段三）：关闭，余料进入从0累加
                switch_value = False
                weight_value = self._get_weight_for_clearing_phase(ctx, hopper_id, hopper, conveyors, route_id)
            elif state == RouteState.WAITING:
                # 上料完成阶段（阶段四）：关闭，保持最终值
                switch_value = False
                weight_value = self._get_weight_for_waiting_phase(ctx, hopper_id)
            elif state == RouteState.STANDBY:
                # 节能待机：关闭，保持最终称重值（与WAITING一致）
                switch_value = False
                weight_value = self._get_weight_for_waiting_phase(ctx, hopper_id)
            else:  # IDLE 或非活跃路线：初始状态为开
                switch_value = True
                weight_value = 0.0

            # [调试] HOPPER日志已注释
            # if should_print or self._hopper_debug_counter == 1:
            #     ctx_state = ctx.state.value if ctx else 'None'
            #     prev_state = getattr(ctx, 'previous_state', None) if ctx else None
            #     print(f"[HOPPER] t={self._hopper_debug_counter} hopper={hopper_id} route={route_id} "
            #           f"state={ctx_state} prev={prev_state} switch={switch_value} weight={weight_value:.4f}")

            # 传感器数据收集（统一通过 SensorDataManager 输出，不直接操作 hopper 对象）
            hopper_switches[hopper_id] = switch_value
            hopper_weights[hopper_id] = weight_value

        # 批量写入开关状态
        for hopper_id, switch_value in hopper_switches.items():
            self.data_manager.write_hopper_switch(hopper_id, switch_value)

        # 批量写入称重数据
        for hopper_id, weight_value in hopper_weights.items():
            self.data_manager.write_hopper_weight(hopper_id, weight_value)

        if should_print:
            self._last_printed_state = self._current_hopper_states_str(active_routes)

    def _current_hopper_states_str(self, active_routes: Set[str]) -> str:
        """生成当前所有中转斗状态的字符串表示（用于检测变化）"""
        parts = []
        for route_id in sorted(active_routes):
            ctx = self.route_state_manager.get_route_context(route_id)
            if ctx:
                parts.append(f"{route_id}:{ctx.state.value}")
        return "|".join(parts)

    def _get_weight_for_moving_phase(self, ctx, hopper_id: str) -> float:
        """阶段一：小车移动 - 称重保持不变"""
        if ctx:
            if hopper_id in ctx.pending_release_weights:
                return ctx.pending_release_weights[hopper_id]
            elif hopper_id in ctx.current_weights:
                return ctx.current_weights[hopper_id]
            elif hopper_id in ctx.final_weights:
                return ctx.final_weights[hopper_id]
        return 0.0

    def _get_weight_for_feeding_phase(self, ctx, hopper_id: str) -> float:
        """阶段二：正常上料 - 先判断余料，若有余料以0.2t/s释放"""
        if not ctx:
            return 0.0

        # 获取上一轮遗留的pending_release_weights（从WAITING/CLEARING阶段继承）
        pending_weight = ctx.pending_release_weights.get(hopper_id, 0.0)

        # 如果pending_release_weights为0，说明是新上料过程，没有余料
        if pending_weight > 0:
            # 有余料，逐渐释放
            decrement_per_sec = 0.2
            delta = min(decrement_per_sec * self.last_update_interval, pending_weight)
            new_pending = pending_weight - delta
            ctx.pending_release_weights[hopper_id] = new_pending
            # print(f"[HOPPER FEEDING] hopper={hopper_id} releasing residual: {pending_weight:.4f} -> {new_pending:.4f}")
            return max(0.0, new_pending)
        else:
            # 无余料，返回0（正常上料时称重显示为0）
            return 0.0

    def _get_weight_for_clearing_phase(self, ctx, hopper_id: str, hopper, conveyors, route_id: str) -> float:
        """阶段三：清空余料 - 关闭，余料进入从0累加"""
        if not ctx or not route_id:
            return 0.0

        route = config.FEED_ROUTES.get(route_id)
        if not route:
            return 0.0

        route_hoppers = route.get('hoppers', [])
        route_conveyors = route.get('conveyors', [])

        # 如果还没有计算过最终值，先计算并存储
        if hopper_id not in ctx.final_weights:
            final_weight = hopper.calculate_residual_weight(
                conveyors,
                route_hoppers,
                route_conveyors,
                route_id
            )
            ctx.final_weights[hopper_id] = final_weight
            ctx.current_weights[hopper_id] = 0.0
            # print(f"[HOPPER CLEARING] hopper={hopper_id} calculated final_weight={final_weight:.4f}")

        # 获取当前值和最终值
        final_weight = ctx.final_weights.get(hopper_id, 0.0)
        current_weight = ctx.current_weights.get(hopper_id, 0.0)

        if current_weight < final_weight:
            # 计算增量速度：每秒增加0.2吨
            increment_per_sec = 0.2
            delta = min(increment_per_sec * self.last_update_interval, final_weight - current_weight)
            weight_value = current_weight + delta
            ctx.current_weights[hopper_id] = weight_value
            # print(f"[HOPPER CLEARING] hopper={hopper_id} accumulating: {current_weight:.4f} -> {weight_value:.4f} (final={final_weight:.4f})")
            return weight_value
        else:
            return final_weight

    def _get_weight_for_waiting_phase(self, ctx, hopper_id: str) -> float:
        """阶段四：上料完成 - 关闭，保持最终值"""
        if ctx and hopper_id in ctx.final_weights:
            return ctx.final_weights[hopper_id]
        return 0.0

    def _get_hopper_route(self, hopper_id: str, active_routes: Set[str]) -> Optional[str]:
        """获取中转斗所属的活跃路线"""
        for route_id in active_routes:
            ctx = self.route_state_manager.get_route_context(route_id)
            if ctx and hopper_id in ctx.assigned_hoppers:
                return route_id
        return None

    def _calculate_residual_material(self,
                                    route_id: str,
                                    conveyors: Dict[str, Any],
                                    materials: List[Any]) -> float:
        """计算路线上所有中转斗的余料重量

        规则：
        - 对于每个中转斗，找到从上一个物料流出单元（上料点或中转斗）到当前中转斗的所有皮带
        - 皮带余料(吨) = 皮带总长度(米) / 皮带速度(米/秒) × 进料速率(吨/秒)
        - 称重值 = 余料重量（吨）= 物料数量 × 0.1t
        """
        if route_id not in config.FEED_ROUTES:
            return 0.0

        route = config.FEED_ROUTES[route_id]
        route_conveyors = route.get('conveyors', [])
        assigned_hoppers = route.get('hoppers', [])
        feed_point = route.get('feed_point')

        ctx = self.route_state_manager.get_route_context(route_id)
        if not ctx:
            return 0.0

        total_weight = 0.0

        # 遍历每个中转斗，计算其对应的余料重量
        prev_outlet = feed_point  # 上一个物料流出单元（初始为上料点）
        conveyor_count = len(route_conveyors)

        for i, hopper_id in enumerate(assigned_hoppers):
            if not hopper_id:
                continue

            # 获取当前中转斗的输入皮带
            hopper_config = config.TRANSFER_HOPPERS.get(hopper_id)
            if not hopper_config:
                continue

            input_conveyors = hopper_config.get('input_conveyor', [])
            if not isinstance(input_conveyors, list):
                input_conveyors = [input_conveyors] if input_conveyors else []

            # 计算从上一个流出单元到当前中转斗之间的皮带长度
            belt_length_sum = 0.0
            for conv_id in input_conveyors:
                conv = conveyors.get(conv_id)
                if conv and hasattr(conv, 'length'):
                    belt_length_sum += conv.length

            # 计算该段皮带的余料重量
            if belt_length_sum > 0:
                # 获取该段皮带的运行状态（使用第一个输入皮带的速度）
                if input_conveyors:
                    first_conv = conveyors.get(input_conveyors[0])
                    if first_conv and hasattr(first_conv, 'current_speed_pps') and first_conv.current_speed_pps > 0:
                        # 转换为米/秒
                        pixel_per_meter = first_conv.pixel_length / first_conv.length if first_conv.length > 0 else 1
                        belt_speed_mps = first_conv.current_speed_pps / pixel_per_meter
                        if belt_speed_mps > 0:
                            residual = (belt_length_sum / belt_speed_mps) * config.FEED_RATE
                            total_weight += residual

            # 更新上一个流出单元为当前中转斗
            prev_outlet = hopper_id

        return total_weight

    def _calculate_single_hopper_residual(self, route_id: str, hopper_id: str,
                                         prev_outlet, conveyors: Dict[str, Any]) -> float:
        """计算单个中转斗的余料重量

        Args:
            route_id: 路线ID
            hopper_id: 中转斗ID
            prev_outlet: 上一个物料流出单元（上料点ID或中转斗ID）
            conveyors: 皮带字典
        """
        if route_id not in config.FEED_ROUTES:
            return 0.0

        route = config.FEED_ROUTES[route_id]
        route_conveyors = route.get('conveyors', [])
        feed_point = route.get('feed_point')

        hopper_config = config.TRANSFER_HOPPERS.get(hopper_id)
        if not hopper_config:
            return 0.0

        # 获取当前中转斗的输入皮带
        input_conveyors = hopper_config.get('input_conveyor', [])
        if not isinstance(input_conveyors, list):
            input_conveyors = [input_conveyors] if input_conveyors else []

        # 确定上一个流出单元的类型和位置
        if prev_outlet == feed_point or prev_outlet is None:
            # 上一个流出单元是上料点，从路线起点开始计算
            start_idx = 0
        else:
            # 上一个流出单元是中转斗，找到它在线路中的位置
            prev_hoppers = route.get('hoppers', [])
            try:
                prev_idx = prev_hoppers.index(prev_outlet)
                # 从上一个中转斗的下一个皮带开始
                start_idx = prev_idx + 1
            except ValueError:
                start_idx = 0

        # 找到当前中转斗在线路中的位置
        hoppers = route.get('hoppers', [])
        try:
            curr_idx = hoppers.index(hopper_id)
        except ValueError:
            return 0.0

        # 获取当前中转斗输入皮带在线路中的位置
        # 输入皮带是 curr_idx 对应的皮带（在 conveyors 列表中）
        if curr_idx < len(route_conveyors):
            # 当前中转斗的输入皮带是 route_conveyors[curr_idx]
            input_conv_id = route_conveyors[curr_idx]
            input_conv = conveyors.get(input_conv_id)

            if input_conv and hasattr(input_conv, 'length') and hasattr(input_conv, 'current_speed_pps'):
                # 计算从 start_idx 到 curr_idx 的皮带总长度
                belt_length_sum = 0.0
                for j in range(start_idx, curr_idx + 1):
                    if j < len(route_conveyors):
                        conv = conveyors.get(route_conveyors[j])
                        if conv and hasattr(conv, 'length'):
                            belt_length_sum += conv.length

                if belt_length_sum > 0 and input_conv.current_speed_pps > 0:
                    pixel_per_meter = input_conv.pixel_length / input_conv.length if input_conv.length > 0 else 1
                    belt_speed_mps = input_conv.current_speed_pps / pixel_per_meter
                    if belt_speed_mps > 0:
                        return (belt_length_sum / belt_speed_mps) * config.FEED_RATE

        return 0.0

    def _get_hopper_position_in_route(self, route_id: str) -> int:
        """获取路线上最后一个中转斗在线路皮带列表中的位置索引"""
        ctx = self.route_state_manager.get_route_context(route_id)
        if not ctx or not ctx.assigned_hoppers:
            return None

        # 获取路线配置
        route = config.FEED_ROUTES.get(route_id)
        if not route:
            return None

        route_conveyors = route.get('conveyors', [])
        if not route_conveyors:
            return None

        # 获取最后一个中转斗的输出皮带
        last_hopper = ctx.assigned_hoppers[-1]
        hopper_config = config.TRANSFER_HOPPERS.get(last_hopper)
        if not hopper_config:
            return None

        output_conv = hopper_config.get('output_conveyor')
        if not output_conv:
            return None

        # 找到输出皮带在路线皮带列表中的位置
        if isinstance(output_conv, list):
            # 取第一个输出皮带的位置
            output_conv = output_conv[0]

        try:
            return route_conveyors.index(output_conv)
        except ValueError:
            return None

    def _generate_feed_signals(self, active_routes: Set[str]):
        """生成上料控制信号数据"""
        # 所有上料点初始化为false
        feed_signals = {
            'feed1_1': False,
            'feed1_2': False,
            'feed2_1': False,
            'feed2_2': False,
            'feed3': False,
            'silo_out': False,
        }

        for route_id in active_routes:
            ctx = self.route_state_manager.get_route_context(route_id)
            if not ctx:
                continue

            feed_point = ctx.feed_point
            if not feed_point:
                continue

            if ctx.state == RouteState.FEEDING:
                feed_signals[feed_point] = True
            elif ctx.state == RouteState.MOVING_TO_TARGET:
                # 小车移动中，上料信号为false
                feed_signals[feed_point] = False
            else:
                feed_signals[feed_point] = False

        # 写入上料控制信号
        self._write_feed_signals(feed_signals)

    def _write_feed_signals(self, feed_signals: Dict[str, bool]):
        """写入上料控制信号到数据管理器"""
        for feed_id, value in feed_signals.items():
            self.data_manager.write_feed_signal(feed_id, value)

    def _generate_cart_sensor_data(self,
                                  active_routes: Set[str],
                                  cart_positions: Dict[str, int]):
        """生成小车传感器数据（故障覆盖优先级最高）"""
        for route_id in active_routes:
            ctx = self.route_state_manager.get_route_context(route_id)
            if not ctx or not ctx.assigned_cart:
                continue

            cart_id = ctx.assigned_cart
            target_bin = ctx.target_bin

            if not target_bin:
                continue

            # 计算目标位置
            position = self._calculate_cart_position(cart_id, target_bin)

            # 计算分料传感器值
            left_divert, right_divert = self._calculate_cart_divert(cart_id, target_bin)

            # 极限传感器在整个上料过程中保持初始状态不变（始终为False）
            left_limit = False
            right_limit = False

            # ===== 故障覆盖：小车传感器（最高优先级） =====
            # 位置传感器故障
            pos_fault_key = f"{cart_id}_position_fault"
            if pos_fault_key in self.fault_overrides:
                fault_config = self.fault_overrides[pos_fault_key]
                fault_type = fault_config.get('type', '')
                if fault_type == 'position_stuck':
                    # 定位彻底失效：位置卡死不变，使用故障配置中的卡死值
                    stuck_value = fault_config.get('stuck_value', position)
                    position = stuck_value
                elif fault_type == 'position_inaccurate':
                    # 定位不准：在目标位置基础上随机偏移±2
                    offset = fault_config.get('offset', 2)
                    position = position + random.randint(-offset, offset)
                    position = max(1, min(7, position))  # 限制在有效范围

            # 左极限传感器故障
            left_limit_key = f"{cart_id}_left_limit"
            if left_limit_key in self.fault_overrides:
                left_limit = self.fault_overrides[left_limit_key]

            # 右极限传感器故障
            right_limit_key = f"{cart_id}_right_limit"
            if right_limit_key in self.fault_overrides:
                right_limit = self.fault_overrides[right_limit_key]

            # 左分料传感器故障
            left_divert_key = f"{cart_id}_left_divert"
            if left_divert_key in self.fault_overrides:
                left_divert = self.fault_overrides[left_divert_key]

            # 右分料传感器故障
            right_divert_key = f"{cart_id}_right_divert"
            if right_divert_key in self.fault_overrides:
                right_divert = self.fault_overrides[right_divert_key]

            # 写入小车传感器数据（故障覆盖后的最终值）
            self.data_manager.write_all_cart_sensors(
                cart_id=cart_id,
                position=position,
                left_limit=left_limit,
                right_limit=right_limit,
                left_divert=left_divert,
                right_divert=right_divert
            )

    def _calculate_cart_position(self, cart_id: str, target_bin: str) -> int:
        """计算小车传感器位置（等实际到达后才更新）"""
        # 获取控制器中的传感器位置
        if self.controller:
            if cart_id == 'Cart4':
                sensor_pos = getattr(self.controller, 'cart4_sensor_position', 1)
                return sensor_pos
            else:
                sensor_pos = self.controller.cart_sensor_positions.get(cart_id, 1)
                return sensor_pos

        # 如果没有控制器引用，使用目标位置（降级处理）
        if cart_id == 'Cart4':
            # 高位储料仓：S1/S7=位置1, S2/S8=位置2, ...
            if target_bin.startswith('S') and len(target_bin) <= 3:
                try:
                    num = int(target_bin[1:])
                    # S1-S6在左侧(左分料), S7-S12在右侧(右分料)
                    # 位置1-6对应S1/S7, S2/S8, ...
                    position = (num - 1) % 6 + 1
                    return position
                except ValueError:
                    return 1
        else:
            # 高位配料站：P1-5 -> 位置5, P2-3 -> 位置3, etc.
            if '-' in target_bin:
                parts = target_bin.split('-')
                if len(parts) == 2:
                    try:
                        return int(parts[1])
                    except ValueError:
                        return 1
        return 1

    def _calculate_cart_divert(self, cart_id: str, target_bin: str) -> tuple:
        """计算小车分料传感器值"""
        if cart_id == 'Cart1':
            # P1配料站位于小车左侧
            return (True, False)
        elif cart_id == 'Cart2':
            # 左侧为P2，右侧为P3
            if target_bin.startswith('P2'):
                return (True, False)
            elif target_bin.startswith('P3'):
                return (False, True)
            return (True, False)
        elif cart_id == 'Cart3':
            # P4配料站位于小车右侧
            return (False, True)
        elif cart_id == 'Cart4':
            # 左侧为S1-S6，右侧为S7-S12
            if target_bin.startswith('S'):
                try:
                    num = int(target_bin[1:])
                    if 1 <= num <= 6:
                        return (True, False)
                    elif 7 <= num <= 12:
                        return (False, True)
                except ValueError:
                    pass
            return (True, False)
        return (False, False)

    def _calculate_cart_limits(self, cart_id: str, position: int) -> tuple:
        """计算小车极限传感器值"""
        if cart_id == 'Cart4':
            max_pos = 6
        else:
            max_pos = 7

        left_limit = (position == 1)
        right_limit = (position == max_pos)
        return (left_limit, right_limit)

    def _generate_level_sensor_data(self):
        """生成料位传感器数据（百分比）"""
        for bin_id, level_percent in self.level_sensors.items():
            self.data_manager.write_level_sensor(bin_id, level_percent)

    def _generate_conveyor_speed_data(self, active_routes: Set[str], conveyors: Dict[str, Any]):
        """生成皮带转速传感器数据

        规则：
        - 皮带在活跃路线上运行时：正常转速 SPEED_NORMAL_VALUE (500)
        - 皮带停止时：转速为 0
        """
        for conv_id, conveyor in conveyors.items():
            # 检查皮带是否在活跃路线上
            is_on_active_route = False
            for route_id in active_routes:
                route = config.FEED_ROUTES.get(route_id)
                if route and conv_id in route.get('conveyors', []):
                    is_on_active_route = True
                    break

            # 获取该皮带的转速传感器ID
            speed_sensor_id = config.CONVEYOR_SPEED_SENSORS.get(conv_id)
            if not speed_sensor_id:
                continue

            # 根据皮带状态确定转速值
            if is_on_active_route and conveyor.is_running:
                speed = config.SPEED_NORMAL_VALUE
            else:
                speed = 0

            # 写入皮带转速数据
            self.data_manager.write_conveyor_speed(speed_sensor_id, speed)

    def _update_route_residual_materials(self,
                                       active_routes: Set[str],
                                       conveyors: Dict[str, Any],
                                       materials: List[Any]):
        """更新路线状态机的余料数据"""
        for route_id in active_routes:
            ctx = self.route_state_manager.get_route_context(route_id)
            if not ctx:
                continue

            route = config.FEED_ROUTES.get(route_id)
            if not route:
                continue

            route_conveyors = route.get('conveyors', [])

            # 计算每条皮带上余料量
            for conv_id in route_conveyors:
                conv_weight = 0.0
                for material in materials:
                    if (material.is_active and
                        material.current_conveyor == conv_id):
                        conv_weight += config.MATERIAL_WEIGHT
                self.route_state_manager.update_material_on_belt(route_id, conv_id, conv_weight)

    def _apply_fault_overrides(self, sensor_values: Dict[str, bool]) -> Dict[str, bool]:
        """应用故障覆盖值（最高优先级）"""
        result = sensor_values.copy()
        for sensor_id, value in self.fault_overrides.items():
            result[sensor_id] = value
        return result

    def get_level_sensors(self) -> Dict[str, float]:
        """获取所有料位传感器数据"""
        return self.level_sensors.copy()

    def get_feed_signals(self) -> Dict[str, bool]:
        """获取所有上料控制信号"""
        return self.data_manager.read_feed_signals()

    def get_route_states(self) -> Dict[str, str]:
        """获取所有路线状态"""
        return self.route_state_manager.get_all_route_states()


# 全局单例
_generator_instance: Optional['ControlStrategyGenerator'] = None


def get_control_strategy_generator(data_manager: SensorDataManager = None) -> ControlStrategyGenerator:
    """获取控制策略数据生成器单例"""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = ControlStrategyGenerator(data_manager)
    return _generator_instance


def reset_control_strategy_generator():
    """重置生成器单例"""
    global _generator_instance
    _generator_instance = None
