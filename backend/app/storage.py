"""Verified SQLite migration and online backups; credentials never leave database files."""

import hashlib
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import NamedTemporaryFile

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Column, MetaData, String, Table, inspect, select
from sqlalchemy.engine import Engine

from . import models  # noqa: F401
from .db import Base, build_engine


def _staging_file(output: Path) -> Path:
    if output.exists():
        raise FileExistsError("目标文件已存在，请指定新的路径；不会覆盖已有数据库")
    output.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent, delete=False) as file:
        return Path(file.name)


def _remove_staging(path: Path):
    for suffix in ("", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)


def _publish(staging: Path, output: Path):
    # Both files are on the same local filesystem. link atomically refuses an existing target.
    os.link(staging, output)
    staging.unlink()


def _digest(connection, table):
    digest = hashlib.sha256()
    count = 0
    for row in connection.execute(select(table).order_by(*table.primary_key.columns)).mappings():
        digest.update(json.dumps(dict(row), sort_keys=True, ensure_ascii=False,
                                 separators=(",", ":"), allow_nan=False).encode())
        digest.update(b"\n")
        count += 1
    return {"count": count, "sha256": digest.hexdigest()}


def copy_to_sqlite(source: Engine, output: Path) -> dict:
    """Copy a current-schema database to a new SQLite file, then validate before publishing."""
    output = output.resolve()
    staging = _staging_file(output)
    target = None
    try:
        backend = Path(__file__).resolve().parents[1]
        config = Config(str(backend / "alembic.ini"))
        config.set_main_option("script_location", str(backend / "migrations"))
        heads = set(ScriptDirectory.from_config(config).get_heads())
        version = Table("alembic_version", MetaData(), Column("version_num", String(32), primary_key=True))
        target = build_engine(f"sqlite:///{staging}")
        Base.metadata.create_all(target)
        version.create(target)
        with source.connect() as origin:
            if source.dialect.name == "postgresql":
                origin = origin.execution_options(isolation_level="REPEATABLE READ")
            with origin.begin():
                if source.dialect.name == "sqlite":
                    origin.exec_driver_sql("BEGIN")
                if "alembic_version" not in inspect(origin).get_table_names():
                    raise ValueError("源数据库尚未迁移，请先执行 migrate")
                if set(origin.scalars(select(version.c.version_num))) != heads:
                    raise ValueError("源数据库版本与程序不一致，请先更新并执行 migrate")
                tables = [*Base.metadata.sorted_tables, version]
                result = {}
                with target.begin() as destination:
                    destination.exec_driver_sql("PRAGMA defer_foreign_keys=ON")
                    for table in tables:
                        rows = origin.execute(select(table).order_by(*table.primary_key.columns)).mappings()
                        for batch in rows.partitions(500):
                            destination.execute(table.insert(), [dict(row) for row in batch])
                        expected = _digest(origin, table)
                        actual = _digest(destination, table)
                        if actual != expected:
                            raise ValueError(f"{table.name} 内容校验失败，未发布迁移文件")
                        result[table.name] = actual
                    if destination.exec_driver_sql("PRAGMA foreign_key_check").fetchall():
                        raise ValueError("外键校验失败，未发布迁移文件")
                    if destination.exec_driver_sql("PRAGMA integrity_check").scalar_one() != "ok":
                        raise ValueError("完整性校验失败，未发布迁移文件")
        with target.connect() as connection:
            checkpoint = connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if checkpoint[0] != 0:
                raise ValueError("WAL 未完成落盘，未发布迁移文件")
        target.dispose()
        target = None
        _publish(staging, output)
        return {"tables": result, "integrity": "ok", "foreign_keys": "ok", "journal_mode": "wal"}
    finally:
        if target is not None:
            target.dispose()
        _remove_staging(staging)


def backup_sqlite(source: Engine, output: Path) -> dict:
    """Use SQLite's backup API to include committed WAL pages in an online backup."""
    if source.dialect.name != "sqlite" or source.url.database in (None, "", ":memory:"):
        raise ValueError("在线备份仅支持文件 SQLite；其他数据库请使用对应备份工具")
    output = output.resolve()
    staging = _staging_file(output)
    try:
        with source.connect() as origin:
            raw = origin.connection.driver_connection
            with closing(sqlite3.connect(staging)) as destination:
                raw.backup(destination, pages=256, sleep=0.05)
                if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("备份完整性校验失败")
                if destination.execute("PRAGMA foreign_key_check").fetchall():
                    raise ValueError("备份外键校验失败")
        _publish(staging, output)
        return {"integrity": "ok", "foreign_keys": "ok"}
    finally:
        _remove_staging(staging)
