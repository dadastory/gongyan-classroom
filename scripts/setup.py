import sys
from pathlib import Path

if sys.prefix == sys.base_prefix:
    raise SystemExit("请使用 uv run python scripts/setup.py；首次启动可运行 uv run python scripts/quickstart.py")

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))

from app.config import ensure_config_file  # noqa: E402

path = ensure_config_file()
print(f"本地配置已准备：{path}。老师邀请码保存在 teacher_invite_code；已有配置与密钥保持。")
