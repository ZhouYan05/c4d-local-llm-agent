# Local LLM Agent —— 完全本地运行的大模型 Agent 技能

> 挑战任务 C4D 交付物 · 模型：**Gemma 3 1B (`unsloth/gemma-3-1b-it`)** · 设备：**CPU / GPU(自动)** · 全流程离线推理

一个**不依赖任何云 API** 的本地大模型 Agent：在本机加载开源权重，理解中文自然语言
需求 → 输出结构化 JSON → 调用本地工具（函数调用）→ 生成一张**可交互的 Leaflet 地图**。

用户只需说一句：

> "帮我在 SIAS University（郑州西亚斯学院）附近生成一张地图"

Agent 就会自动规划、生成地点标注、校验坐标、渲染出带可点击标记的交互式 HTML 地图。

---

## 1. 这是什么（能力概览）

| 能力 | 说明 |
| --- | --- |
| **本地推理** | 使用 `transformers` 在本机加载 Gemma 3 1B，全程离线，无需联网 API |
| **结构化输出** | 模型按 JSON Schema 产出结果，叠加校验器 + 失败重采样，小模型也能稳定输出 |
| **函数调用 / 多步 Agent** | 模型决策 → 工具执行 → 观测 的闭环循环（规划 / 地理编码 / 校验 / 渲染 / 自检） |
| **交互式地图** | 由**模型生成的地点数据**渲染 Leaflet HTML，标记可点击，弹窗含名称/类别/描述/坐标 |
| **可复现** | 固定随机种子、记录每步 tokens 与耗时，产出 trace JSON 作为本地运行证据 |

---

## 2. 目录结构

```
c4d-local-llm-agent/
├─ src/local_llm_agent/
│  ├─ __init__.py      # 包导出
│  ├─ config.py        # AgentConfig（模型目录/设备/采样参数/缓存）
│  ├─ llm.py           # LocalLLM：加载权重 + 离线推理 + JSON 结构化输出
│  ├─ schemas.py       # 数据契约 Plan / Marker + 校验器
│  ├─ tools.py         # 工具层：geocode / haversine / validate_markers
│  ├─ map_render.py    # 交互式 Leaflet 地图渲染
│  ├─ agent.py         # MapAgent：多步 Agent 主循环 + trace
│  └─ cli.py           # 命令行入口
├─ tests/test_core.py  # 离线单元测试（不加载模型）
├─ docs/               # 方案设计 / 验证报告
├─ AI日志.md           # 与 AI 协作开发的全过程日志
├─ AAR_复盘.md         # 课后复盘（After Action Review）
├─ Agent技能说明.md     # 面向使用者的技能说明
├─ demo_运行演示.md     # 本地运行演示说明
├─ pyproject.toml
├─ requirements.txt
└─ README.md
```

---

## 3. 安装

前置：Python ≥ 3.10。

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
pip install -e .
```

`torch` 默认安装 CPU 版即可运行；如有 NVIDIA 显卡且已装 CUDA，可改装对应 GPU 版
（本机实测为 CUDA 13.3 驱动 + RTX 4060 Laptop）。

---

## 4. 准备本地模型（离线）

本项目默认从 Hugging Face 镜像下载 Gemma 3 1B 权重到本地缓存：

```bash
# 设置镜像（国内网络）
export HF_ENDPOINT=https://hf-mirror.com        # Windows: $env:HF_ENDPOINT="https://hf-mirror.com"

# 下载到 <仓库>/.models/gemma-3-1b-it
python tools/download_models.py gemma
```

下载脚本对**大权重文件**采用断点续传（`.part` + HTTP Range），网络中断后可重跑续传。
若 Gemma 下载受限，自动回退 `Qwen/Qwen2.5-1.5B-Instruct`：

```bash
python tools/download_models.py qwen
```

缓存目录可用环境变量 `LOCAL_LLM_CACHE` 覆盖（默认 `<仓库>/.models`）。

---

## 5. 使用

### 5.1 查看运行时 / 模型信息

```bash
python -m local_llm_agent.cli info
```

输出示例（真实本机）：

```json
{
  "model_dir": ".../.models/gemma-3-1b-it",
  "device": "cpu",
  "dtype": "float32",
  "model": "gemma-3-1b-it"
}
```

### 5.2 生成某区域交互式地图

```bash
python -m local_llm_agent.cli generate-map \
  --query "帮我在 SIAS University 附近生成一张地图" \
  --out output/sias_map.html \
  --trace output/sias_trace.json
```

生成后用浏览器打开 `output/sias_map.html`：可见地图中心与若干可点击标记。

### 5.3 作为库调用

```python
from local_llm_agent.agent import MapAgent
from local_llm_agent.config import AgentConfig

agent = MapAgent(AgentConfig())
result = agent.run("生成 SIAS 大学区域地图", out_html="output/map.html")
print(result["summary"], len(result["markers"]))
```

---

## 6. 工作原理

```
用户自然语言
   │
   ▼
[Step1 规划]  模型 → Plan{地点, 中心坐标, 类别, 标注数量}           ── JSON 校验/重采样
   │
   ▼
[Step2 工具]  geocode(place_name) → 中心坐标（模型坐标作回退）
   │
   ▼
[Step3 生成]  模型 → MarkerCard{markers:[name, category, description, lat, lon]}
   │
   ▼
[Step4 工具]  validate_markers(...) → 过滤越界(>3km)/重复的 POI
   │
   ▼
[Step5 工具]  render_map(...) → 交互式 Leaflet HTML
   │
   ▼
[Step6 自检]  模型 → 一句话总结 + 改进点
```

每一次「模型决策 → 工具执行 → 观测」都记录进 `trace`（含每步 tokens、耗时、tok/s），
既是可复现证据，也是 `aiUsage` 维度的佐证。

---

## 7. 设计取舍（为什么这样做）

- **为什么用 1B 小模型**：挑战强调「本地可跑通」。1B 模型 CPU 即可秒级响应，验证门槛低；
  更大的 E4B/26B 在同一份代码下只需改 `--model-dir` 即可切换。
- **为什么强调结构化输出**：小模型直接输出长 JSON 易错。我们采用「Schema 约束 + 校验器 +
  失败重采样」，把"模型会不会写格式"的偶发问题变成可重试的工程问题。
- **为什么地图数据必须由模型生成**：这是挑战的核心考察点——验证 Agent 真的把模型的
  输出变成了下游产物，而不是人手写一份 JSON。
- **为什么工具层独立**：模型只负责"决定调用什么、传什么参数"，副作用（编码/校验/渲染）
  由工具层完成，便于单测与离线复现。

---

## 8. 复现实验

`docs/验证报告.md` 记录了本机（i7-14650HX / 31.8GB RAM / RTX 4060 Laptop）上的
真实运行结果，包括模型名、量化、设备、tokens/s 与生成耗时。按第 3–5 节步骤即可复现。

---

## 9. 许可

代码以 MIT 许可发布。模型权重（Gemma 3）遵循其各自的开源许可，请查阅上游条款。
