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

## 说明

- 仅支持 `https://github.com/owner/repo` 形式的公开仓库，拒绝本地路径、SSH 与带凭据 URL。
- 克隆采用 `--depth 1` 浅克隆，单文件上限 2MB，单仓库 5000 文件 / 100MB 上限。
- 密钥检测基于字符串匹配，存在误报/漏报可能，请人工复核。
- `.env` 已加入 `.gitignore`，密钥不会随代码入库。
- `POST /api/analyze` 和 `GET /api/report/{id}` 均受 IP 限流保护；报告缓存 1 小时后过期。
