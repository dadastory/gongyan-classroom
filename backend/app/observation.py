"""当前阶段的只读助教概况；不返回任务 payload 或模型密钥。"""

import time
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AnalysisJob, Group, Intervention, ModelConnection, Topic


def job_view(job: AnalysisJob) -> dict:
    runtime = job.payload.get("runtime", job.payload)
    skill = runtime.get("skill", {})
    connection = runtime.get("connection", {})
    return {
        **{key: getattr(job, key) for key in (
            "id", "phase_id", "kind", "status", "attempts", "error", "created_at", "available_at",
        )},
        "intervention_id": job.payload.get("intervention_id"),
        "model": connection.get("model"),
        "connection_version": connection.get("version"),
        "skill_slug": skill.get("slug"),
        "skill_version": skill.get("version"),
        "config_version": runtime.get("topic_version"),
    }


def assistant_overview(db: Session, group: Group, *, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    topic = db.get(Topic, group.topic_id)
    rules = topic.settings["rules"]
    connection = db.scalar(select(ModelConnection).where(ModelConnection.teacher_id == topic.teacher_id))
    jobs = db.scalars(select(AnalysisJob).where(
        AnalysisJob.group_id == group.id, AnalysisJob.phase_id == group.phase_id,
    )).all()
    items = db.scalars(select(Intervention).where(
        Intervention.group_id == group.id, Intervention.phase_id == group.phase_id,
    )).all()
    coding = Counter(job.status for job in jobs if job.kind == "analysis")
    prompts = Counter(item.status for item in items)
    reviewing = [item for item in items if group.state != "completed" and item.status == "published" and item.review_at is not None
                 and (item.effect is None or item.effect.get("result") == "insufficient-data")]
    due_times = [item.review_at for item in reviewing if item.effect is None]
    cooldown_until = (group.last_intervention_at + rules["cooldown_seconds"]
                      if group.last_intervention_at and group.state != "completed" else None)
    if cooldown_until is not None and cooldown_until <= now:
        cooldown_until = None
    model_status = "unconfigured" if connection is None else "ready" if connection.enabled else "disabled"
    if group.state != "active":
        status = group.state
    elif model_status != "ready":
        status = f"model-{model_status}"
    elif prompts["generating"]:
        status = "generating"
    elif coding["running"]:
        status = "analyzing"
    elif prompts["pending"] or prompts["notify"]:
        status = "needs-teacher"
    elif coding["pending"]:
        status = "queued"
    elif coding["failed"] or prompts["failed"]:
        status = "failed"
    elif cooldown_until:
        status = "cooldown"
    elif not rules["enabled"]:
        status = "manual"
    else:
        status = "monitoring"
    return {
        "status": status,
        "model_status": model_status,
        "model": connection.model if connection else None,
        "connection_version": connection.version if connection else None,
        "rules_enabled": rules["enabled"],
        "mode": rules["mode"],
        "window_seconds": rules["window_seconds"],
        "cooldown_seconds": rules["cooldown_seconds"],
        "analysis_pending": coding["pending"],
        "analysis_running": coding["running"],
        "analysis_blocked": coding["blocked"],
        "analysis_failed": coding["failed"],
        "retrying": sum(job.status == "pending" and job.error is not None for job in jobs),
        "generating": prompts["generating"],
        "pending_approval": prompts["pending"],
        "notifications": prompts["notify"],
        "generation_failed": prompts["failed"],
        "published": prompts["published"],
        "cooldown_until": cooldown_until,
        "review_pending": len(reviewing),
        "review_waiting_data": sum(item.effect is not None for item in reviewing),
        "next_review_at": min(due_times) if due_times else None,
        "updated_at": now,
    }
