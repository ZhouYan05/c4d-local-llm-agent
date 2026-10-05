"""local_llm_agent — 一个完全本地运行的大模型 Agent 技能工具箱。

核心能力：
  * 本地加载开源权重模型（默认 Gemma 3 1B），CPU/GPU 均可，离线推理；
  * 结构化输出（JSON Schema 约束）+ 工具调用（function calling）多步 Agent 循环；
  * 内置工具：地理编码、POI 生成、交互式 Leaflet 地图渲染；
  * CLI 可复现：`python -m local_llm_agent.cli generate-map --query ...`

作者：2024102310451
"""
from .config import AgentConfig
from .llm import LocalLLM
from .agent import MapAgent
from .tools import ToolRegistry

__all__ = ["AgentConfig", "LocalLLM", "MapAgent", "ToolRegistry"]
__version__ = "1.0.0"
