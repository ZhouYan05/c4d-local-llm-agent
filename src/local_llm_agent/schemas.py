"""结构化输出的数据契约（schema）与校验器。

小参数模型（1B）直接生成长 JSON 容易出错，因此这里把「地图生成」任务
拆成两个稳定的 JSON 契约，并用严格的校验器 + 重采样保证可用性：

1. PlanCard  —— 任务规划：解析用户意图，产出目标地点、中心坐标、待生成 POI 类别；
2. MarkerCard —— 地点卡片数组：每个地点含 name / category / description / lat / lon。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 西亚斯国际学院（SIAS / 郑州西亚斯学院）位于河南省郑州市新郑市。
# 作为区域中心提供给模型，模型据此在自己生成的坐标里保持合理范围。
SIAS_CENTER = {"lat": 34.5040, "lon": 113.7466, "name": "郑州西亚斯学院（SIAS University）"}
MAX_RADIUS_KM = 3.0


@dataclass
class Plan:
    task: str
    place_name: str
    center_lat: float
    center_lon: float
    marker_count: int
    categories: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "task": self.task,
            "place_name": self.place_name,
            "center": {"lat": self.center_lat, "lon": self.center_lon},
            "marker_count": self.marker_count,
            "categories": self.categories,
        }


@dataclass
class Marker:
    name: str
    category: str
    description: str
    lat: float
    lon: float

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "lat": self.lat,
            "lon": self.lon,
        }


PLAN_SCHEMA_HINT = (
    '{"task":str, "place_name":str, "center_lat":number, "center_lon":number, '
    '"marker_count":int(3-10), "categories":[str, ...]}'
)
MARKER_SCHEMA_HINT = (
    '{"markers":[{"name":str, "category":str, "description":str(中文,一句话), '
    '"lat":number, "lon":number}, ...]}'
)


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except Exception:
        return None


def validate_plan(obj: dict) -> bool:
    if not isinstance(obj, dict):
        return False
    if not isinstance(obj.get("place_name"), str) or not obj.get("place_name", "").strip():
        return False
    lat, lon = _num(obj.get("center_lat")), _num(obj.get("center_lon"))
    if lat is None or lon is None:
        return False
    mc = obj.get("marker_count")
    if not isinstance(mc, int) or not (3 <= mc <= 12):
        return False
    cats = obj.get("categories")
    if not isinstance(cats, list) or not cats:
        return False
    return True


def validate_markers(obj: dict, want: int) -> bool:
    markers = obj.get("markers") if isinstance(obj, dict) else None
    if not isinstance(markers, list) or len(markers) < max(3, want - 2):
        return False
    for m in markers:
        if not isinstance(m, dict):
            return False
        if not str(m.get("name", "")).strip():
            return False
        if _num(m.get("lat")) is None or _num(m.get("lon")) is None:
            return False
    return True


def to_plan(obj: dict) -> Plan:
    return Plan(
        task=str(obj.get("task", "")).strip(),
        place_name=str(obj.get("place_name", "")).strip(),
        center_lat=float(obj["center_lat"]),
        center_lon=float(obj["center_lon"]),
        marker_count=int(obj["marker_count"]),
        categories=[str(c).strip() for c in obj.get("categories", []) if str(c).strip()],
    )


def to_markers(obj: dict) -> list[Marker]:
    out = []
    for m in obj.get("markers", []):
        out.append(
            Marker(
                name=str(m.get("name", "")).strip(),
                category=str(m.get("category", "")).strip(),
                description=str(m.get("description", "")).strip(),
                lat=float(m["lat"]),
                lon=float(m["lon"]),
            )
        )
    return out
