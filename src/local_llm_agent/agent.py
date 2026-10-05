"""MapAgent —— 多步本地 Agent 循环。

流程（每一步都是「模型决策 → 工具执行 → 观测」的闭环）：

  Step 1  规划 Plan      : 模型解析用户意图 -> Plan(地点/中心/类别/marker 数量)
  Step 2  调用 geocode   : 工具解析中心坐标（模型给的坐标作为回退）
  Step 3  生成 POI       : 模型产出 MarkerCard（结构化输出）
  Step 4  调用校验工具    : validate_markers 过滤越界/重复
  Step 5  调用 render_map: 渲染交互式 Leaflet HTML
  Step 6  模型自检 summary: 模型用一句话总结本次生成结果

产出的 trace（每步耗时/tokens/工具调用）写入结构化日志，作为本地推理证据。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import AgentConfig
from .llm import GenStats, LocalLLM
from .map_render import render_map
from .schemas import (
    MARKER_SCHEMA_HINT,
    PLAN_SCHEMA_HINT,
    SIAS_CENTER,
    to_markers,
    to_plan,
    validate_markers,
    validate_plan,
)
from .tools import build_default_registry, disperse_markers, geocode
PLAN_SYSTEM = (
    "你是一个本地部署的地图生成 Agent 的规划器。用户会用中文提出一个"
    "「生成某区域地图」的需求。请把它转成一个 JSON 规划，字段："
    "task(任务描述)、place_name(目标地区名称)、center_lat、center_lon"
    "(该地区大致中心经纬度)、marker_count(需要标注的地点数量, 3-10)、"
    "categories(地点类别数组, 如 教学楼/食堂/宿舍/图书馆/地标)。"
    "只输出 JSON。"
)
MARKER_SYSTEM = (
    "你是一个本地地图 POI 生成器。给定地区、中心坐标与类别，请生成真实合理的"
    "地点标注。每个地点必须包含 name(名称)、category(类别)、description(中文一句话简介)、"
    "lat、lon(经纬度, 必须落在给定的中心坐标附近)。只输出 JSON，格式为"
    '{"markers":[...]}。'
)


@dataclass
class AgentTrace:
    query: str
    steps: list[dict] = field(default_factory=list)
    stats: list[dict] = field(default_factory=list)

    def add(self, step: str, detail: dict) -> None:
        self.steps.append({"step": step, "t": round(time.time(), 3), **detail})

    def as_dict(self) -> dict:
        return {"query": self.query, "steps": self.steps}


class MapAgent:
    def __init__(self, config: AgentConfig | None = None, llm: LocalLLM | None = None):
        self.config = config or AgentConfig()
        self.llm = llm or LocalLLM(self.config)
        self.tools = build_default_registry()

    # -- 各步骤 -------------------------------------------------------------
    def plan(self, query: str) -> tuple:
        user = (
            f"用户需求：{query}\n"
            f"参考：若目标地区是「西亚斯 / SIAS 大学」，中心坐标约为 "
            f"{SIAS_CENTER['lat']}, {SIAS_CENTER['lon']}。\n"
            "请输出 JSON 规划。"
        )
        obj, st = self.llm.json_call(PLAN_SYSTEM, user, validate_plan, PLAN_SCHEMA_HINT)
        return to_plan(obj), st

    def geocode_center(self, plan) -> dict:
        return self.tools.call("geocode", place_name=plan.place_name,
                               fallback={"lat": plan.center_lat, "lon": plan.center_lon,
                                         "name": plan.place_name})

    def make_markers(self, plan, center: dict) -> tuple:
        user = (
            f"地区：{plan.place_name}\n中心坐标：{center['lat']}, {center['lon']}\n"
            f"请生成 {plan.marker_count} 个地点，类别从这些里选：{', '.join(plan.categories)}。\n"
            "要求：每个地点的经纬度必须各不相同，围绕中心在 ±0.004 度（约 400 米）内分散分布；"
            "不同地点朝不同方向铺开（有的偏北、有的偏南、有的偏东、有的偏西），"
            "不要所有点共用同一个坐标。\n"
            "经纬度保留到小数点后 4 位。只输出 JSON。"
        )
        want = plan.marker_count
        obj, st = self.llm.json_call(
            MARKER_SYSTEM, user, lambda o: validate_markers(o, want), MARKER_SCHEMA_HINT
        )
        return to_markers(obj), st

    def summarize(self, plan, markers) -> tuple:
        listing = "；".join(m.name for m in markers[:6])
        user = (
            f"我刚为「{plan.place_name}」生成了 {len(markers)} 个地点标注：{listing}。"
            "请用一句中文总结这次生成结果，并指出一个可以改进的点。只输出一句话。"
        )
        return self.llm.chat(
            [{"role": "system", "content": "你是地图生成 Agent 的自检器。"},
             {"role": "user", "content": user}]
        )

    # -- 主循环 -------------------------------------------------------------
    def run(self, query: str, out_html: str | Path, trace_path: str | Path | None = None) -> dict:
        trace = AgentTrace(query=query)
        info = self.llm.info()
        trace.add("load_model", info)

        plan, st1 = self.plan(query)
        trace.add("plan", {"plan": plan.as_dict(), "gen": st1.as_dict()})

        center = self.geocode_center(plan)
        trace.add("tool:geocode", {"input": plan.place_name, "output": center})

        markers, st2 = self.make_markers(plan, center)
        trace.add("generate_markers", {"raw_count": len(markers), "gen": st2.as_dict()})

        markers, moved = disperse_markers(markers, center)
        if moved:
            trace.add("tool:disperse_markers", {"moved": len(moved), "detail": moved})

        kept, dropped = self.tools.call("validate_markers", markers=markers, center=center)
        trace.add("tool:validate_markers", {"kept": len(kept), "dropped": dropped})

        out = render_map(
            kept, title=f"{plan.place_name} 区域地图", center=center, out_path=out_html,
            model=Path(self.config.model_dir).name, device=self.llm.device,
        )
        trace.add("tool:render_map", {"output": str(out), "markers": len(kept)})

        summary, st3 = self.summarize(plan, kept)
        trace.add("self_check", {"summary": summary.strip(), "gen": st3.as_dict()})

        result = {
            "ok": True,
            "query": query,
            "plan": plan.as_dict(),
            "center": center,
            "markers": [m.as_dict() for m in kept],
            "dropped": dropped,
            "map_html": str(out),
            "summary": summary.strip(),
            "model_info": info,
            "trace": trace.as_dict(),
        }
        if trace_path:
            Path(trace_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
