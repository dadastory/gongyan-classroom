"""Start the built webpage, API and WebSocket in one Python process."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="共研前后端一体化启动")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认只允许本机访问")
    parser.add_argument("--port", type=int, default=8088, help="网页、API 和实时连接的共同端口")
    parser.add_argument("--build", action="store_true", help="启动前用 Node 安装依赖并构建网页")
    parser.add_argument("--demo", action="store_true", help="创建演示账号与课堂")
    args = parser.parse_args()
    if sys.prefix == sys.base_prefix:
        parser.error("请使用 uv run python scripts/run.py；首次启动运行 uv run python scripts/quickstart.py")
    if not 1 <= args.port <= 65535:
        parser.error("端口必须在 1–65535 之间")
    subprocess.run([sys.executable, str(ROOT / "scripts/setup.py")], check=True)
    if args.build:
        subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=ROOT / "frontend", check=True)
        subprocess.run(["npm", "run", "build"], cwd=ROOT / "frontend", check=True)
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "backend")}
    # Use the same local JSON settings as the HTTP service.
    sys.path.insert(0, str(ROOT / "backend"))
    from app.config import settings

    if not (settings().frontend_dist / "index.html").is_file():
        parser.error("网页尚未构建，请先执行 npm --prefix frontend run build，或添加 --build")
    subprocess.run([sys.executable, "-m", "app.manage", "migrate"], cwd=ROOT, env=environment, check=True)
    if args.demo:
        subprocess.run([sys.executable, "-m", "app.manage", "seed-demo"], cwd=ROOT, env=environment, check=True)
    os.chdir(ROOT)
    os.execvpe(sys.executable, [sys.executable, "-m", "uvicorn", "app.main:app",
                              "--host", args.host, "--port", str(args.port), "--workers", "1"], environment)


if __name__ == "__main__":
    main()
