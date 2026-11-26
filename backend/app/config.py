import os
from pathlib import Path

# 从 backend/.env 加载配置（不引入额外依赖，且优先级低于系统环境变量）
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

# DeepSeek API 配置：优先从环境变量读取，避免硬编码密钥
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 评分阈值：大于 80 分为接入就绪
READY_THRESHOLD = 80
TOTAL_SCORE = 100

# 各检测项满分（按重要程度分配）
WEIGHTS = {
    "secrets": 40,       # 密钥与敏感信息风险最高
    "windows": 25,       # Windows 专用脚本
    "hardcoded": 20,     # 硬编码路径
    "completeness": 15,  # README / 依赖清单 / 启动脚本完整度
}

def _env_int(name: str, default: int) -> int:
    """读取整型环境变量，非法值回退默认值（避免配置错误导致启动失败）。"""
    raw = os.getenv(name, "")
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


# 克隆与扫描限制（均可通过环境变量覆盖）
CLONE_DEPTH = 1
CLONE_TIMEOUT_SEC = _env_int("CLONE_TIMEOUT_SEC", 120)
MAX_FILE_SIZE = _env_int("MAX_FILE_SIZE_MB", 2) * 1024 * 1024  # 单文件上限
MAX_SCAN_FILES = _env_int("MAX_SCAN_FILES", 5000)              # 单仓库扫描文件数上限
MAX_REPO_SIZE_MB = _env_int("MAX_REPO_SIZE_MB", 100)           # 仓库总体积上限

# 服务端安全配置（均可通过环境变量覆盖）
MAX_CONCURRENT_ANALYSIS = _env_int("MAX_CONCURRENT_ANALYSIS", 3)
RATE_LIMIT_PER_MIN = _env_int("RATE_LIMIT_PER_MIN", 10)
REPORT_TTL_SEC = _env_int("REPORT_TTL_SEC", 3600)
REPORT_MAX_ENTRIES = _env_int("REPORT_MAX_ENTRIES", 500)

def _parse_origins(raw: str) -> list[str]:
    parts = [o.strip() for o in raw.split(",") if o.strip()]
    return parts if parts else ["http://localhost:5173", "http://127.0.0.1:5173"]

# CORS 白名单：生产环境通过 CORS_ORIGINS 环境变量配置（逗号分隔）
CORS_ORIGINS = _parse_origins(os.getenv("CORS_ORIGINS", ""))

# 可选 API Token 鉴权：配置后 /api/analyze 需携带 Authorization: Bearer <token>
API_TOKEN = os.getenv("API_TOKEN", "")
