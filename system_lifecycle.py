"""
系统生命周期管理器 — 工业级启停状态机

状态: SELF_TEST → STANDBY → RUNNING ⇄ PAUSED → STOPPING → STANDBY → SHUTDOWN
                                           ↘ EMERGENCY (急停)

自检项:
  - IO总线连通性
  - 传感器初始状态（接近开关应常开false、激光传感器应常开true有料）
  - 小车位置有效范围
  - 调度服务连通性（可选）
"""

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional


class LifecycleState(Enum):
    UNINITIALIZED = "uninitialized"
    SELF_TEST = "self_test"
    STANDBY = "standby"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    EMERGENCY = "emergency"
    SHUTDOWN = "shutdown"


@dataclass
class SelfTestResult:
    passed: bool = True
    items: List[dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class SystemLifecycle:
    """系统生命周期管理器"""

    def __init__(self):
        self._state = LifecycleState.UNINITIALIZED
        self._state_history: List[LifecycleState] = []
        self._callbacks: Dict[str, Callable] = {}
        self._state_file = os.path.join(os.path.dirname(__file__),
                                         'data', 'system_state.json')

    # ------------------------------------------------------------------
    # 状态属性
    # ------------------------------------------------------------------

    @property
    def state(self) -> LifecycleState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == LifecycleState.RUNNING

    @property
    def is_operational(self) -> bool:
        return self._state in (LifecycleState.RUNNING, LifecycleState.PAUSED,
                               LifecycleState.STOPPING)

    # ------------------------------------------------------------------
    # 回调注册
    # ------------------------------------------------------------------

    def on(self, event: str, callback: Callable):
        """注册生命周期事件回调"""
        self._callbacks[event] = callback

    def _emit(self, event: str, *args):
        cb = self._callbacks.get(event)
        if cb:
            cb(*args)

    def _transition(self, new_state: LifecycleState):
        old = self._state
        self._state = new_state
        self._state_history.append(new_state)
        print(f"[生命周期] {old.value} → {new_state.value}", flush=True)
        self._emit('state_changed', old, new_state)

    # ------------------------------------------------------------------
    # 阶段1: 自检
    # ------------------------------------------------------------------

    def self_test(self, io_bus=None, controller=None,
                  check_scheduling: bool = False) -> SelfTestResult:
        """启动自检：验证所有硬件/传感器处于预期初始状态"""
        self._transition(LifecycleState.SELF_TEST)
        result = SelfTestResult()

        # === IO总线连通性 ===
        result.items.append({'item': 'IO总线', 'status': '检查中'})
        if io_bus is not None:
            try:
                test_val = io_bus.read("bin.P1-1.level")
                if test_val is not None:
                    result.items[-1]['status'] = '通过'
                else:
                    result.items[-1]['status'] = '警告'
                    result.warnings.append("IO总线: 仿真模式，部分tag返回None")
            except Exception as e:
                result.items[-1]['status'] = '失败'
                result.errors.append(f"IO总线不可用: {e}")
                result.passed = False
        else:
            result.items[-1]['status'] = '跳过'
            result.warnings.append("IO总线未注入，跳过检查")

        # === 传感器初始状态自检 ===
        sensor_checks = self._check_sensors(io_bus, controller)
        result.items.extend(sensor_checks)
        for s in sensor_checks:
            if s['status'] == '异常':
                result.errors.append(f"传感器 {s['item']}: {s['detail']}")
                result.passed = False
            elif s['status'] == '警告':
                result.warnings.append(f"传感器 {s['item']}: {s['detail']}")

        # === 小车位置有效性 ===
        result.items.append({'item': '小车位置', 'status': '检查中'})
        cart_ok = True
        for cart_id in ['Cart1', 'Cart2', 'Cart3']:
            pos = io_bus.read(f"cart.{cart_id}.position") if io_bus else None
            if pos is not None and (pos < 1 or pos > 7):
                cart_ok = False
                result.errors.append(f"{cart_id} 位置异常: {pos} (应为1-7)")
        cart4_pos = io_bus.read("cart.Cart4.position") if io_bus else None
        if cart4_pos is not None and (cart4_pos < 1 or cart4_pos > 6):
            cart_ok = False
            result.errors.append(f"Cart4 位置异常: {cart4_pos} (应为1-6)")
        if not cart_ok:
            result.passed = False
            result.items[-1]['status'] = '异常'
        else:
            result.items[-1]['status'] = '通过'

        # === 调度服务连通性（可选） ===
        if check_scheduling:
            result.items.append({'item': '调度服务', 'status': '检查中'})
            try:
                import socket
                for belt, port in [('D7', 8891), ('D8', 8892), ('D9', 8893), ('D6', 8894)]:
                    s = socket.socket()
                    s.settimeout(1)
                    r = s.connect_ex(('127.0.0.1', port))
                    s.close()
                    if r != 0:
                        result.warnings.append(f"调度服务 {belt}:{port} 不可达")
            except Exception:
                result.warnings.append("调度服务连通性检查失败")
            result.items[-1]['status'] = '通过' if not result.warnings else '警告'

        # === 汇总 ===
        print(f"[自检] {'通过' if result.passed else '失败'} "
              f"({len(result.errors)}错误/{len(result.warnings)}警告)", flush=True)
        for e in result.errors:
            print(f"  [ERROR] {e}", flush=True)
        for w in result.warnings:
            print(f"  [WARN] {w}", flush=True)

        if result.passed:
            self._transition(LifecycleState.STANDBY)
        return result

    def _check_sensors(self, io_bus, controller) -> List[dict]:
        """传感器初始状态自检"""
        results = []
        if io_bus is None:
            return [{'item': '传感器自检', 'status': '跳过'}]

        # 接近开关应处于 false（无物料经过）
        prox_sensors = [
            'S-E1','S-E2','S-E4','S-E5','S-E6','S-E7','S-E8','S-E9','S-E10',
            'S-D1','S-D2','S-D2-2','S-D3','S-D4','S-D5','S-D6','S-D7','S-D8',
            'S-D9','S-D13',
        ]
        for sid in prox_sensors:
            tag = f"sensor.{sid}.active"
            try:
                val = io_bus.read(tag)
                if val is True:
                    results.append({
                        'item': sid, 'status': '异常',
                        'detail': f'接近开关启动时应为false，实际为true（可能有残留物料信号）'
                    })
                else:
                    results.append({'item': sid, 'status': '通过'})
            except:
                results.append({'item': sid, 'status': '警告', 'detail': '读取失败'})

        # 激光传感器应处于 true（有原料）
        for lid in ['feed1_1', 'feed1_2', 'feed2_1', 'feed2_2', 'feed3']:
            tag = f"laser.{lid}.has_material"
            try:
                val = io_bus.read(tag)
                if val is False:
                    results.append({
                        'item': f'激光-{lid}', 'status': '警告',
                        'detail': '上料点无原料信号'
                    })
                else:
                    results.append({'item': f'激光-{lid}', 'status': '通过'})
            except:
                results.append({'item': f'激光-{lid}', 'status': '警告', 'detail': '读取失败'})

        return results

    # ------------------------------------------------------------------
    # 阶段2: 启动运行
    # ------------------------------------------------------------------

    def start(self):
        """从 STANDBY 进入 RUNNING"""
        if self._state not in (LifecycleState.STANDBY, LifecycleState.PAUSED):
            print(f"[生命周期] 无法从 {self._state.value} 启动", flush=True)
            return False
        self._transition(LifecycleState.RUNNING)
        self._emit('start')
        return True

    # ------------------------------------------------------------------
    # 阶段3: 正常停止（清空余料→关斗→停皮带→保存）
    # ------------------------------------------------------------------

    def stop(self, controller=None):
        """正常停止：依次执行清空流程"""
        if self._state not in (LifecycleState.RUNNING, LifecycleState.PAUSED):
            return False
        self._transition(LifecycleState.STOPPING)
        self._emit('stop')

        if controller:
            # 1. 停止上料（不再生成新物料）
            for route_id in list(controller.active_routes):
                controller.stop_route(route_id)

            # 2. 等待清空完成（最多30秒）
            waited = 0.0
            while controller.active_routes and waited < 30.0:
                time.sleep(0.5)
                waited += 0.5

            # 3. 关闭所有中转斗
            for hopper_id in controller.hoppers:
                controller.hoppers[hopper_id].is_open = False

            # 4. 停止所有皮带
            for conv in controller.conveyors.values():
                conv.stop()

        self._transition(LifecycleState.STANDBY)
        self._emit('stopped')
        return True

    # ------------------------------------------------------------------
    # 暂停/恢复
    # ------------------------------------------------------------------

    def pause(self):
        """暂停：保持当前状态不变"""
        if self._state != LifecycleState.RUNNING:
            return False
        self._transition(LifecycleState.PAUSED)
        self._emit('pause')
        return True

    def resume(self):
        """恢复"""
        if self._state != LifecycleState.PAUSED:
            return False
        self._transition(LifecycleState.RUNNING)
        self._emit('resume')
        return True

    # ------------------------------------------------------------------
    # 急停（立即切断所有输出）
    # ------------------------------------------------------------------

    def emergency_stop(self, controller=None):
        """急停：立即切断所有输出，不等待清空"""
        self._transition(LifecycleState.EMERGENCY)
        self._emit('emergency_stop')

        if controller:
            # 立即停止所有皮带
            for conv in controller.conveyors.values():
                conv.stop()
            # 关闭所有中转斗
            for hopper_id in controller.hoppers:
                controller.hoppers[hopper_id].is_open = False
            # 停止上料
            controller.is_running = False
            controller.feed_timer.stop()

        print("[急停] 所有输出已切断", flush=True)
        # 急停后回到 STANDBY（需人工确认复位）
        time.sleep(1)
        self._transition(LifecycleState.STANDBY)

    # ------------------------------------------------------------------
    # 关闭
    # ------------------------------------------------------------------

    def shutdown(self, controller=None):
        """安全关闭：停止→保存状态→断开IO→退出"""
        if self._state == LifecycleState.RUNNING:
            self.stop(controller)
        self._transition(LifecycleState.SHUTDOWN)
        self._emit('shutdown')
        print("[关闭] 系统已安全停机", flush=True)

    # ------------------------------------------------------------------
    # 状态持久化
    # ------------------------------------------------------------------

    def save_state(self, controller=None):
        """保存当前状态到文件"""
        if controller is None:
            return
        state = {
            'timestamp': time.time(),
            'lifecycle_state': self._state.value,
            'active_routes': list(controller.active_routes),
            'belt_auto_mode': dict(controller._belt_auto_mode),
        }
        try:
            os.makedirs(os.path.dirname(self._state_file), exist_ok=True)
            with open(self._state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[状态保存] 失败: {e}", flush=True)

    def load_state(self) -> Optional[dict]:
        """从文件加载状态"""
        if not os.path.exists(self._state_file):
            return None
        try:
            with open(self._state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
