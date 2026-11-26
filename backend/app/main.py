"""FastAPI 入口：提供分析接口、AI 建议与 HTML 报告导出。"""
import asyncio
import hmac
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import (
    API_TOKEN, CORS_ORIGINS, DEEPSEEK_API_KEY, MAX_CONCURRENT_ANALYSIS,
    RATE_LIMIT_PER_MIN, READY_THRESHOLD, REPORT_MAX_ENTRIES, REPORT_TTL_SEC, TOTAL_SCORE,
)
from .models import AiResult, AnalyzeRequest, AnalyzeResult
from .services.repo import scan_repo, RepoError
from .services.detector import detect_all
from .services.ai import get_ai_advice
from .services.report import render_report

app = FastAPI(title="Git 仓库接入体检工具", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# ---- 报告缓存（带 TTL 与容量上限）----
REPORTS: dict[str, tuple[float, AnalyzeResult]] = {}
_report_lock = threading.Lock()


def _store_report(result: AnalyzeResult) -> str:
    report_id = uuid.uuid4().hex[:12]
    now = time.time()
    with _report_lock:
        # 惰性清理过期项
        expired = [k for k, (ts, _) in REPORTS.items() if now - ts > REPORT_TTL_SEC]
        for k in expired:
            del REPORTS[k]
        # 容量上限：超限时删除最旧的
        if len(REPORTS) >= REPORT_MAX_ENTRIES:
            oldest = min(REPORTS, key=lambda k: REPORTS[k][0])
            del REPORTS[oldest]
        REPORTS[report_id] = (now, result)
    return report_id


# ---- 并发闸门（扫描为同步阻塞，放线程池 + 信号量限流）----
_analysis_semaphore = asyncio.Semaphore(MAX_CONCURRENT_ANALYSIS)

# ---- IP 频率限制（滑动窗口）----
_rate_window: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = threading.Lock()


def _check_rate_limit(ip: str):
    now = time.time()
    with _rate_lock:
        window = _rate_window[ip]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= RATE_LIMIT_PER_MIN:
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
        window.append(now)


# ---- 可选 API Token 鉴权 ----
def verify_auth(authorization: str | None = Header(default=None)):
    if not API_TOKEN:
        return  # 未配置 Token 时开放访问（本地开发默认）
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="需要 Bearer Token")
    if not hmac.compare_digest(authorization[7:].strip(), API_TOKEN):
        raise HTTPException(status_code=403, detail="Token 无效")


@app.get("/api/health")
def health():
    return {"status": "ok", "ai_enabled": bool(DEEPSEEK_API_KEY)}


async def _run_analysis(req: AnalyzeRequest) -> AnalyzeResult:
    """在线程池中执行阻塞的克隆与扫描，受信号量约束。"""
    async with _analysis_semaphore:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _analyze_sync, req)


def _analyze_sync(req: AnalyzeRequest) -> AnalyzeResult:
    url = req.repo_url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="请输入仓库链接")

    scan = None
    try:
        scan = scan_repo(url)
        categories, findings = detect_all(scan.files)
        total = int(sum(c.score for c in categories))
        total = max(0, min(TOTAL_SCORE, total))
        ready = total > READY_THRESHOLD

        ai = get_ai_advice(scan.repo_name, total, categories, findings, ready) if req.use_ai else \
            AiResult(enabled=False, error="用户未启用 AI 建议")

        return AnalyzeResult(
            repo_url=url,
            repo_name=scan.repo_name,
            total_score=total,
            ready=ready,
            threshold=READY_THRESHOLD,
            categories=categories,
            findings=findings,
            ai=ai,
            scanned_files=scan.scanned_files,
            skipped_files=scan.skipped_files,
            generated_at=datetime.now().isoformat(timespec="seconds"),
        )
    except RepoError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        # 不回显内部异常细节，避免信息泄露
        raise HTTPException(status_code=500, detail="分析过程出错，请稍后重试")
    finally:
        if scan:
            scan.cleanup()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@app.post("/api/analyze", response_model=AnalyzeResult)
async def analyze(req: AnalyzeRequest, request: Request, authorization: str | None = Header(default=None)):
    # 限流前置：失败请求（401/403）同样计入配额，防止 Token 爆破
    _check_rate_limit(_client_ip(request))
    verify_auth(authorization)
    result = await _run_analysis(req)
    result.report_id = _store_report(result)
    return result


@app.get("/api/report/{report_id}", response_class=HTMLResponse)
def get_report(report_id: str, request: Request):
    _check_rate_limit(_client_ip(request))
    with _report_lock:
        entry = REPORTS.get(report_id)
    if not entry:
        raise HTTPException(status_code=404, detail="报告不存在或已过期，请重新分析")
    ts, result = entry
    if time.time() - ts > REPORT_TTL_SEC:
        with _report_lock:
            REPORTS.pop(report_id, None)
        raise HTTPException(status_code=404, detail="报告已过期，请重新分析")
    return HTMLResponse(content=render_report(result))


# ---- 托管前端静态资源（Docker 单镜像部署）----
# 路径：项目根/frontend/dist；本地开发时该目录可能不存在，跳过挂载
_STATIC_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="frontend")
