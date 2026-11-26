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

# 克隆与扫描限制
CLONE_DEPTH = 1
CLONE_TIMEOUT_SEC = 120
MAX_FILE_SIZE = 2 * 1024 * 1024   # 单文件最大 2MB，超过则跳过内容扫描
MAX_SCAN_FILES = 8000             # 单仓库最大扫描文件数
