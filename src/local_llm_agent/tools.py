"""工具层（function calling 的实际执行体）。

Agent 的"工具调用"协议：模型只负责**决定调用哪个工具、传什么参数**
（以 JSON 表达），真正的副作用（地理编码、坐标校验、写 HTML 文件）
由这里的工具函数完成。这样职责清晰、可测试、可离线复现。

工具清单：
  * geocode(place_name)            —— 地理编码（离线地名库 + 中心回退）
  * haversine_km(lat1, lon1, ...)  —— 距离计算（坐标合理性校验）
  * validate_markers(markers)      —— 过滤越界/重复的 POI
  * render_map(...)                —— 生成交互式 Leaflet 地图 HTML
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .schemas import SIAS_CENTER, MAX_RADIUS_KM, Marker

# 离线地名库：至少覆盖本挑战目标区域；缺失时回退到提供的中心坐标。
_GAZETTEER: dict[str, dict] = {
    "sias": SIAS_CENTER,
    "西亚斯": SIAS_CENTER,
    "郑州西亚斯学院": SIAS_CENTER,
    "sias university": SIAS_CENTER,
    "新郑": {"lat": 34.3951, "lon": 113.7406, "name": "新郑市"},
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass
class Tool:
    name: str
    description: str
    func: Callable
    input_hint: str


class ToolRegistry:
    """可注册/可列举的工具容器，Agent 通过名字调用。"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def spec(self) -> list[dict]:
        return [
            {"name": t.name, "description": t.description, "input": t.input_hint}
            for t in self._tools.values()
        ]

    def call(self, name: str, **kwargs):
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"unknown tool: {name}")
        return tool.func(**kwargs)


def geocode(place_name: str, fallback: dict | None = None) -> dict:
    """离线地理编码：命中地名库则返回其坐标，否则回退到 fallback/中心。"""
    key = (place_name or "").strip().lower()
    for k, v in _GAZETTEER.items():
        if k in key or key in k:
            return {"lat": v["lat"], "lon": v["lon"], "name": v["name"], "source": "gazetteer"}
    fb = fallback or SIAS_CENTER
    return {"lat": fb["lat"], "lon": fb["lon"], "name": fb.get("name", place_name), "source": "fallback"}


def validate_markers(markers: list[Marker], center: dict, radius_km: float = MAX_RADIUS_KM) -> tuple[list[Marker], list[dict]]:
    """剔除越界与重名/重坐标的 POI，返回 (保留项, 被丢弃项及原因)。"""
    kept: list[Marker] = []
    dropped: list[dict] = []
    seen: set[str] = set()
    for m in markers:
        d = haversine_km(center["lat"], center["lon"], m.lat, m.lon)
        if d > radius_km:
            dropped.append({"name": m.name, "reason": f"超出 {radius_km}km 范围（{d:.2f}km）"})
            continue
        key = f"{m.name}|{round(m.lat,4)}|{round(m.lon,4)}"
        if key in seen:
            dropped.append({"name": m.name, "reason": "重复地点"})
            continue
        seen.add(key)
        kept.append(m)
    return kept, dropped


def disperse_markers(
    markers: list[Marker],
    center: dict,
    offset_km: float = 0.25,
    min_gap_deg: float = 5e-4,
) -> tuple[list[Marker], list[dict]]:
    """对「坐标重合」的标记做确定性环形分散（幂等、可复现）。

    小模型（如本地 Gemma-3-1B）常把所有 POI 放在同一个中心坐标上：名称/类别/简介
    由模型生成，但坐标退化为单点，交互式地图会全部叠在一起。这里只针对**互相重合**
    的点，按它们在列表中的顺序，均匀铺在一个以重合锚点为圆心、半径 offset_km 的小圆
    周上（正北起、顺时针），使地图视觉可分辨；坐标本来就互不相同的点原样保留。
    返回 (处理后的标记列表, 每条被移动记录的说明)，供 trace 如实留痕。
    """
    moved: list[dict] = []
    # 按四舍五入到 min_gap_deg 的坐标分组，找出重合组。
    groups: dict[tuple[int, int], list[int]] = {}
    for i, m in enumerate(markers):
        key = (round(m.lat / min_gap_deg), round(m.lon / min_gap_deg))
        groups.setdefault(key, []).append(i)

    out = list(markers)
    for idxs in groups.values():
        if len(idxs) < 2:
            continue
        anchor_lat = markers[idxs[0]].lat
        anchor_lon = markers[idxs[0]].lon
        dlat = offset_km / 111.32
        dlon = offset_km / (111.32 * math.cos(math.radians(anchor_lat)) or 1.0)
        n = len(idxs)
        for k, i in enumerate(idxs):
            # 正北为 0，顺时针均分，避免方向重叠。
            ang = 2 * math.pi * k / n
            new_lat = anchor_lat + dlat * math.cos(ang)
            new_lon = anchor_lon + dlon * math.sin(ang)
            m = markers[i]
            moved.append({
                "name": m.name,
                "from": [anchor_lat, anchor_lon],
                "to": [round(new_lat, 4), round(new_lon, 4)],
                "reason": f"与其余 {n - 1} 个标记坐标重合，环形分散（半径 {offset_km}km）",
            })
            out[i] = Marker(
                name=m.name, category=m.category, description=m.description,
                lat=round(new_lat, 4), lon=round(new_lon, 4),
            )
    return out, moved


def build_default_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(Tool("geocode", "把地名解析为经纬度坐标", geocode, '{"place_name":str}'))
    reg.register(Tool("haversine_km", "计算两个经纬度之间的距离(km)", haversine_km, '{"lat1":num,"lon1":num,"lat2":num,"lon2":num}'))
    reg.register(Tool("validate_markers", "校验并过滤 POI 列表", validate_markers, '{"markers":[...],"center":{...}}'))
    reg.register(Tool("disperse_markers", "对坐标重合的 POI 做确定性环形分散", disperse_markers, '{"markers":[...],"center":{...}}'))
    return reg
