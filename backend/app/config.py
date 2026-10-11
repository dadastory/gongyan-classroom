import base64
import json
import os
import secrets
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile

from cryptography.fernet import Fernet
from dotenv import dotenv_values
from pydantic import TypeAdapter, field_validator
from pydantic_settings import BaseSettings, JsonConfigSettingsSource, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


def config_path() -> Path:
    path = Path(os.environ.get("CLASSROOM_CONFIG_FILE", str(ROOT / "data/config.json")))
    return path if path.is_absolute() else ROOT / path


def ensure_config_file(path: Path | None = None, legacy_env: Path | None = None) -> Path:
    path = path or config_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            Fernet(data["encryption_key"].encode())
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise ValueError("本地配置无法读取或密钥无效，请修复配置或恢复备份；不会自动替换密钥") from error
        return path
    if legacy_env is None and path == ROOT / "data/config.json":
        legacy_env = ROOT / ".env"
    values = {
        "encryption_key": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "teacher_invite_code": secrets.token_urlsafe(18),
        "allowed_origins": "http://localhost:8088,http://127.0.0.1:8088,http://localhost:5173,http://127.0.0.1:5173",
        "cookie_secure": False,
    }
    old_key = path.parent / ".encryption-key"
    if old_key.exists():
        values["encryption_key"] = old_key.read_text().strip()
    migrate_env = legacy_env is not None and legacy_env.is_file()
    if migrate_env:
        old = dotenv_values(legacy_env, interpolate=False)
        for name, field in Settings.model_fields.items():
            value = old.get(name.upper())
            if value is not None and value != "":
                try:
                    values[name] = TypeAdapter(field.annotation).validate_python(value)
                except ValueError as error:
                    raise ValueError(f"旧配置中的 {name} 无效，请先修复；原文件已保留") from error
    try:
        Fernet(values["encryption_key"].encode())
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("旧加密密钥无效，请恢复原密钥；不会生成替代密钥") from error
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
        staging = Path(file.name)
        try:
            json.dump(values, file, ensure_ascii=False, indent=2, default=str)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
            try:
                os.link(staging, path)
            except FileExistsError:
                return ensure_config_file(path)
        finally:
            staging.unlink(missing_ok=True)
    if migrate_env:
        backup = path.parent / "legacy-env-backup"
        with os.fdopen(os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb") as file:
            file.write(legacy_env.read_bytes())
        legacy_env.unlink()
    return path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)
    database_url: str = f"sqlite:///{ROOT / 'data' / 'classroom.db'}"
    encryption_key: str = ""
    teacher_invite_code: str = ""
    cookie_secure: bool = False
    allowed_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8088,http://127.0.0.1:8088"
    )
    worker_enabled: bool = True
    analysis_delay_seconds: float = 8
    worker_interval_seconds: float = 3
    session_hours: int = 12
    demo_mode: bool = False
    frontend_dist: Path = ROOT / "frontend" / "dist"

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings,
                                   dotenv_settings, file_secret_settings):
        return (init_settings, env_settings, JsonConfigSettingsSource(settings_cls, json_file=config_path()))

    @field_validator("encryption_key")
    @classmethod
    def valid_encryption_key(cls, value):
        try:
            Fernet(value.encode())
        except (ValueError, TypeError) as error:
            raise ValueError("加密密钥无效，请恢复原配置") from error
        return value

    @property
    def origins(self) -> list[str]:
        return [item.strip().rstrip("/") for item in self.allowed_origins.split(",") if item.strip()]


@lru_cache
def settings() -> Settings:
    ensure_config_file()
    return Settings()
