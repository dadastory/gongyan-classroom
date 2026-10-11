import time
import uuid

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def uid() -> str:
    return uuid.uuid4().hex


class Identity:
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class User(Identity, Base):
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(12))
    password_hash: Mapped[str] = mapped_column(Text)


class AuthSession(Identity, Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[float] = mapped_column(Float)


class Topic(Identity, Base):
    __tablename__ = "topics"
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    references: Mapped[str] = mapped_column(Text, default="")
    join_code: Mapped[str] = mapped_column(String(10), unique=True)
    join_open: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="preparing")
    settings: Mapped[dict] = mapped_column(JSON)
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)


class Group(Identity, Base):
    __tablename__ = "groups"
    topic_id: Mapped[str] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    direction: Mapped[str] = mapped_column(Text, default="")
    capacity: Mapped[int] = mapped_column(Integer, default=6)
    state: Mapped[str] = mapped_column(String(20), default="waiting")
    phase_index: Mapped[int] = mapped_column(Integer, default=0)
    phase_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    deadline: Mapped[float | None] = mapped_column(Float, nullable=True)
    remaining_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_intervention_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    concerns: Mapped[list] = mapped_column(JSON, default=list)
    intervention_state: Mapped[str] = mapped_column(String(30), default="monitoring")


class Enrollment(Identity, Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("topic_id", "user_id", name="uq_enrollment"),)
    topic_id: Mapped[str] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    group_id: Mapped[str | None] = mapped_column(
        ForeignKey("groups.id", ondelete="SET NULL"), nullable=True, index=True
    )


class Phase(Identity, Base):
    __tablename__ = "phases"
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    index: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(80))
    started_at: Mapped[float] = mapped_column(Float, default=time.time)
    ended_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    member_ids: Mapped[list] = mapped_column(JSON)


class Message(Identity, Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("group_id", "author_id", "client_id", name="uq_message_client"),)
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    phase_id: Mapped[str | None] = mapped_column(ForeignKey("phases.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(12))
    content: Mapped[str] = mapped_column(Text)
    client_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reply_to: Mapped[str | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    analysis_status: Mapped[str] = mapped_column(String(20), default="pending")


class MeaningUnit(Identity, Base):
    __tablename__ = "meaning_units"
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    phase_id: Mapped[str] = mapped_column(ForeignKey("phases.id"), index=True)
    start: Mapped[int] = mapped_column(Integer)
    end: Mapped[int] = mapped_column(Integer)
    quote: Mapped[str] = mapped_column(Text)
    cognitive: Mapped[str] = mapped_column(String(2))
    emotion: Mapped[str] = mapped_column(String(2))
    task_relevant: Mapped[bool] = mapped_column(Boolean)
    metacognitive: Mapped[list] = mapped_column(JSON, default=list)
    social: Mapped[list] = mapped_column(JSON, default=list)
    reason: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    skill_slug: Mapped[str] = mapped_column(String(80))
    skill_version: Mapped[int] = mapped_column(Integer)
    config_version: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(String(120))
    corrected: Mapped[bool] = mapped_column(Boolean, default=False)


class Outcome(Identity, Base):
    __tablename__ = "outcomes"
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    phase_id: Mapped[str] = mapped_column(ForeignKey("phases.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(Text)


class SkillVersion(Identity, Base):
    __tablename__ = "skill_versions"
    __table_args__ = (UniqueConstraint("teacher_id", "slug", "version", name="uq_skill_version"),)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    slug: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(1024))
    version: Mapped[int] = mapped_column(Integer)
    markdown: Mapped[str] = mapped_column(Text)
    digest: Mapped[str] = mapped_column(String(64))


class ModelConnection(Identity, Base):
    __tablename__ = "model_connections"
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    base_url: Mapped[str] = mapped_column(String(500))
    model: Mapped[str] = mapped_column(String(120))
    encrypted_key: Mapped[str] = mapped_column(Text)
    output_mode: Mapped[str] = mapped_column(String(20), default="json")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=60)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class AnalysisJob(Identity, Base):
    __tablename__ = "analysis_jobs"
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    phase_id: Mapped[str] = mapped_column(ForeignKey("phases.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="analysis")
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[float] = mapped_column(Float, default=time.time)
    lease_until: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Intervention(Identity, Base):
    __tablename__ = "interventions"
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    phase_id: Mapped[str] = mapped_column(ForeignKey("phases.id"), index=True)
    group_version: Mapped[int] = mapped_column(Integer)
    rule: Mapped[str] = mapped_column(String(80))
    skill_slug: Mapped[str] = mapped_column(String(80))
    skill_version: Mapped[int] = mapped_column(Integer)
    config_version: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(String(120))
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="generating")
    content: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[dict] = mapped_column(JSON)
    target_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    published_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    review_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    effect: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class MetricSnapshot(Identity, Base):
    __tablename__ = "metric_snapshots"
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    phase_id: Mapped[str] = mapped_column(ForeignKey("phases.id"), index=True)
    window_start: Mapped[float] = mapped_column(Float)
    window_end: Mapped[float] = mapped_column(Float)
    data: Mapped[dict] = mapped_column(JSON)


class AuditEvent(Identity, Base):
    __tablename__ = "audit_events"
    topic_id: Mapped[str] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    group_id: Mapped[str | None] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    event: Mapped[str] = mapped_column(String(80))
    data: Mapped[dict] = mapped_column(JSON)
