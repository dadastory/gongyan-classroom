from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import ROOT, settings


class Base(DeclarativeBase):
    pass


def build_engine(url: str):
    parsed = make_url(url)
    sqlite = parsed.get_backend_name() == "sqlite"
    file_database = sqlite and parsed.database not in (None, "", ":memory:")
    if file_database:
        path = Path(parsed.database)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        parsed = parsed.set(database=str(path))
    engine = create_engine(
        parsed, connect_args={"check_same_thread": False, "timeout": 30} if sqlite else {}, pool_pre_ping=True
    )
    if sqlite:

        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            mode = cursor.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if file_database and mode.lower() != "wal":
                raise RuntimeError("数据库无法启用 SQLite WAL，请检查数据目录是否可写")
            cursor.execute("PRAGMA synchronous=FULL")
            cursor.close()

    return engine


engine = build_engine(settings().database_url)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db() -> Generator[Session]:
    with SessionLocal() as db:
        yield db


def lock_topic(db: Session, topic_id: str):
    from .models import Topic

    # Classroom mutations use a write transaction with SQLite, and a row lock with PostgreSQL.
    if db.bind.dialect.name == "sqlite":
        from sqlalchemy import update

        db.execute(update(Topic).where(Topic.id == topic_id).values(config_version=Topic.config_version))
    return db.get(Topic, topic_id, with_for_update=True, populate_existing=True)
