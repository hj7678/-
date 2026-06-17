"""
调度管理器 — FeedingMaster 与调度引擎的对接模块

职责:
  1. 构建调度请求数据 (料位 + 小车位置 + 分料状态)
  2. 发送请求 → 调度服务 (:8891-8894)
  3. 接收调度序列 → 缓存 → 管理执行
  4. 触发: 空闲检测 / 紧急 / 预请求
"""
import json
import socket
import threading
import time
import sys
from typing import Dict, List, Optional, Set, Tuple

# 调度服务端口
SCHEDULING_HOST = '127.0.0.1'
SCHEDULING_PORTS = {'D7': 8891, 'D8': 8892, 'D9': 8893, 'D6': 8894}

# 路线→料仓列前缀
BELT_TO_PREFIX = {'D7': 'P1', 'D8': 'P2', 'D9': 'P4', 'D6': 'S'}

# 小车→皮带
CART_TO_BELT = {'Cart1': 'D7', 'Cart2': 'D8', 'Cart3': 'D9', 'Cart4': 'D6'}

# 皮带→小车
BELT_TO_CART = {v: k for k, v in CART_TO_BELT.items()}

# 调度冷却
SCHEDULE_COOLDOWN = 120.0      # 普通请求冷却
EMERGENCY_COOLDOWN = 10.0      # 紧急请求冷却
EMERGENCY_THRESHOLD_TONS = 11.0  # 紧急阈值 (吨)
IDLE_THRESHOLD_TONS = 70.0      # 空闲阈值 (吨) — D7/D8/D9
D6_IDLE_THRESHOLD_TONS = 336.0  # D6 空闲阈值 (420*0.8)


class ScheduleManager:
    """FeedingMaster 调度管理器"""

    def __init__(self, stock_client, route_manager):
        self.stock = stock_client
        self.route_mgr = route_manager

        self._sequences: Dict[str, list] = {}
        self._sequences_lock = threading.Lock()

        self._executing: Dict[str, str] = {}
        self._executing_bin: Dict[str, str] = {}

        self._last_request: Dict[str, float] = {}
        self._last_emergency: Dict[str, float] = {}

        # 防抖: 每个belt每次tick最多触发一次
        self._tick_triggered: set = set()

        self._on_sequence: Optional[callable] = None

    def on_sequence_ready(self, callback):
        """序列可用时的回调 callback(belt_id, [bin_ids])"""
        self._on_sequence = callback

    # ── 每周期 tick ──

    def set_active(self, active: bool):
        was = getattr(self, '_active', False)
        self._active = active
        if active and not was:
            print("[FM-Sched] 调度服务已激活", flush=True)
        elif not active and was:
            print("[FM-Sched] 调度服务已关闭", flush=True)

    def tick(self, total_runtime: float):
        """检查是否需要触发调度"""
        if not getattr(self, '_active', False):
            return
        self._tick_triggered.clear()
        for belt_id in SCHEDULING_PORTS:
            if self._check_emergency(belt_id, total_runtime):
                continue
            if self._check_idle(belt_id, total_runtime):
                continue

    def _check_emergency(self, belt_id: str, now: float) -> bool:
        levels = self._get_belt_bins(belt_id)
        for b in levels:
            if b['stock'] < EMERGENCY_THRESHOLD_TONS:
                last = self._last_emergency.get(belt_id, 0)
                if now - last >= EMERGENCY_COOLDOWN:
                    self._last_emergency[belt_id] = now
                    print(f"[FM-Sched] {belt_id} 紧急调度 (料位={b['stock']:.1f}t)", flush=True)
                    self._request_schedule(belt_id)
                    return True
        return False

    def _check_idle(self, belt_id: str, now: float) -> bool:
        # 正在执行中或已有缓存序列 → 跳过
        if belt_id in self._executing:
            return False
        with self._sequences_lock:
            if self._sequences.get(belt_id):
                return False

        # 空闲检测: 有仓低于阈值
        threshold = D6_IDLE_THRESHOLD_TONS if belt_id == 'D6' else IDLE_THRESHOLD_TONS
        levels = self._get_belt_bins(belt_id)
        any_below = any(b['stock'] < threshold for b in levels)
        if not any_below:
            return False

        last = self._last_request.get(belt_id, 0)
        if now - last < SCHEDULE_COOLDOWN:
            return False

        self._last_request[belt_id] = now
        print(f"[FM-Sched] {belt_id} 空闲调度", flush=True)
        self._request_schedule(belt_id)
        return True

    def request_schedule_now(self, belt_id: str):
        """强制请求调度（忽略冷却）"""
        self._request_schedule(belt_id)

    # ── 构建请求 ──

    def _get_belt_bins(self, belt_id: str) -> List[dict]:
        """从 Stock Management 获取某皮带对应料仓的料位"""
        from scheduling.bin_config import BELT_BINS
        bin_ids = BELT_BINS.get(belt_id, [])
        if not bin_ids:
            return []
        levels = self.stock.get_levels(bin_ids)
        return [
            {
                'bin_id': b['bin_id'],
                'stock': b['level_tons'],
                'consumption_rate': b.get('consumption_rate', 0.01),
                'maintenance': False,
                'has_future_order': False,
            }
            for b in levels
        ]

    def _request_schedule(self, belt_id: str):
        """发送调度请求到调度服务"""
        if belt_id in self._tick_triggered:
            return
        self._tick_triggered.add(belt_id)

        bins = self._get_belt_bins(belt_id)
        if not bins:
            return

        cart_id = BELT_TO_CART.get(belt_id, '')
        cart_pos = self._cart_positions.get(cart_id, 1) if hasattr(self, '_cart_positions') else 1
        left_div, right_div = False, False
        if hasattr(self, '_cart_divert'):
            left_div, right_div = self._cart_divert.get(cart_id, (False, False))

        if belt_id == 'D8' and hasattr(self, '_map_d8_pos'):
            cart_pos = self._map_d8_pos(cart_pos, left_div, right_div)

        payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "belt_id": belt_id,
            "boost_mode": False,
            "bins": bins,
            "cart_position": cart_pos,
            "left_divert": left_div,
            "right_divert": right_div,
            "maintenance_bins": list(getattr(self, '_maintenance_bins', set())),
        }

        t = threading.Thread(target=self._send_and_recv, args=(belt_id, payload), daemon=True)
        t.start()

    def _send_and_recv(self, belt_id: str, payload: dict):
        """短连接发送 (调度请求不频繁, 避免持久连接竞态)"""
        port = SCHEDULING_PORTS.get(belt_id)
        if not port:
            return
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((SCHEDULING_HOST, port))
            sock.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))

            buf = b""
            sock.settimeout(120)  # D8 14仓计算较慢, 给2分钟
            while b"\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk

            if buf:
                resp = json.loads(buf.decode("utf-8").strip())
                self._on_schedule_response(belt_id, resp)
        except Exception as e:
            print(f"[FM-Sched] {belt_id} 调度请求失败: {e}", file=sys.stderr)
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    def _on_schedule_response(self, belt_id: str, resp: dict):
        seq = resp.get('sequence', [])
        if not seq:
            print(f"[FM-Sched] {belt_id} 无需补料", flush=True)
            return

        print(f"[FM-Sched] {belt_id} 收到序列: {seq}", flush=True)

        # 缓存序列
        with self._sequences_lock:
            self._sequences[belt_id] = list(seq)

        # 仅当皮带空闲时自动启动第一条, 否则等WAITING→auto-continue
        if not self.is_executing(belt_id) and self._on_sequence:
            self._on_sequence(belt_id, list(seq))

    # ── 序列消费 ──

    def get_next_bin(self, belt_id: str) -> Optional[str]:
        """取下一个待补料仓 (不移除)"""
        with self._sequences_lock:
            seq = self._sequences.get(belt_id, [])
            return seq[0] if seq else None

    def pop_next_bin(self, belt_id: str) -> Optional[str]:
        """取出并移除下一个料仓"""
        with self._sequences_lock:
            seq = self._sequences.get(belt_id, [])
            if not seq:
                return None
            nxt = seq.pop(0)
            if not seq:
                del self._sequences[belt_id]
            return nxt

    def has_sequence(self, belt_id: str) -> bool:
        with self._sequences_lock:
            return bool(self._sequences.get(belt_id))

    # ── 执行追踪 ──

    def mark_executing(self, belt_id: str, route_id: str, bin_id: str):
        self._executing[belt_id] = route_id
        self._executing_bin[belt_id] = bin_id

    def mark_completed(self, belt_id: str):
        self._executing.pop(belt_id, None)
        self._executing_bin.pop(belt_id, None)

    def is_executing(self, belt_id: str) -> bool:
        return belt_id in self._executing

    # ── 状态注入 ──

    def update_cart_state(self, cart_positions: dict, cart_divert: dict):
        self._cart_positions = cart_positions
        self._cart_divert = cart_divert

    @staticmethod
    def _map_d8_pos(row: int, left: bool, right: bool) -> int:
        if right and not left:
            return 15 - row  # P3
        return 8 - row       # P2
