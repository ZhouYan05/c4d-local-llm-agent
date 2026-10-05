"""命令行入口：`python -m local_llm_agent.cli generate-map --query "..."`。

示例：
  python -m local_llm_agent.cli info
  python -m local_llm_agent.cli generate-map \
      --query "帮我在 SIAS University 附近生成一张地图" \
      --out output/sias_map.html \
      --trace output/sias_trace.json
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import AgentConfig
from .agent import MapAgent


def _make_config(args) -> AgentConfig:
    """只把显式提供的参数传给 AgentConfig，避免用 None 覆盖默认值。"""
    kwargs = {}
    if args.model_dir:
        kwargs["model_dir"] = args.model_dir
    if args.device:
        kwargs["device"] = args.device
    return AgentConfig(**kwargs)


def _cmd_info(args) -> int:
    from .llm import LocalLLM

    cfg = _make_config(args)
    llm = LocalLLM(cfg)
    print(json.dumps(llm.info(), ensure_ascii=False, indent=2))
    return 0


def _cmd_generate_map(args) -> int:
    cfg = _make_config(args)
    agent = MapAgent(cfg)
    print(f"[agent] 加载本地模型：{cfg.model_dir}", file=sys.stderr)
    result = agent.run(args.query, out_html=args.out, trace_path=args.trace)
    print(f"[agent] 生成 {len(result['markers'])} 个地点 -> {result['map_html']}", file=sys.stderr)
    print(json.dumps({k: result[k] for k in ("ok", "query", "map_html", "summary")},
                     ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="local_llm_agent", description="本地大模型 Agent 技能 CLI")
    p.add_argument("--model-dir", default=None, help="本地模型目录（默认取缓存目录）")
    p.add_argument("--device", default=None, help="cpu / cuda / auto（默认 auto）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("info", help="打印运行时与模型信息")
    sp.set_defaults(func=_cmd_info)

    sp = sub.add_parser("generate-map", help="生成某区域交互式地图")
    sp.add_argument("--query", required=True, help="自然语言需求")
    sp.add_argument("--out", default="output/map.html", help="输出地图 HTML 路径")
    sp.add_argument("--trace", default=None, help="输出 trace JSON 路径")
    sp.set_defaults(func=_cmd_generate_map)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
