"""本地大模型封装：加载开源权重 + 离线推理 + JSON 结构化输出。

设计要点
--------
* 使用 `transformers` 在本地加载（默认 Gemma 3 1B），设备与精度可配置；
* `chat()` 走 tokenizer 的 chat template，保证与指令微调模型对齐；
* `json_call()` 在 chat 之上叠加「JSON Schema 约束 + 校验 + 重采样」，
  使小参数模型也能稳定产出可被程序消费的结构化结果（Agent 的工具调用基础）。
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from .config import AgentConfig


@dataclass
class GenStats:
    """单次生成的性能统计，用于在日志中提供真实本地推理证据。"""

    prompt_tokens: int = 0
    new_tokens: int = 0
    seconds: float = 0.0

    @property
    def tok_per_s(self) -> float:
        return self.new_tokens / self.seconds if self.seconds > 0 else 0.0

    def as_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "new_tokens": self.new_tokens,
            "seconds": round(self.seconds, 3),
            "tok_per_s": round(self.tok_per_s, 2),
        }


class LocalLLM:
    """一个最小的本地 LLM 客户端。"""

    def __init__(self, config: AgentConfig | None = None):
        self.config = config or AgentConfig()
        self._model = None
        self._tokenizer = None
        self.stats: list[GenStats] = []

    # ---- 加载 -------------------------------------------------------------
    def load(self) -> "LocalLLM":
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        device = self.config.resolve_device()
        dtype = getattr(torch, self.config.dtype)
        path = str(self.config.model_path)
        self._tokenizer = AutoTokenizer.from_pretrained(path)
        self._model = AutoModelForCausalLM.from_pretrained(
            path, torch_dtype=dtype, low_cpu_mem_usage=True
        )
        self._model.to(device)
        self._model.eval()
        self.device = device
        return self

    def info(self) -> dict[str, Any]:
        import torch

        if self._model is None:
            self.load()
        n = sum(p.numel() for p in self._model.parameters())
        return {
            "model_path": str(self.config.model_path),
            "device": self.device,
            "dtype": self.config.dtype,
            "parameters": n,
            "parameters_human": f"{n/1e9:.2f}B",
            "torch": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
        }

    # ---- 推理 -------------------------------------------------------------
    def chat(self, messages: Sequence[dict], **overrides) -> tuple[str, GenStats]:
        import torch

        if self._model is None:
            self.load()
        cfg = self.config
        max_new = overrides.get("max_new_tokens", cfg.max_new_tokens)
        temperature = overrides.get("temperature", cfg.temperature)
        do_sample = overrides.get("do_sample", cfg.do_sample)

        torch.manual_seed(cfg.seed)
        text = self._tokenizer.apply_chat_template(
            list(messages), tokenize=False, add_generation_prompt=True
        )
        inputs = self._tokenizer(text, return_tensors="pt").to(self.device)
        t0 = time.time()
        with torch.no_grad():
            out = self._model.generate(
                **inputs,
                max_new_tokens=max_new,
                do_sample=do_sample,
                temperature=max(temperature, 1e-3),
                top_p=cfg.top_p,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        dt = time.time() - t0
        new_ids = out[0][inputs["input_ids"].shape[1]:]
        content = self._tokenizer.decode(new_ids, skip_special_tokens=True)
        st = GenStats(
            prompt_tokens=int(inputs["input_ids"].shape[1]),
            new_tokens=int(new_ids.shape[0]),
            seconds=dt,
        )
        self.stats.append(st)
        return content, st

    # ---- 结构化输出 -------------------------------------------------------
    def json_call(
        self,
        system: str,
        user: str,
        validator: Callable[[dict], bool],
        schema_hint: str,
        **overrides,
    ) -> tuple[dict, GenStats]:
        """让模型输出 JSON，并用 ``validator`` 校验，不合法则重采样。

        Returns: (parsed_obj, last_stats)
        """
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        last_err = None
        for attempt in range(self.config.max_retries):
            raw, st = self.chat(messages, **overrides)
            obj = extract_json(raw)
            if obj is not None and validator(obj):
                return obj, st
            last_err = raw[-400:] if raw else "(empty)"
            # 把失败原因反馈给模型，进行下一轮修正
            messages += [
                {"role": "assistant", "content": raw.strip()[:1200]},
                {
                    "role": "user",
                    "content": (
                        "你上一次的输出不是合法的 JSON 或不满足约束。"
                        f"约束如下：{schema_hint}\n"
                        "请只输出一个 JSON 对象，不要任何解释、Markdown 代码块或多余文字。"
                    ),
                },
            ]
        raise ValueError(f"模型连续 {self.config.max_retries} 次未产出合法 JSON；最后一次输出：{last_err}")


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> dict | None:
    """从模型输出里稳健地抽出第一个 JSON 对象。"""
    if not text:
        return None
    candidates = []
    m = _FENCE_RE.search(text)
    if m:
        candidates.append(m.group(1))
    candidates.append(text)
    # 括号配对扫描
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : i + 1])
                    break
    for cand in candidates:
        try:
            obj = json.loads(cand.strip())
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None
