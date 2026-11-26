"""仓库拉取与文件扫描：浅克隆公开 Git 仓库并遍历文本文件。"""
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field

from ..config import CLONE_DEPTH, CLONE_TIMEOUT_SEC, MAX_FILE_SIZE, MAX_SCAN_FILES, MAX_REPO_SIZE_MB


class RepoError(Exception):
    """仓库链接非法或拉取失败。"""


@dataclass
class ScanResult:
    tmp_dir: str
    files: list[tuple[str, str]] = field(default_factory=list)  # (相对路径, 文本内容)
    scanned_files: int = 0
    skipped_files: int = 0
    repo_name: str = ""

    def cleanup(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)


# 仅接受 http(s) 的 GitHub 链接，拒绝本地路径 / ssh / 带凭据的 URL
URL_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)

# 二进制 / 大体积扩展名，直接跳过内容读取
BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar", ".jar", ".war",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".class",
    ".pyc", ".pyd", ".woff", ".woff2", ".ttf", ".eot", ".mp3", ".mp4",
    ".wav", ".avi", ".mov", ".lock", ".sum", ".db", ".sqlite", ".sqlite3",
}
SKIP_DIRS = {
    ".git", ".github", "node_modules", "dist", "build", "out", "target",
    "vendor", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache",
    ".idea", ".vscode", ".gradle", "coverage", ".next", ".nuxt",
}
SKIP_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock", "gemfile.lock"}


def validate_url(url: str) -> tuple[str, str]:
    url = url.strip()
    m = URL_RE.match(url)
    if not m:
        raise RepoError(
            "仅支持公开的 GitHub 仓库链接，格式如 https://github.com/owner/repo"
        )
    owner, repo = m.group("owner"), m.group("repo")
    if repo in {"", ".", ".."}:
        raise RepoError("仓库名无效")
    return owner, repo


def _clone(owner: str, repo: str, dest: str):
    url = f"https://github.com/{owner}/{repo}.git"
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"  # 禁止凭据交互，确保只访问公开仓库
    env["GIT_LFS_SKIP_SMUDGE"] = "1"
    try:
        proc = subprocess.run(
            ["git", "clone", "--depth", str(CLONE_DEPTH), "--quiet", url, dest],
            env=env,
            capture_output=True,
            text=True,
            timeout=CLONE_TIMEOUT_SEC,
        )
    except FileNotFoundError:
        raise RepoError("服务器未安装 git，无法拉取仓库")
    except subprocess.TimeoutExpired:
        raise RepoError(f"克隆超时（超过 {CLONE_TIMEOUT_SEC} 秒），请确认仓库为公开且体积适中")
    if proc.returncode != 0:
        # 不回显 git 原文，按常见失败类型映射为用户可读提示
        raw = ((proc.stderr or "") + (proc.stdout or "")).lower()
        if "not found" in raw or "could not read username" in raw or "authentication failed" in raw:
            raise RepoError("仓库不存在或非公开，请检查链接是否正确")
        if "repository not found" in raw:
            raise RepoError("仓库不存在或非公开，请检查链接是否正确")
        if "timed out" in raw or "connection" in raw:
            raise RepoError("拉取仓库时网络超时，请稍后重试")
        if "rate limit" in raw:
            raise RepoError("GitHub 访问频率受限，请稍后重试")
        raise RepoError("拉取仓库失败，请确认链接为公开 GitHub 仓库")


def _looks_text(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def scan_repo(url: str) -> ScanResult:
    owner, repo = validate_url(url)
    tmp = tempfile.mkdtemp(prefix="repo-checkup-")
    result = ScanResult(tmp_dir=tmp, repo_name=f"{owner}/{repo}")
    try:
        _clone(owner, repo, tmp)
        # 仓库总体积上限：防止超大仓库打满磁盘
        total_bytes = 0
        max_bytes = MAX_REPO_SIZE_MB * 1024 * 1024
        for root, _, filenames in os.walk(tmp):
            for name in filenames:
                try:
                    total_bytes += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
                if total_bytes > max_bytes:
                    raise RepoError(f"仓库体积超过 {MAX_REPO_SIZE_MB}MB 上限，已拒绝分析")
        for root, dirs, filenames in os.walk(tmp):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
            for name in filenames:
                if result.scanned_files >= MAX_SCAN_FILES:
                    result.skipped_files += 1
                    continue
                full = os.path.join(root, name)
                rel = os.path.relpath(full, tmp).replace("\\", "/")
                if name.lower() in SKIP_FILES:
                    result.skipped_files += 1
                    continue
                ext = os.path.splitext(name)[1].lower()
                if ext in BINARY_EXT:
                    result.skipped_files += 1
                    continue
                try:
                    size = os.path.getsize(full)
                    if size > MAX_FILE_SIZE or size == 0:
                        result.skipped_files += 1
                        continue
                    with open(full, "rb") as f:
                        data = f.read()
                    if not _looks_text(data):
                        result.skipped_files += 1
                        continue
                    content = data.decode("utf-8", errors="replace")
                except OSError:
                    result.skipped_files += 1
                    continue
                result.files.append((rel, content))
                result.scanned_files += 1
        return result
    except Exception:
        result.cleanup()
        raise
