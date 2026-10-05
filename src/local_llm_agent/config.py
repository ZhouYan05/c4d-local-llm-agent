"""配置对象：模型路径、设备、采样参数、缓存目录。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_cache() -> Path:
    env = os.environ.get("LOCAL_LLM_CACHE")
    if env:
        return Path(env)
    # 默认仓库上级目录的 .models（与 tools/direct_download.py 一致）
    return Path(__file__).resolve().parents[2] / ".models"


@dataclass
class AgentConfig:
    """Agent 运行配置。所有字段都有可离线复现的默认值。"""

    model_dir: str = field(
        default_factory=lambda: str(_default_cache() / "gemma-3-1b-it")
    )
    device: str = "auto"          # auto | cpu | cuda
    dtype: str = "float32"        # float32 | float16 | bfloat16
    max_new_tokens: int = 640
    temperature: float = 0.4
    top_p: float = 0.9
    seed: int = 20260717
    do_sample: bool = True
    # 结构化输出的最大重试次数（模型输出不合法时重新采样）
    max_retries: int = 3

    @property
    def model_path(self) -> Path:
        return Path(self.model_dir)

    def resolve_device(self) -> str:
        if self.device != "auto":
            return self.device
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"
