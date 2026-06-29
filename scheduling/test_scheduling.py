"""
调度模块验证脚本 —— 测试 7 仓/14 仓引擎和端到端 TCP 流程
"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scheduling.engine import SchedulingEngine
from scheduling.sched_types import BinState, ScheduleResult
from scheduling.server import SchedulingServer


# ========================================================================
# 14仓测试数据
# ========================================================================

D8_BINS = [
    BinState("P2-1", stock=20.3, consumption_rate=0.01, has_future_order=True),
    BinState("P2-2", stock=56.8, consumption_rate=0.01, has_future_order=True),
    BinState("P2-3", stock=10.5, consumption_rate=0.01, has_future_order=True),
    BinState("P2-4", stock=40.2, consumption_rate=0.01, has_future_order=True),
    BinState("P2-5", stock=15.1, consumption_rate=0.01, maintenance=True),
    BinState("P2-6", stock=10.1, consumption_rate=0.01, maintenance=True),
    BinState("P2-7", stock=26.5, consumption_rate=0.01, has_future_order=True),
    BinState("P3-1", stock=10.6, consumption_rate=0.015, has_future_order=True),
    BinState("P3-2", stock=63.3, consumption_rate=0.015, has_future_order=True),
    BinState("P3-3", stock=13.3, consumption_rate=0.01, maintenance=True),
    BinState("P3-4", stock=15.1, consumption_rate=0.015, has_future_order=True),
    BinState("P3-5", stock=70.0, consumption_rate=0.01, has_future_order=True),
    BinState("P3-6", stock=58.1, consumption_rate=0.01, has_future_order=True),
    BinState("P3-7", stock=20.5, consumption_rate=0.01, maintenance=True),
]

# ========================================================================
# 7仓测试数据（D7 P1列）
# ========================================================================

D7_BINS = [
    BinState("P1-1", stock=25.0, consumption_rate=0.01),
    BinState("P1-2", stock=60.0, consumption_rate=0.01),
    BinState("P1-3", stock=15.0, consumption_rate=0.01),
    BinState("P1-4", stock=45.0, consumption_rate=0.01),
    BinState("P1-5", stock=55.0, consumption_rate=0.01),
    BinState("P1-6", stock=20.0, consumption_rate=0.01),
    BinState("P1-7", stock=30.0, consumption_rate=0.01),
]


def test_engine_14bin_trigger():
    """14仓模式：触发条件检查"""
    engine = SchedulingEngine(col_count=2, belt_id='D8')
    triggered, reason = engine.check_trigger(D8_BINS)
    assert triggered, f"应触发调度，实际: {reason}"
    print(f"PASS: 14仓触发条件 -> {reason}")


def test_engine_14bin_eligible():
    """14仓模式：符合补料条件的仓"""
    engine = SchedulingEngine(col_count=2, belt_id='D8')
    eligible = engine.get_eligible_bins(D8_BINS)
    assert len(eligible) > 0, "应有符合补料条件的仓"
    # 检修仓不应出现在列表中
    maintenance_bins = {b.bin_id for b in eligible if b.maintenance}
    assert len(maintenance_bins) == 0, f"检修仓不应符合条件: {maintenance_bins}"
    print(f"PASS: 14仓补料条件 -> {len(eligible)} 个仓符合: {[b.bin_id for b in eligible]}")


def test_engine_14bin_solve():
    """14仓模式：完整求解"""
    engine = SchedulingEngine(col_count=2, belt_id='D8')
    result = engine.solve(D8_BINS)
    assert isinstance(result, ScheduleResult)
    assert len(result.sequence) > 0, "应有上料序列"
    assert len(result.steps) == len(result.sequence), "步骤数应与序列长度一致"
    print(f"PASS: 14仓求解 -> 序列({len(result.sequence)}仓): {result.sequence}")
    print(f"      总移动:{result.total_move:.1f}s 总等料:{result.total_wait:.1f}s "
          f"总补料:{result.total_fill:.1f}s 总停产:{result.total_stop:.1f}s")
    for s in result.steps[:3]:
        print(f"      [{s.seq}] {s.bin_id} {s.mode} 库存:{s.remain_stock}t 状态:{s.stock_status}")


def test_engine_7bin_trigger():
    """7仓模式：触发条件检查"""
    engine = SchedulingEngine(col_count=1, belt_id='D7')
    triggered, reason = engine.check_trigger(D7_BINS)
    assert triggered, f"应触发调度，实际: {reason}"
    print(f"PASS: 7仓触发条件 -> {reason}")


def test_engine_7bin_solve():
    """7仓模式：完整求解"""
    engine = SchedulingEngine(col_count=1, belt_id='D7')
    result = engine.solve(D7_BINS)
    assert isinstance(result, ScheduleResult)
    assert len(result.sequence) > 0
    assert result.belt_id == 'D7'
    # 7仓不应有跨列模式
    cross_steps = [s for s in result.steps if s.mode == "跨列"]
    assert len(cross_steps) == 0, f"7仓不应出现跨列移动: {cross_steps}"
    print(f"PASS: 7仓求解 -> 序列({len(result.sequence)}仓): {result.sequence}")
    for s in result.steps[:3]:
        print(f"      [{s.seq}] {s.bin_id} {s.mode} 库存:{s.remain_stock}t 状态:{s.stock_status}")


def test_engine_no_trigger():
    """库存充足时不应触发"""
    engine = SchedulingEngine(col_count=1, belt_id='D7')
    full_bins = [
        BinState(f"P1-{i}", stock=100.0, consumption_rate=0.01)
        for i in range(1, 8)
    ]
    triggered, _ = engine.check_trigger(full_bins)
    assert not triggered, "库存充足不应触发"
    result = engine.solve(full_bins)
    assert result.sequence == [], "库存充足时序列应为空"
    print("PASS: 库存充足不触发")


def test_server_process_request():
    """服务端请求处理"""
    server = SchedulingServer(belt_id='D8')
    request = {
        "timestamp": "2026-05-20 15:00:00.000000",
        "belt_id": "D8",
        "boost_mode": False,
        "bins": [
            {"bin_id": "P2-1", "stock": 20.3, "consumption_rate": 0.01, "has_future_order": True},
            {"bin_id": "P2-2", "stock": 56.8, "consumption_rate": 0.01, "has_future_order": True},
            {"bin_id": "P2-3", "stock": 10.5, "consumption_rate": 0.01, "has_future_order": True},
            {"bin_id": "P2-4", "stock": 40.2, "consumption_rate": 0.01, "has_future_order": True},
            {"bin_id": "P2-5", "stock": 15.1, "consumption_rate": 0.01, "maintenance": True},
            {"bin_id": "P2-6", "stock": 10.1, "consumption_rate": 0.01, "maintenance": True},
            {"bin_id": "P2-7", "stock": 26.5, "consumption_rate": 0.01, "has_future_order": True},
            {"bin_id": "P3-1", "stock": 10.6, "consumption_rate": 0.015, "has_future_order": True},
            {"bin_id": "P3-2", "stock": 63.3, "consumption_rate": 0.015, "has_future_order": True},
            {"bin_id": "P3-3", "stock": 13.3, "consumption_rate": 0.01, "maintenance": True},
            {"bin_id": "P3-4", "stock": 15.1, "consumption_rate": 0.015, "has_future_order": True},
            {"bin_id": "P3-5", "stock": 70.0, "consumption_rate": 0.01, "has_future_order": True},
            {"bin_id": "P3-6", "stock": 58.1, "consumption_rate": 0.01, "has_future_order": True},
            {"bin_id": "P3-7", "stock": 20.5, "consumption_rate": 0.01, "maintenance": True},
        ],
    }
    json_str = json.dumps(request, ensure_ascii=False)
    response_str = server._process_request(json_str)
    response = json.loads(response_str)

    assert "timestamp" in response
    assert response["belt_id"] == "D8"
    assert "sequence" in response
    assert "steps" in response
    assert "summary" in response
    print(f"PASS: 服务端TCP请求 -> 序列{len(response['sequence'])}仓, "
          f"步骤{len(response['steps'])}个")


if __name__ == "__main__":
    print("=" * 60)
    print("调度算法模块 验证")
    print("=" * 60)
    test_engine_14bin_trigger()
    test_engine_14bin_eligible()
    test_engine_14bin_solve()
    test_engine_7bin_trigger()
    test_engine_7bin_solve()
    test_engine_no_trigger()
    test_server_process_request()
    print("=" * 60)
    print("全部 7 项测试通过")
