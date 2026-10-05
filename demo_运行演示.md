# 运行演示 —— 从一句中文需求到一张交互式地图

本文件记录**一次真实、可复现的端到端演示**：本地 Gemma-3-1B 模型在纯 CPU 上理解一句
中文需求，经过规划 → 地理编码 → 生成地点 → 坐标分散 → 校验 → 渲染，输出一张可交互的
地图 HTML。所有数字都来自 `output/sias_trace.json` 与 `output/run3.out`。

## 1. 运行命令

```powershell
cd c4d-local-llm-agent
$env:PYTHONPATH = "src"
$env:LOCAL_LLM_CACHE = "<仓库外>/.models"   # 内含 gemma-3-1b-it/
python scripts/run_demo.py
```

`scripts/run_demo.py` 中的需求：

> 帮我在郑州西亚斯学院（SIAS University）附近生成一张地图，标注教学楼、食堂、宿舍、图书馆、体育馆等地标。

## 2. Agent 主循环（8 步，trace 逐步可查）

```
load_model        # 加载本地 gemma-3-1b-it（CPU/float32）
plan              # 模型解析意图 → 任务/地区/中心/类别/点位数量
tool:geocode      # 离线地名库命中中心 34.504, 113.7466
generate_markers  # 模型生成 6 个地点卡片（名称/类别/中文简介）
tool:disperse_markers  # 检测到 6 点坐标重合 → 确定性环形铺开
tool:validate_markers  # 过滤越界/重复（本轮 dropped=[]）
tool:render_map        # 写出 Leaflet 交互式 HTML
self_check        # 模型用一句话总结
```

## 3. 实测性能（纯 CPU）

| 步骤 | prompt_tokens | new_tokens | 秒 | tok/s |
| --- | --- | --- | --- | --- |
| plan | 195 | 111 | 16.51 | 6.72 |
| generate_markers | 226 | 467 | 68.70 | 6.80 |
| self_check | 94 | 45 | 6.94 | 6.49 |

模型 `gemma-3-1b-it`，参数 999,885,952（1.00B），设备 `cpu`，dtype `float32`，全程离线推理。

## 4. 模型生成的结果

Plan：任务「生成地图」，地点「西亚斯 / SIAS 大学」，类别 `[教学楼, 食堂, 宿舍, 图书馆, 体育馆]`，点位 6 个。

| 地点 | 纬度 | 经度 |
| --- | --- | --- |
| 西亚斯大学教学楼 | 34.5062 | 113.7466 |
| 西亚斯大学食堂 | 34.5051 | 113.7490 |
| 西亚斯大学宿舍区 | 34.5029 | 113.7490 |
| 西亚斯大学图书馆 | 34.5018 | 113.7466 |
| 西亚斯大学体育馆 | 34.5029 | 113.7442 |
| 西亚斯大学学生宿舍 | 34.5051 | 113.7442 |

自检总结（模型原文）：

> 生成了西亚斯大学的六个地点标注，但可以考虑更详细地描述每个地点，例如，教学楼、食堂、宿舍区、图书馆、体育馆和学生宿舍的具体位置和功能。

## 5. 产物

| 文件 | 说明 |
| --- | --- |
| `output/sias_map.html` | 交互式地图：Leaflet + OSM 瓦片，6 个 marker，点击弹窗显示类别与简介 |
| `output/sias_trace.json` | 全流程结构化 trace（每步耗时/tokens/工具输入输出） |
| `output/run3.out` | 本次运行完整日志 |

在浏览器打开 `output/sias_map.html` 即可看到地图与 6 个地点标注。
> 注：底图瓦片与 Leaflet 组件来自 CDN，显示底图需要联网；**模型推理与数据生成完全离线**。

## 6. 演示看点

1. **真·本地模型**：1B 模型在 CPU 上跑，非 API 调用。
2. **多步 Agent + 工具调用**：模型输出驱动地理编码、校验、渲染等工具。
3. **失败可见、可修正**：首轮 6 点坐标完全重叠，改提示词无效后，用确定性工具
   `disperse_markers` 铺开，并在 trace 中如实记录 `tool:disperse_markers`（moved=6）。
