"""生成可独立打开的 HTML 报告页（含内嵌图表数据）。"""
import html
import json
from datetime import datetime

from ..models import AnalyzeResult

SEV_LABEL = {"high": "高风险", "medium": "中风险", "low": "低风险", "info": "提示"}
SEV_COLOR = {"high": "#e5484d", "medium": "#f5a524", "low": "#30a46c", "info": "#8b8b8b"}


def render_report(result: AnalyzeResult) -> str:
    score = result.total_score
    score_color = "#30a46c" if result.ready else "#e5484d"
    status = "接入就绪" if result.ready else "未达就绪"
    rows = "\n".join(
        f"""<tr>
          <td><span class="badge" style="background:{SEV_COLOR.get(f.severity, '#888')}">{SEV_LABEL.get(f.severity, f.severity)}</span></td>
          <td>{html.escape(f.category)}</td>
          <td class="path">{html.escape(f.file)}{(':' + str(f.line)) if f.line else ''}</td>
          <td>{html.escape(f.message)}</td>
          <td class="snippet">{html.escape(f.snippet or '')}</td>
        </tr>"""
        for f in result.findings
    ) or '<tr><td colspan="5" class="empty">未检出明显风险项</td></tr>'

    cat_rows = "\n".join(
        f"""<tr><td>{html.escape(c.name)}</td><td>{c.score:.0f} / {c.max_score:.0f}</td>
        <td><div class="bar"><div class="bar-inner" style="width:{c.score / c.max_score * 100:.0f}%"></div></div></td></tr>"""
        for c in result.categories
    )

    ai_html = ""
    if result.ai.enabled:
        sugg = "".join(f"<li>{html.escape(s)}</li>" for s in result.ai.suggestions)
        ai_html = f"""<section>
          <h2>AI 接入建议 <span class="tag">DeepSeek · {result.ai.score}/100</span></h2>
          <p>{html.escape(result.ai.summary)}</p>
          <ol>{sugg}</ol>
        </section>"""

    chart_data = json.dumps(
        [{"name": c.name, "score": c.score, "max": c.max_score} for c in result.categories],
        ensure_ascii=False,
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>接入体检报告 - {html.escape(result.repo_name)}</title>
<style>
  *{{box-sizing:border-box}}
  body{{margin:0;background:#0f1115;color:#e6e6e6;font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;line-height:1.6}}
  .wrap{{max-width:1080px;margin:0 auto;padding:40px 24px 80px}}
  h1{{font-size:26px;margin:0 0 4px}} h2{{font-size:18px;margin:36px 0 14px;border-left:3px solid #5b8def;padding-left:10px}}
  .sub{{color:#8b949e;font-size:13px}}
  .hero{{display:flex;gap:32px;align-items:center;background:#171a21;border:1px solid #262b36;border-radius:14px;padding:28px;margin-top:24px}}
  .score{{font-size:64px;font-weight:700;line-height:1;color:{score_color}}}
  .status{{display:inline-block;padding:4px 14px;border-radius:20px;background:{score_color};color:#0f1115;font-weight:600;font-size:13px;margin-top:8px}}
  table{{width:100%;border-collapse:collapse;background:#171a21;border:1px solid #262b36;border-radius:10px;overflow:hidden;font-size:13px}}
  th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid #232833;vertical-align:top}}
  th{{color:#8b949e;background:#1c2029;font-weight:600}}
  tr:last-child td{{border-bottom:none}}
  .badge{{color:#0f1115;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;white-space:nowrap}}
  .path{{font-family:Consolas,monospace;color:#79c0ff;word-break:break-all}}
  .snippet{{font-family:Consolas,monospace;color:#a0a8b5;word-break:break-all}}
  .empty{{text-align:center;color:#8b949e;padding:28px}}
  .bar{{background:#232833;border-radius:6px;height:10px;width:180px}}
  .bar-inner{{background:#5b8def;height:100%;border-radius:6px}}
  .tag{{font-size:12px;color:#8b949e;font-weight:400}}
  .meta{{display:flex;gap:24px;color:#8b949e;font-size:13px;margin-top:12px}}
  code{{background:#1c2029;padding:2px 6px;border-radius:4px}}
</style></head><body><div class="wrap">
  <h1>Git 仓库接入体检报告</h1>
  <div class="sub">生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
  <div class="hero">
    <div><div class="score">{score}</div><div class="status">{status}</div></div>
    <div>
      <div style="font-size:20px">{html.escape(result.repo_name)}</div>
      <div class="meta">
        <span>仓库链接：<a href="{html.escape(result.repo_url)}" style="color:#79c0ff">{html.escape(result.repo_url)}</a></span>
        <span>扫描文件：{result.scanned_files}</span>
        <span>就绪阈值：&gt;{result.threshold}</span>
      </div>
      <div class="sub" style="margin-top:10px">评分构成：密钥敏感 40 · Windows 脚本 25 · 硬编码路径 20 · 完整度 15（满分 100）</div>
    </div>
  </div>
  <section><h2>分类得分</h2><table><tr><th>检测项</th><th>得分</th><th>占比</th></tr>{cat_rows}</table></section>
  <section><h2>主要风险清单（{len(result.findings)} 项）</h2>
    <table><tr><th>等级</th><th>类别</th><th>文件</th><th>问题</th><th>证据</th></tr>{rows}</table>
  </section>
  {ai_html}
  <section><h2>说明</h2><p class="sub">
    本报告由自动化静态扫描生成，密钥检测结果基于字符串匹配与占位符过滤，可能存在误报或漏报，
    请结合人工复核。评分 &gt; {result.threshold} 分视为接入就绪。
  </p></section>
</div>
<script>
  // 图表数据（供二次开发使用）
  window.__CHART_DATA__ = {chart_data};
</script>
</body></html>"""
