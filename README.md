# Git 仓库接入体检工具

输入公开 GitHub 仓库链接，自动检测接入风险并给出就绪度评分（满分 100，>80 就绪）与 AI 建议。

## 技术栈

- 后端：FastAPI + uvicorn + pydantic，DeepSeek API（`deepseek-chat`）生成 AI 建议
- 前端：Vue 3 + Vite + ECharts

## 检测项与权重

| 检测项 | 满分 | 扣分规则 |
|---|---|---|
| 密钥与敏感信息 | 40 | `sk-`/`AKID`/Bearer/私钥/.env 入库，每处 10–20 分 |
| Windows 专用脚本 | 25 | `.ps1` 10 分、`.bat`/`.cmd` 8 分、`.vbs` 5 分 |
| 硬编码路径 | 20 | `C:\`、`/Users/`、`/home/`、`/opt/`、UNC 路径，每处 5 分 |
| 文档与脚本完整度 | 15 | README 8 分（存在 3 + 描述 2 + 启动 3）、依赖清单 4 分、启动脚本 3 分 |

误报控制：跳过二进制/大文件与 lock 文件；文档示例、Dockerfile 内部路径、测试目录不计分；占位符（`your-*`、`sk-xxxx` 等）过滤；同一文件同一行同类问题只扣一次。测试资源中的凭证保留为 `info` 级 finding 供审计，但不扣分。

## 本地运行

```bash
# 后端（首次需安装依赖）
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
# 配置 DeepSeek Key（二选一）
#   1) 复制 backend/.env.example 为 backend/.env，填入你的 DEEPSEEK_API_KEY
#   2) 或在启动前设置系统环境变量 DEEPSEEK_API_KEY
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端（另一个终端）
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173 。前端已配置 `/api` 代理到 `http://localhost:8000`。

## 接口

- `GET /api/health` — 健康检查与 AI 启用状态
- `POST /api/analyze` — 请求体 `{"repo_url": "...", "use_ai": true}`，返回结构化分析结果
- `GET /api/report/{report_id}` — 独立的 HTML 报告页

## 服务端安全配置（可选）

通过环境变量或 `backend/.env` 配置：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `API_TOKEN` | 空 | 配置后 `/api/analyze` 需携带 `Authorization: Bearer <token>` |
| `CORS_ORIGINS` | 本地 5173 端口 | 允许的来源，逗号分隔 |
| `RATE_LIMIT_PER_MIN` | 10 | 单 IP 每分钟请求上限（含失败请求，防 Token 爆破） |
| `MAX_CONCURRENT_ANALYSIS` | 3 | 同时分析的最大仓库数 |
| `REPORT_TTL_SEC` | 3600 | 报告缓存有效期（秒） |
| `REPORT_MAX_ENTRIES` | 500 | 报告缓存最大条数 |
| `MAX_REPO_SIZE_MB` | 100 | 单仓库体积上限 |
| `MAX_SCAN_FILES` | 5000 | 单仓库扫描文件数上限 |
| `MAX_FILE_SIZE_MB` | 2 | 单文件大小上限 |
| `CLONE_TIMEOUT_SEC` | 120 | 克隆超时（秒） |

所有配置项均通过 `os.getenv` 读取，非法整数自动回退默认值。详见 `backend/.env.example`。

## Docker 单镜像部署

Dockerfile 已包含前端构建与静态托管，单容器即可提供完整服务：

```bash
docker build -t git-repo-checkup .
docker run -p 8000:8000 --env-file backend/.env git-repo-checkup
```

访问 `http://localhost:8000/` 即为前端页面，`/api/*` 为后端接口。本地开发仍用前后端分离模式（Vite 5173 + uvicorn 8000）。

## 更新跟踪（设计说明，尚未实现）

> 本节是设计提案，描述"原仓库后续有代码更新时如何处理"。当前版本**未实现**以下任何机制：每次 `POST /api/analyze` 都是全新浅克隆 + 全量扫描，结果不记录 commit，报告缓存仅存在于进程内存（TTL 1 小时，重启即失效）。

### 现状与目标的差距

| 能力 | 当前实现 | 设计目标 |
|---|---|---|
| 发现更新 | 无检测，每次都全量重扫 | 用 commit SHA 比对，命中则复用报告 |
| 缓存粒度 | 按随机 `report_id`，内存字典 | 按 `repo + commit_sha`，持久化 |
| commit 标注 | 无 | 报告显式标注所基于的 commit |
| 失败兜底 | 直接报错或 429 | 返回带 stale 标记的上次报告 |

### 1. 怎么发现更新

用 `git ls-remote <url> HEAD` 只读取远端 HEAD 的 commit SHA，**不下载代码**，开销为一次轻量网络请求。将 SHA 与该仓库上次报告的 `commit_sha` 比对：

- **相同** → 源码未变，直接返回缓存报告，零重算；
- **不同** → 有新提交，触发增量更新流程。

可选增强：注册 GitHub `push` webhook，在代码推送时主动标记缓存失效，让用户发起请求前就完成刷新。webhook 需配置密钥校验，且不应把仓库内容暴露给未授权请求。

### 2. 怎么避免全量重算

采用**文件级缓存 + 分类级重新聚合**的三级策略：

1. **SHA 命中**：直接返回整份缓存报告，不跑任何检测。
2. **SHA 变化**：只克隆新快照，用 `git diff --name-only <old_sha> <new_sha>` 取得变更文件列表；仅对变更文件重跑检测规则，未变更文件复用其 findings（按文件路径索引缓存）。
3. **重新聚合**：把新旧 findings 合并后重新计算分类得分与总分。注意两个全局耦合点——
   - 完整度项依赖"README / 依赖清单 / 启动脚本是否存在"，若变更涉及这些文件的增删，需重判；
   - 硬编码路径按"命中文件数 / 总文件数"的密度扣分，文件总数变化时即便 findings 未变也必须重算密度分。

缓存介质从内存字典改为 SQLite（以 `repo + commit_sha` 为主键），进程重启后仍可复用；同时保留 TTL 与容量上限，避免无限增长。

### 3. 报告如何标注所基于的 commit

在结果模型与报告中新增以下字段：

- `commit_sha`：完整 40 位哈希，用于精确比对与缓存键；
- `commit_short`：前 7 位，用于界面展示；
- `commit_url`：`https://github.com/{owner}/{repo}/commit/{sha}`，可直接跳转；
- `commit_date`：该 commit 的提交时间；
- `analyzed_at`：本次分析时间（与 commit 时间区分）；
- `stale`：布尔值，标记报告是否基于非最新 commit。

报告页顶部展示 `commit_short` 链接与"分析于 xxx"的时间戳；当 `stale=true` 时以醒目样式提示"仓库已有新提交，本报告基于旧版本"。前端风险清单的每条 finding 保留文件路径与行号，便于按 commit 定位。

### 4. 失败或限流时怎么兜底

按"是否有可用旧报告"分两条路径：

- **有缓存**：当 `ls-remote` 失败、克隆失败、GitHub 限流或服务端自身触发 429 时，返回最近一份有效报告，置 `stale=true`，并在响应中附带 `error` 字段说明原因（如"GitHub 限流，返回上次分析结果"）。绝不把旧报告伪装成最新结果。
- **无缓存**：返回明确错误（区分"仓库不存在或非公开"、"网络超时"、"服务限流，请稍后重试"），并给出 `Retry-After` 响应头供客户端退避重试。

其他约束：AI 建议失败继续降级（现有行为已实现，不依赖 AI 返回规则结果）；兜底返回的旧报告仍受鉴权与限流保护；后台异步刷新队列可选——先立即返回旧报告并触发刷新，下次请求即可拿到新结果，避免用户等待完整扫描。

## 说明

- 仅支持 `https://github.com/owner/repo` 形式的公开仓库，拒绝本地路径、SSH 与带凭据 URL。
- 克隆采用 `--depth 1` 浅克隆，单文件上限 2MB，单仓库 5000 文件 / 100MB 上限。
- 密钥检测基于字符串匹配，存在误报/漏报可能，请人工复核。
- `.env` 已加入 `.gitignore`，密钥不会随代码入库。
- `POST /api/analyze` 和 `GET /api/report/{id}` 均受 IP 限流保护；报告缓存 1 小时后过期。
