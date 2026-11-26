"""四类检测规则：完整度、Windows 脚本、硬编码路径、密钥敏感信息。"""
import os
import re
from dataclasses import dataclass

from ..config import WEIGHTS
from ..models import CategoryResult, Finding

DOC_EXT = {".md", ".markdown", ".rst", ".txt", ".adoc"}
TEST_MARK = ("test_", "_test", ".test.", ".spec.", "tests/", "spec/", "__tests__/",
             "testing_utils", "conftest", "fixtures/", "mock", "stub")

# ---- README 内容判定 ----
README_RE = re.compile(r"^readme(\.[a-z0-9]+)?$", re.I)
DESC_RE = re.compile(
    # 英文标题需 \b 边界；中文标题不能用 \b（中文非单词字符），用前瞻空格/行尾/标点替代
    r"(?:^#{1,3}\s*)(?:about|description|overview)\b|"
    r"(?:^#{1,3}\s*)(?:简介|项目介绍|项目简介|概述|介绍)(?=\s|$|[：:。.、])|"
    r"(?:本项目|这个项目|一个(?:用于|基于)|a (?:simple|python|node|library|tool|framework|web))",
    re.I | re.M,
)
START_RE = re.compile(
    r"\b(?:quick\s*start|getting\s*started|install(?:ation)?|usage|run(?:ning)?|"
    r"启动|运行|使用|安装|快速开始|部署)\b|npm\s+(?:install|run|start)|"
    r"pip\s+install|docker\s+(?:run|compose)|yarn\s+(?:add|start)|go\s+run|"
    r"python\s+[\w./-]+\.py|mvn\s|gradle\s",
    re.I,
)

# ---- 依赖清单 ----
DEP_FILES = {
    "package.json", "requirements.txt", "pyproject.toml", "pipfile", "setup.py",
    "setup.cfg", "pom.xml", "build.gradle", "build.gradle.kts", "go.mod",
    "cargo.toml", "gemfile", "composer.json", "deno.json", "pubspec.yaml",
    "requirements-dev.txt", "environment.yml",
}
DEP_RE = re.compile(
    r"^(?:package\.json|requirements(?:-dev)?\.txt|pyproject\.toml|pipfile|setup\.(?:py|cfg)|"
    r"pom\.xml|build\.gradle(?:\.kts)?|go\.mod|cargo\.toml|gemfile|composer\.json|"
    r"deno\.json|pubspec\.yaml|environment\.yml)$",
    re.I,
)

# ---- 启动脚本 ----
START_FILES = {
    "dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml",
    "makefile", "procfile", "start.sh", "run.sh", "dev.sh", "serve.sh",
    "launcher.sh", "entrypoint.sh", "start.ps1",
}
START_FILE_RE = re.compile(
    r"^(?:dockerfile|docker-compose\.ya?ml|compose\.ya?ml|makefile|procfile|"
    r"start\.sh|run\.sh|dev\.sh|serve\.sh|launcher\.sh|entrypoint\.sh)$",
    re.I,
)

# ---- Windows 专用脚本扩展名与扣分 ----
WIN_EXT_SCORE = {".ps1": 10, ".bat": 8, ".cmd": 8, ".vbs": 5, ".vbscript": 5}

# ---- 硬编码路径 ----
PATH_PATTERNS = [
    # 盘符路径：单个字母 + 冒号 + 单个斜杠。\b 与负向先行断言排除 URL 协议（http://、https://）
    (re.compile(r"\b[A-Za-z]:[\\/](?![\\/])(?![xX][0-9a-fA-F]{2})[A-Za-z0-9._~ -]{2,}"), "Windows 盘符路径 (C:\\)"),
    (re.compile(r"/Users/[A-Za-z0-9._-]+"), "macOS 用户目录 (/Users/)"),
    (re.compile(r"/home/[A-Za-z0-9._-]+"), "Linux 用户目录 (/home/)"),
    (re.compile(r"/(?:var|opt|srv|usr/local)/[A-Za-z0-9._/-]+"), "Unix 绝对路径 (/var,/opt,/usr/local)"),
    # UNC 路径：段首不允许是常见转义字母（n/t/r/x/u/b/f/v/0），避免匹配 \\n \\zeta 等字面转义
    (re.compile(r"\\\\[A-Za-z0-9._-]+\\[A-Za-z0-9._$\\-]+"), "UNC 网络路径 (\\\\server\\share)"),
]

# Dockerfile 内部路径是容器构建规范，不属于接入风险；系统级标准路径同样不应计入
DOCKER_FILE_RE = re.compile(r"(?:^|/)dockerfile$|\.dockerfile$|(?:^|/)docker/", re.I)
SYSTEM_PATH_SAFE = re.compile(
    r"^/(?:var/lib/apt|var/cache|usr/local/(?:bin|lib|share|src)|usr/lib|usr/share|usr/bin|"
    r"opt/(?:venv|uv|ci|homebrew|conda)|etc/ssl|proc|sys|dev)(?:/|$)",
    re.I,
)
# 字面转义序列（Jinja / LaTeX / 正则 / 字节串）而非真实 UNC 路径
ESCAPE_SEQ_RE = re.compile(r"\\[ntrxubfv0NZ]|\\[uU][0-9a-fA-F]{4}")


def _hardcoded_deduct(hits: list["Hit"], total_files: int) -> int:
    """按命中密度扣分：命中文件占比越高扣分越多，避免大仓库被海量示例路径扣满。"""
    if not hits or total_files <= 0:
        return 0
    affected = len({h.file for h in hits})
    density = affected / total_files       # 命中文件占比
    # 每 1% 命中约扣 0.5 分，封顶 20；小仓库少量硬编码也会被适度扣分
    import math
    return min(20, max(3, math.ceil(density * 50)))

# ---- 密钥与敏感信息 ----
# 每条规则：(key, 正则, 扣分, 描述)。扣分档：20=高危凭证，15=中危，10=通用赋值
SECRET_PATTERNS = [
    # OpenAI 旧版 sk- 与新版 sk-proj-（项目密钥含连字符）
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"), 20, "疑似 OpenAI API 密钥 (sk-/sk-proj-)"),
    ("aliyun_akid", re.compile(r"\b(?:AKID|LTAI)[A-Za-z0-9]{12,}\b"), 20, "疑似阿里云 AccessKey ID"),
    ("aws_akid", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16,20}\b"), 20, "疑似 AWS AccessKey ID"),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b"), 20, "疑似 GitHub Token"),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), 20, "疑似 Slack Token"),
    ("stripe_key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b"), 20, "疑似 Stripe 密钥"),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"), 20, "私钥文件入库"),
    ("bearer", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}\b"), 15, "疑似 Bearer Token"),
    ("generic_secret", re.compile(
        r"(?:api[_-]?key|secret|token|passwd|password|access[_-]?key)\s*[:=]\s*[\"']"
        r"[A-Za-z0-9_\-]{16,}[\"']", re.I), 10, "疑似硬编码密钥/口令"),
]
# 测试资源中的凭证类命中：保留 finding 供审计，但不扣分（severity 降为 info）
TEST_EXEMPT_KEYS = {"openai_key", "aliyun_akid", "aws_akid", "github_token",
                    "slack_token", "stripe_key", "private_key", "bearer", "generic_secret"}
ENV_FILE_RE = re.compile(r"^\.env(?:\.[A-Za-z0-9_-]+)?$", re.I)
ENV_SAFE_RE = re.compile(r"^\.env\.(?:example|sample|template|dist|default)$", re.I)

PLACEHOLDER_RE = re.compile(
    r"your[_-]?|xxx+|example|placeholder|changeme|dummy|sample|fake|test[_-]?key|"
    r"^\$\{|^<|^\{\{|os\.getenv|process\.env|os\.environ|getenv\(|env\(|"
    r"insert[_-]?|replace[_-]?|填写|替换|示例|占位",
    re.I,
)
HIGH_ENTROPY_RE = re.compile(r"[A-Za-z0-9_\-]{20,}")


@dataclass
class Hit:
    key: str
    file: str
    line: int
    snippet: str
    deduct: int
    message: str
    severity: str = "high"


def _is_doc(file: str) -> bool:
    return os.path.splitext(file)[1].lower() in DOC_EXT


def _is_test(file: str) -> bool:
    f = file.lower()
    return any(m in f for m in TEST_MARK)


def _snippet(line: str, limit: int = 160) -> str:
    s = line.strip()
    return s if len(s) <= limit else s[:limit] + "…"


def detect_completeness(files: list[tuple[str, str]]) -> tuple[CategoryResult, list[Finding]]:
    paths = [p for p, _ in files]
    max_score = WEIGHTS["completeness"]
    findings: list[Finding] = []
    details: list[str] = []
    score = 0.0

    # README：存在(3) + 项目描述(2) + 启动方式(3)
    readme = next((p for p in paths if README_RE.match(os.path.basename(p))), None)
    if readme:
        content = dict(files).get(readme, "")
        score += 3
        details.append(f"README 存在：{readme}")
        if DESC_RE.search(content) or len(content) > 500:
            score += 2
            details.append("README 包含项目描述")
        else:
            findings.append(Finding(
                category="completeness", severity="medium", file=readme,
                message="README 缺少明确的项目描述/简介", snippet="建议补充项目用途与功能概述",
            ))
        if START_RE.search(content):
            score += 3
            details.append("README 包含安装/启动说明")
        else:
            findings.append(Finding(
                category="completeness", severity="high", file=readme,
                message="README 缺少安装/启动说明", snippet="建议补充快速开始与运行命令",
            ))
    else:
        findings.append(Finding(
            category="completeness", severity="high", file="README*",
            message="缺少 README 文件", snippet="README 是接入方理解项目的第一入口",
        ))

    # 依赖清单：存在即满分 4
    deps = sorted({os.path.basename(p) for p in paths if DEP_RE.match(os.path.basename(p))})
    if deps:
        score += 4
        details.append("依赖清单：" + ", ".join(deps))
    else:
        findings.append(Finding(
            category="completeness", severity="high", file="(未找到)",
            message="缺少依赖清单文件", snippet="未发现 requirements.txt / package.json / pom.xml 等",
        ))

    # 启动脚本：存在即满分 3
    starts = sorted({os.path.basename(p) for p in paths if START_FILE_RE.match(os.path.basename(p))})
    pkg_scripts = False
    for p, c in files:
        if os.path.basename(p).lower() == "package.json" and re.search(r'"(?:start|dev|serve)"\s*:', c):
            pkg_scripts = True
            break
    if starts or pkg_scripts:
        score += 3
        details.append("启动脚本：" + (", ".join(starts) if starts else "package.json scripts"))
    else:
        findings.append(Finding(
            category="completeness", severity="medium", file="(未找到)",
            message="缺少标准启动脚本", snippet="未发现 Dockerfile / Makefile / start.sh / npm scripts 等",
        ))

    return CategoryResult(
        key="completeness", name="文档与脚本完整度", score=min(score, max_score),
        max_score=max_score, details=details,
    ), findings


def detect_windows(files: list[tuple[str, str]]) -> tuple[CategoryResult, list[Finding]]:
    max_score = WEIGHTS["windows"]
    hits: list[Hit] = []
    for p, _ in files:
        ext = os.path.splitext(p)[1].lower()
        if ext in WIN_EXT_SCORE:
            hits.append(Hit(
                key="windows", file=p, line=1, snippet=f"脚本文件：{os.path.basename(p)}",
                deduct=WIN_EXT_SCORE[ext],
                message=f"Windows 专用脚本 ({ext})",
                severity="high" if ext == ".ps1" else "medium",
            ))
    return _build_result("windows", "Windows 专用脚本", max_score, hits)


def detect_hardcoded(files: list[tuple[str, str]]) -> tuple[CategoryResult, list[Finding]]:
    max_score = WEIGHTS["hardcoded"]
    hits: list[Hit] = []
    seen: set[tuple[str, int, str]] = set()
    for p, content in files:
        # 文档示例、Dockerfile 内部路径、测试目录均不计入
        if _is_doc(p) or DOCKER_FILE_RE.search(p) or _is_test(p):
            continue
        for lineno, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "//", "*", "/*")):
                continue
            for pattern, label in PATH_PATTERNS:
                m = pattern.search(line)
                if not m:
                    continue
                val = m.group(0)
                if PLACEHOLDER_RE.search(val) or len(val) < 5:
                    continue
                # 系统标准路径（/usr/local/bin、/opt/venv 等）不算硬编码
                if SYSTEM_PATH_SAFE.match(val):
                    continue
                # UNC 模式下命中转义序列（\\n、\\zeta 等）视为误报
                if "UNC" in label and ESCAPE_SEQ_RE.search(val):
                    continue
                dedup_key = (p, lineno, label)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                hits.append(Hit(
                    key="hardcoded", file=p, line=lineno, snippet=_snippet(line),
                    deduct=5, message=f"硬编码路径：{label}", severity="medium",
                ))
    # 改用命中密度扣分，避免大仓库被海量示例路径直接扣满
    result, findings = _build_result("hardcoded", "硬编码路径", max_score, hits)
    deduct = _hardcoded_deduct(hits, len(files))
    result.score = max(0.0, max_score - deduct)
    result.details = [f"命中 {len(hits)} 处（{len({h.file for h in hits})} 个文件），按密度扣分 {deduct}/{max_score}"]
    return result, findings


def detect_secrets(files: list[tuple[str, str]]) -> tuple[CategoryResult, list[Finding]]:
    max_score = WEIGHTS["secrets"]
    hits: list[Hit] = []
    seen: set[tuple[str, int, str]] = set()

    for p, content in files:
        base = os.path.basename(p)
        is_doc = _is_doc(p)
        is_test = _is_test(p)
        # .env 入库检测（排除示例模板与测试目录）
        if ENV_FILE_RE.match(base) and not ENV_SAFE_RE.match(base):
            hits.append(Hit(
                key="secrets", file=p, line=1, snippet=f"环境配置文件入库：{base}",
                deduct=0 if is_test else 15,
                message=".env 环境配置文件入库" + ("（测试资源，未扣分）" if is_test else ""),
                severity="info" if is_test else "high",
            ))

        for lineno, line in enumerate(content.splitlines(), 1):
            for key, pattern, deduct, label in SECRET_PATTERNS:
                m = pattern.search(line)
                if not m:
                    continue
                val = m.group(0)
                # 占位符/示例过滤
                if PLACEHOLDER_RE.search(val):
                    continue
                # 文档中的凭证示例直接跳过
                if key in TEST_EXEMPT_KEYS and is_doc:
                    continue
                # 测试资源中的凭证：保留 finding 供审计，但不扣分（info 级）
                severity = "high" if deduct >= 15 else "medium"
                if key in TEST_EXEMPT_KEYS and is_test:
                    deduct = 0
                    severity = "info"
                dedup_key = (p, lineno, key)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                hits.append(Hit(
                    key="secrets", file=p, line=lineno, snippet=_snippet(line),
                    deduct=deduct, message=label + ("（测试资源，未扣分）" if deduct == 0 else ""),
                    severity=severity,
                ))

    return _build_result("secrets", "密钥与敏感信息", max_score, hits)


def _build_result(key: str, name: str, max_score: float, hits: list[Hit]) -> tuple[CategoryResult, list[Finding]]:
    total_deduct = sum(h.deduct for h in hits)
    score = max(0.0, max_score - total_deduct)
    findings = [
        Finding(category=h.key, severity=h.severity, file=h.file, line=h.line,
                message=h.message, snippet=h.snippet)
        for h in hits
    ]
    details = [f"命中 {len(hits)} 处，扣分 {min(total_deduct, max_score)}/{max_score}"]
    return CategoryResult(
        key=key, name=name, score=score, max_score=max_score, details=details,
    ), findings


def detect_all(files: list[tuple[str, str]]) -> tuple[list[CategoryResult], list[Finding]]:
    detections = [
        detect_completeness(files),
        detect_secrets(files),
        detect_windows(files),
        detect_hardcoded(files),
    ]
    categories: list[CategoryResult] = []
    findings: list[Finding] = []
    for cat, finds in detections:
        categories.append(cat)
        findings.extend(finds)
    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings.sort(key=lambda f: (order.get(f.severity, 9), f.category, f.file))
    return categories, findings
