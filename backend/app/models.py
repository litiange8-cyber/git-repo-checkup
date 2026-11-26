from typing import Any, Optional
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    repo_url: str = Field(..., description="公开 Git 仓库链接（GitHub）")
    use_ai: bool = Field(True, description="是否调用 DeepSeek 生成 AI 建议")


class Finding(BaseModel):
    category: str
    severity: str          # high / medium / low / info
    file: str
    line: Optional[int] = None
    message: str
    snippet: Optional[str] = None


class CategoryResult(BaseModel):
    key: str
    name: str
    score: float           # 该项得分（扣后）
    max_score: float
    details: list[str] = Field(default_factory=list)


class AiResult(BaseModel):
    enabled: bool = False
    score: Optional[int] = None
    summary: str = ""
    suggestions: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class AnalyzeResult(BaseModel):
    repo_url: str
    repo_name: str
    total_score: int
    ready: bool
    threshold: int
    categories: list[CategoryResult]
    findings: list[Finding]
    ai: AiResult
    scanned_files: int
    skipped_files: int
    generated_at: str
    report_id: Optional[str] = None
