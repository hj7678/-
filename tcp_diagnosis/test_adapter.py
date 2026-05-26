"""
TCP 诊断模块验证脚本 —— 测试适配器和端到端诊断流程
"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fault_diagnosis.types import RouteState, SystemSnapshot
from fault_diagnosis.engine import DiagnosisEngine
from tcp_diagnosis.adapter import TcpDataAdapter
from tcp_diagnosis.server import TcpDiagnosisServer


def make_test_json(overrides=None):
    """构造与 generate_data.json 同格式的测试数据"""
    data = {
        "timestamp": "2026-05-20 10:00:00.000000",
        "sensors": {
            "S-E1": {"type": "proximity", "unit": "bool", "value": True},
            "S-E4": {"type": "proximity", "unit": "bool", "value": True},
            "S-E8": {"type": "proximity", "unit": "bool", "value": True},
            "S-E10": {"type": "proximity", "unit": "bool", "value": True},
            "S-D7": {"type": "proximity", "unit": "bool", "value": True},
        },
        "conveyor_sensors": {
            "S-CV-E1": {"type": "speed", "unit": "sint", "value": 500},
            "S-CV-E4": {"type": "speed", "unit": "sint", "value": 500},
            "S-CV-E8": {"type": "speed", "unit": "sint", "value": 500},
            "S-CV-E10": {"type": "speed", "unit": "sint", "value": 500},
            "S-CV-D7": {"type": "speed", "unit": "sint", "value": 500},
        },
        "hoppers": {
            "hopper1": {
                "switch": {"type": "switch", "unit": "bool", "value": True},
                "weight": {"type": "weight", "unit": "t", "value": 0.0},
            },
        },
        "feed_signals": {
            "feed1_1": {"type": "feed", "unit": "bool", "value": True},
        },
        "cart_sensors": {
            "Cart1": {
                "position": {"type": "position", "unit": "int", "value": 1},
                "left_limit": {"type": "limit", "unit": "bool", "value": False},
                "right_limit": {"type": "limit", "unit": "bool", "value": False},
                "left_divert": {"type": "divert", "unit": "bool", "value": False},
                "right_divert": {"type": "divert", "unit": "bool", "value": False},
            },
            "Cart2": {
                "position": {"type": "position", "unit": "int", "value": 1},
                "left_limit": {"type": "limit", "unit": "bool", "value": False},
                "right_limit": {"type": "limit", "unit": "bool", "value": False},
                "left_divert": {"type": "divert", "unit": "bool", "value": False},
                "right_divert": {"type": "divert", "unit": "bool", "value": False},
            },
            "Cart3": {
                "position": {"type": "position", "unit": "int", "value": 1},
                "left_limit": {"type": "limit", "unit": "bool", "value": False},
                "right_limit": {"type": "limit", "unit": "bool", "value": False},
                "left_divert": {"type": "divert", "unit": "bool", "value": False},
                "right_divert": {"type": "divert", "unit": "bool", "value": False},
            },
            "Cart4": {
                "position": {"type": "position", "unit": "int", "value": 1},
                "left_limit": {"type": "limit", "unit": "bool", "value": False},
                "right_limit": {"type": "limit", "unit": "bool", "value": False},
                "left_divert": {"type": "divert", "unit": "bool", "value": False},
                "right_divert": {"type": "divert", "unit": "bool", "value": False},
            },
        },
    }
    if overrides:
        _deep_update(data, overrides)
    return data


def _deep_update(d, u):
    for k, v in u.items():
        if isinstance(v, dict) and isinstance(d.get(k), dict):
            _deep_update(d[k], v)
        else:
            d[k] = v


def test_adapter_basic():
    """适配器基本转换：正常 FEEDING 状态"""
    adapter = TcpDataAdapter()
    data = make_test_json()
    snap = adapter.build_snapshot(data)

    assert snap.active_route_ids == ["route1"], f"活跃路线应为route1，实际: {snap.active_route_ids}"
    assert "route1" in snap.routes
    assert snap.routes["route1"].state == RouteState.FEEDING
    assert snap.conveyors["E1"].is_running
    assert snap.conveyors["E1"].speed == 500
    assert snap.proximity_sensors["S-E1"].state is True
    assert snap.hoppers["hopper1"].switch_open is True
    print("PASS: 适配器基本转换")


def test_adapter_no_feed_signal():
    """无上料信号且皮带全停时路线为 IDLE"""
    adapter = TcpDataAdapter()
    data = make_test_json({
        "feed_signals": {"feed1_1": {"value": False}},
        "conveyor_sensors": {
            "S-CV-E1": {"value": 0},
            "S-CV-E4": {"value": 0},
            "S-CV-E8": {"value": 0},
            "S-CV-E10": {"value": 0},
            "S-CV-D7": {"value": 0},
        },
    })
    snap = adapter.build_snapshot(data)

    assert snap.active_route_ids == []
    assert snap.routes["route1"].state == RouteState.IDLE
    print("PASS: 无上料信号 IDLE")


def test_adapter_clearing():
    """上料信号关闭但皮带仍在运行 → CLEARING"""
    adapter = TcpDataAdapter()
    data = make_test_json({"feed_signals": {"feed1_1": {"value": False}}})
    snap = adapter.build_snapshot(data)

    # feed 关了但传感器数据里皮带转速还在 → running=True, 非 active → CLEARING
    assert snap.routes["route1"].state == RouteState.CLEARING
    print("PASS: CLEARING 状态推断")


def test_adapter_multiple_routes():
    """多路线场景"""
    adapter = TcpDataAdapter()
    data = make_test_json()
    # 同时激活 route1 和 route3
    data["feed_signals"]["feed2_1"] = {"type": "feed", "unit": "bool", "value": True}
    # route3 的皮带
    data["conveyor_sensors"]["S-CV-E5"] = {"type": "speed", "unit": "sint", "value": 500}
    data["sensors"]["S-E5"] = {"type": "proximity", "unit": "bool", "value": True}

    snap = adapter.build_snapshot(data)
    assert "route1" in snap.active_route_ids
    assert "route3" in snap.active_route_ids
    print("PASS: 多路线场景")


def test_end_to_end_no_false_positive():
    """端到端：正常工况不应产生高置信度误报"""
    engine = DiagnosisEngine()
    adapter = TcpDataAdapter()
    data = make_test_json()

    for i in range(30):
        data["timestamp"] = f"2026-05-20 10:00:{i:02d}.000000"
        snap = adapter.build_snapshot(data)
        results = engine.diagnose(snap)

    high_conf = [r for r in results if r.confidence >= 0.7]
    assert len(high_conf) == 0, f"误报: {[(r.sensor_id, r.description) for r in high_conf]}"
    print("PASS: 端到端零误报")


def test_end_to_end_cart_fault():
    """端到端：小车传感器互斥诊断"""
    engine = DiagnosisEngine()
    adapter = TcpDataAdapter()
    data = make_test_json()
    data["cart_sensors"]["Cart1"]["left_limit"]["value"] = True
    data["cart_sensors"]["Cart1"]["right_limit"]["value"] = True

    snap = adapter.build_snapshot(data)
    results = engine.diagnose(snap)
    high = [r for r in results if r.confidence >= 0.9 and "limit" in r.sensor_id]
    assert high, "未检出小车极限互斥"
    print(f"PASS: 端到端小车故障检出 -> {high[0].description}")


def test_server_process_frame():
    """服务端 _process_frame 方法"""
    server = TcpDiagnosisServer()
    data = make_test_json()
    json_str = json.dumps(data, ensure_ascii=False)

    response_str = server._process_frame(json_str)
    response = json.loads(response_str)
    assert "timestamp" in response
    assert "diagnosis_text" in response
    assert "diagnosis_results" in response
    assert isinstance(response["diagnosis_results"], list)
    print(f"PASS: 服务端帧处理 -> {response['diagnosis_text']}")


if __name__ == "__main__":
    print("=" * 60)
    print("TCP 诊断模块 验证")
    print("=" * 60)
    test_adapter_basic()
    test_adapter_no_feed_signal()
    test_adapter_clearing()
    test_adapter_multiple_routes()
    test_end_to_end_no_false_positive()
    test_end_to_end_cart_fault()
    test_server_process_frame()
    print("=" * 60)
    print("全部 7 项测试通过")
