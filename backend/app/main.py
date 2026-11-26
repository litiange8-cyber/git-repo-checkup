"""FastAPI 入口：提供分析接口、AI 建议与 HTML 报告导出。"""
import uuid
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .config import READY_THRESHOLD, TOTAL_SCORE, DEEPSEEK_API_KEY
from .models import AiResult, AnalyzeRequest, AnalyzeResult
from .services.repo import scan_repo, RepoError
from .services.detector import detect_all
from .services.ai import get_ai_advice
from .services.report import render_report

app = FastAPI(title="Git 仓库接入体检工具", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

REPORTS: dict[str, AnalyzeResult] = {}


@app.get("/api/health")
def health():
    return {"status": "ok", "ai_enabled": bool(DEEPSEEK_API_KEY)}


@app.post("/api/analyze", response_model=AnalyzeResult)
def analyze(req: AnalyzeRequest):
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

        result = AnalyzeResult(
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
        report_id = uuid.uuid4().hex[:12]
        result.report_id = report_id
        REPORTS[report_id] = result
        return result
    except RepoError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析过程出错：{str(e)[:300]}")
    finally:
        if scan:
            scan.cleanup()


@app.get("/api/report/{report_id}", response_class=HTMLResponse)
def get_report(report_id: str):
    result = REPORTS.get(report_id)
    if not result:
        raise HTTPException(status_code=404, detail="报告不存在或已过期，请重新分析")
    return HTMLResponse(content=render_report(result))
