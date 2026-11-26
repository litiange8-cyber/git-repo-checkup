# AI 使用说明

本文档说明本项目中 AI 的使用范围、边界，以及如何验证 AI 输出。核心原则：**AI 只提供建议，不决定评分**。

## 一、使用了哪些 AI 工具

| 工具 | 用途 | 是否影响评分 | 接入位置 |
|---|---|---|---|
| DeepSeek API（`deepseek-chat`） | 生成接入建议、给出独立的参考评分 | 否 | `backend/app/services/ai.py` |

调用方式：通过 `openai` SDK 以 OpenAI 兼容接口访问，默认地址 `https://api.deepseek.com`，模型 `deepseek-chat`。API Key 从环境变量 `DEEPSEEK_API_KEY`（或 `backend/.env`）读取，未配置时自动跳过 AI 建议，不影响主流程。

## 二、AI 的职责边界

1. **评分由确定性规则计算，AI 不参与。** `total_score` 由四类检测项的扣分规则求和得出（`backend/app/services/detector.py`），AI 返回的 `score` 仅作为参考值展示，不写入 `total_score`，不改变就绪判定（就绪只看 `total_score > 80`）。
2. **AI 的输入是结构化的体检结果**，而非原始仓库代码。传给模型的只有：仓库名、总分、四项分类得分、风险清单摘要（最多 40 条）。代码正文不发送给 AI。
3. **AI 输出经过约束与截断**：要求返回 JSON（`response_format=json_object`），温度 0.3；`summary` 截断到 500 字，`suggestions` 最多 5 条、每条 300 字。
4. **失败即降级**：网络错误、额度不足、返回格式异常时，捕获异常并将 `ai.enabled` 置为 false，附带错误原因；接口仍返回完整的规则分析结果。

## 三、如何验证 AI 输出

AI 输出属于建议性质，无需（也不应）直接信任。以下是可操作的验证手段。

### 1. 对照确定性评分

将 AI 给出的 `score`（`ai.score`）与规则评分 `total_score` 对比：

```bash
curl -s -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/owner/repo","use_ai":true}'
```

两者若出现显著差异（例如规则 90 分、AI 60 分），应视为 AI 的误判信号，以规则评分为准，并检查 AI 的 `summary` 是否指出了规则未覆盖的真实问题。

### 2. 检查建议是否可追溯到具体 finding

每条有效建议应能对应到风险清单中的具体条目（文件、行号、问题）。例如建议"移除硬编码路径"时，风险清单中应有对应的 `hardcoded` 条目及文件路径。无法对应的建议视为泛泛而谈，忽略即可。

### 3. 关闭 AI 做 A/B 对照

请求体设置 `"use_ai": false`，对比两次结果。规则评分、分类得分、风险清单在两次请求中应完全一致——若不一致，说明存在非 AI 引入的确定性缺陷，应排查规则引擎。

### 4. 单元测试回归

后端 13 项单元测试覆盖四类检测规则与误报回归（含测试证书不扣分、URL 不误判为盘符路径、测试目录豁免、各类密钥格式识别）：

```bash
cd backend
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

这些测试验证的是规则引擎（即评分来源），不依赖 AI，也不受 API Key 影响。

### 5. 真实仓库基准

以下仓库可作为评分基准，用于验证规则引擎的稳定性（历史验证值）：

| 仓库 | 基准总分 | 说明 |
|---|---|---|
| `psf/requests` | 92 | 测试目录的私钥证书以 info 级保留，不扣分 |
| `huggingface/transformers` | 92 | Dockerfile 系统路径、Jinja/LaTeX 转义不计入硬编码 |
| `Renhuai123/ziwei-doushu` | 85 | 2 处 `/opt/homebrew` 绝对路径，中风险 |

若同一仓库多次扫描分数波动，说明规则存在非确定性，需排查。

### 6. 验证降级路径

未配置 `DEEPSEEK_API_KEY` 时启动服务，`GET /api/health` 应返回 `"ai_enabled": false`；执行分析后 `result.ai.enabled` 应为 false，`result.total_score` 仍正常计算。这验证了 AI 不可用不会影响核心功能。

## 四、已知局限

1. **模型判断具有不确定性**：相同输入在不同调用中可能给出不同措辞或评分（temperature 0.3 仍有随机性）。因此 AI 评分不作为自动化决策依据。
2. **无事实核验机制**：AI 不会重新读取仓库源码来验证其建议，建议基于已结构化的摘要生成，可能与仓库实际情况有偏差。
3. **摘要截断**：风险清单只传前 40 条，AI 看不到完整清单；因此 AI 可能遗漏后续风险。
4. **提示注入面**：AI 的输入中包含仓库名和文件名/路径（`finding.file`）。恶意仓库可通过构造特殊文件名试图影响模型输出，但无法影响规则评分与就绪判定。建议人工审阅 AI 输出中的异常表述。
5. **API 成本与延迟**：每次 `use_ai=true` 的请求都会产生一次外部 API 调用（超时 60 秒）。生产环境建议配置 API Token 与限流，避免滥用。

## 五、配置参考

```bash
# backend/.env
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com   # 可选，默认值
DEEPSEEK_MODEL=deepseek-chat                  # 可选，默认值
```

不配置任何 AI 参数时，工具仍可完整运行——只是没有 AI 建议部分。
