"""针对 schemas 与 tools 的离线单元测试（不需要加载模型）。

    python -m pytest tests/ -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from local_llm_agent.schemas import (  # noqa: E402
    SIAS_CENTER,
    Marker,
    to_markers,
    to_plan,
    validate_markers,
    validate_plan,
)
from local_llm_agent.tools import (  # noqa: E402
    build_default_registry,
    geocode,
    haversine_km,
    validate_markers as vm,
)


def test_validate_plan_ok():
    obj = {
        "task": "生成 SIAS 地图",
        "place_name": "西亚斯大学",
        "center_lat": 34.50,
        "center_lon": 113.74,
        "marker_count": 6,
        "categories": ["教学楼", "食堂"],
    }
    assert validate_plan(obj)
    p = to_plan(obj)
    assert p.place_name == "西亚斯大学"
    assert p.marker_count == 6


def test_validate_plan_rejects_bad():
    assert not validate_plan({"marker_count": 6})          # 缺 place_name/坐标
    assert not validate_plan({"place_name": "x", "center_lat": 1, "center_lon": 2,
                              "marker_count": 99, "categories": ["a"]})  # 数量越界


def test_marker_validation_and_filter():
    good = Marker("图书馆", "图书馆", "藏书 50 万册", 34.5045, 113.7470)
    far = Marker("北京天安门", "地标", "太远了", 39.9087, 116.3975)
    dup = Marker("图书馆", "图书馆", "重复", 34.5045, 113.7470)
    kept, dropped = vm([good, far, dup], SIAS_CENTER)
    assert [m.name for m in kept] == ["图书馆"]
    reasons = " ".join(d["reason"] for d in dropped)
    assert "范围" in reasons and "重复" in reasons


def test_validate_markers_min_count():
    obj = {"markers": [{"name": "a", "lat": 34.5, "lon": 113.7}]}
    assert not validate_markers(obj, want=6)
    lst = to_markers({"markers": [{"name": "a", "category": "x", "description": "d",
                                   "lat": 34.5, "lon": 113.7}]})
    assert lst[0].category == "x"


def test_haversine():
    d = haversine_km(34.5040, 113.7466, 34.5040, 113.7466)
    assert d < 0.001
    d2 = haversine_km(34.50, 113.74, 34.60, 113.74)
    assert 10 < d2 < 12  # 0.1 纬度约 11km


def test_geocode_hit_and_fallback():
    hit = geocode("SIAS University")
    assert hit["source"] == "gazetteer" and abs(hit["lat"] - SIAS_CENTER["lat"]) < 0.01
    fb = geocode("某个不存在的地方", fallback={"lat": 1.0, "lon": 2.0, "name": "FB"})
    assert fb["source"] == "fallback" and fb["lat"] == 1.0


def test_registry_lists_tools():
    reg = build_default_registry()
    names = reg.names()
    assert "geocode" in names and "validate_markers" in names
    assert reg.get("nope") is None
