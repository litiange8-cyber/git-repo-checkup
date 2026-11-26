"""DeepSeek AI 接入：给出项目评分与接入建议。"""
import json
from typing import Optional

from openai import OpenAI

from ..config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from ..models import AiResult, CategoryResult, Finding


def build_prompt(repo_name: str, total_score: int, categories: list[CategoryResult],
                 findings: list[Finding], ready: bool) -> str:
    cat_lines = "\n".join(
        f"- {c.name}：{c.score:.0f}/{c.max_score:.0f}" for c in categories
    )
    risk_lines = "\n".join(
        f"[{f.severity}] {f.category} {f.file}"
        + (f":{f.line}" if f.line else "")
        + f" - {f.message}"
        for f in findings[:40]
    ) or "无明显风险"
    return f"""你是一名资深技术负责人，正在评估一个开源仓库是否适合接入（接手维护/二次开发）。
请基于以下体检结果给出专业判断。

仓库：{repo_name}
接入就绪度评分：{total_score}/100（{'已就绪' if ready else '未就绪'}，阈值 80）
分类得分：
{cat_lines}

主要风险清单：
{risk_lines}

请严格输出 JSON（不要输出其他文字），格式如下：
{{"score": <你给出的综合评分 0-100 整数>, "summary": "<不超过 120 字的总体评价>", "suggestions": ["<建议1>", "<建议2>", "<建议3>"]}}
建议需具体、可执行，聚焦接入前必须处理的问题。"""


def get_ai_advice(repo_name: str, total_score: int, categories: list[CategoryResult],
                  findings: list[Finding], ready: bool) -> AiResult:
    if not DEEPSEEK_API_KEY:
        return AiResult(enabled=False, error="未配置 DEEPSEEK_API_KEY，跳过 AI 建议")
    try:
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, timeout=60.0)
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": "你是严谨的技术评估专家，只输出规定的 JSON，不添加任何解释文字。"},
                {"role": "user", "content": build_prompt(repo_name, total_score, categories, findings, ready)},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        return AiResult(
            enabled=True,
            score=int(data.get("score", total_score)),
            summary=str(data.get("summary", ""))[:500],
            suggestions=[str(s)[:300] for s in data.get("suggestions", [])[:5]],
        )
    except Exception as e:  # 网络/额度/格式异常均降级，不影响主流程
        return AiResult(enabled=False, error=f"AI 建议生成失败：{str(e)[:200]}")
