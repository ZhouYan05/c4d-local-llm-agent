# -*- coding: utf-8 -*-
"""端到端演示：用本地 Gemma 3 1B 驱动多步地图 Agent。

单独用脚本（而非把中文参数传命令行）是为了规避 Windows 命令行编码问题。
运行： PYTHONPATH=src python scripts/run_demo.py
"""
import json
import sys
from pathlib import Path

from local_llm_agent.config import AgentConfig
from local_llm_agent.agent import MapAgent

MODEL_DIR = r"D:\.cogseed\userWorkSpace\完成挑战任务c4d\.models\gemma-3-1b-it"
QUERY = "帮我在郑州西亚斯学院（SIAS University）附近生成一张地图，标注教学楼、食堂、宿舍、图书馆、体育馆等地标。"


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    out = repo / "output" / "sias_map.html"
    trace = repo / "output" / "sias_trace.json"
    out.parent.mkdir(parents=True, exist_ok=True)

    cfg = AgentConfig(model_dir=MODEL_DIR)
    agent = MapAgent(cfg)
    print(f"[demo] 模型目录：{MODEL_DIR}", file=sys.stderr)
    print(f"[demo] 设备：{cfg.resolve_device()} / dtype={cfg.dtype}", file=sys.stderr)

    result = agent.run(QUERY, out_html=out, trace_path=trace)
    brief = {k: result[k] for k in ("ok", "query", "map_html", "summary")}
    brief["markers"] = len(result["markers"])
    print(json.dumps(brief, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
