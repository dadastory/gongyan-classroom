"""Build the webpage if needed, then run the classroom in uv's project environment."""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def frontend_digest() -> str:
    files = [path for directory in ("src", "public")
             for path in (ROOT / "frontend" / directory).rglob("*") if path.is_file()]
    files += [path for path in (ROOT / "frontend").iterdir() if path.is_file()]
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(str(path.relative_to(ROOT / "frontend")).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description="共研快速启动：Python + SQLite WAL，无需 Docker")
    parser.add_argument("--demo", action="store_true", help="创建演示账号和课堂")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认只允许本机访问")
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--update", action="store_true", help="重新构建网页")
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        parser.error("需要 Python 3.12 或更新版本")
    if sys.prefix == sys.base_prefix:
        parser.error("请使用 uv run python scripts/quickstart.py，由 uv 准备项目虚拟环境")
    if not 1 <= args.port <= 65535:
        parser.error("端口必须在 1–65535 之间")
    source_digest = frontend_digest()
    web_marker = ROOT / "frontend/dist/.classroom-sources.sha256"
    if (args.update or not (ROOT / "frontend/dist/index.html").is_file()
            or not web_marker.exists() or web_marker.read_text() != source_digest):
        npm = shutil.which("npm")
        node = shutil.which("node")
        if not npm or not node:
            parser.error("首次构建需要 Node.js 22+；网页已构建时可用 uv run python scripts/run.py")
        version = subprocess.check_output([node, "--version"], text=True).strip()
        if int(version.lstrip("v").split(".")[0]) < 22:
            parser.error("首次构建需要 Node.js 22 或更新版本")
        print("正在构建网页……", flush=True)
        subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=ROOT / "frontend", check=True)
        subprocess.run([npm, "run", "build"], cwd=ROOT / "frontend", check=True)
        web_marker.write_text(source_digest)
    command = [sys.executable, str(ROOT / "scripts/run.py"), "--host", args.host, "--port", str(args.port)]
    if args.demo:
        command.append("--demo")
    os.chdir(ROOT)
    os.execvpe(sys.executable, command, os.environ)


if __name__ == "__main__":
    main()
