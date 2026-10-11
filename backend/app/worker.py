import asyncio
import hashlib
import json
import logging
import time
from contextlib import suppress

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .agent_runtime import analysis_prompt, run_agent, validate_analysis
from .config import settings
from .db import SessionLocal, lock_topic
from .metrics import calculate_metrics, rule_candidates
from .models import (
    AnalysisJob,
    AuditEvent,
    Group,
    Intervention,
    MeaningUnit,
    Message,
    MetricSnapshot,
    ModelConnection,
    Phase,
    Topic,
)
from .realtime import hub
from .schemas import AnalysisOutput, InterventionOutput
from .skills import latest_skills, skill_dict

logger = logging.getLogger(__name__)


def connection_dict(connection: ModelConnection) -> dict:
    return {
        "base_url": connection.base_url,
        "model": connection.model,
        "encrypted_key": connection.encrypted_key,
        "timeout_seconds": connection.timeout_seconds,
        "output_mode": connection.output_mode,
        "version": connection.version,
    }


def enqueue_analysis(db: Session, message: Message):
    job = db.scalar(
        select(AnalysisJob)
        .where(
            AnalysisJob.group_id == message.group_id,
            AnalysisJob.phase_id == message.phase_id,
            AnalysisJob.kind == "analysis",
            AnalysisJob.status == "pending",
        )
        .order_by(AnalysisJob.created_at)
        .with_for_update()
    )
    if job and len(job.payload["message_ids"]) < 20:
        job.payload = {**job.payload, "message_ids": [*job.payload["message_ids"], message.id]}
    else:
        db.add(
            AnalysisJob(
                dedupe_key=f"analysis:{message.id}",
                group_id=message.group_id,
                phase_id=message.phase_id,
                payload={"message_ids": [message.id]},
                available_at=time.time() + settings().analysis_delay_seconds,
            )
        )


def publish_intervention(
    db: Session, intervention: Intervention, group: Group, topic: Topic, actor_id: str | None = None
):
    if intervention.status == "published":
        return
    if (
        group.state != "active"
        or group.phase_id != intervention.phase_id
        or group.version != intervention.group_version
        or topic.config_version != intervention.config_version
    ):
        intervention.status = "stale"
        raise HTTPException(409, "讨论状态已变化，此提示已过期")
    now = time.time()
    if (
        group.last_intervention_at
        and now - group.last_intervention_at < topic.settings["rules"]["cooldown_seconds"]
    ):
        raise HTTPException(409, "小组正在干预冷却期，稍后再处理")
    message = Message(
        group_id=group.id,
        phase_id=group.phase_id,
        kind="ai",
        content=intervention.content,
        analysis_status="not-applicable",
    )
    db.add(message)
    db.flush()
    intervention.status, intervention.message_id = "published", message.id
    intervention.published_at = now
    intervention.review_at = now + topic.settings["rules"]["cooldown_seconds"]
    group.last_intervention_at, group.intervention_state = now, "cooldown"
    db.add(
        AuditEvent(
            topic_id=topic.id,
            group_id=group.id,
            actor_id=actor_id,
            event="intervention.published",
            data={
                "intervention_id": intervention.id,
                "rule": intervention.rule,
                "skill": intervention.skill_slug,
                "skill_version": intervention.skill_version,
                "message_id": message.id,
            },
        )
    )


def schedule_intervention(db: Session, group: Group, candidate: dict, *, force: bool = False):
    topic = db.get(Topic, group.topic_id)
    connection = db.scalar(select(ModelConnection).where(ModelConnection.teacher_id == topic.teacher_id))
    if not connection or not connection.enabled:
        raise HTTPException(409, "请先配置并启用模型连接")
    rules = topic.settings["rules"]
    now = time.time()
    if (
        not force
        and group.last_intervention_at
        and now - group.last_intervention_at < rules["cooldown_seconds"]
    ):
        return None
    slug = "group-summary" if candidate["rule"] == "summary" else rules["bindings"][candidate["rule"]]
    skill = latest_skills(db, topic.teacher_id).get(slug)
    if not skill:
        raise HTTPException(409, f"绑定的 skill 不存在：{slug}")
    evidence = {**candidate, "metrics": calculate_metrics(db, group), "rule_settings": rules}
    fingerprint = hashlib.sha256(
        json.dumps(
            {"rule": candidate["rule"], "ids": candidate["message_ids"], "group_version": group.version},
            sort_keys=True,
        ).encode()
    ).hexdigest()[:24]
    dedupe = f"intervention:{group.id}:{group.phase_id}:{fingerprint}"
    existing = db.scalar(select(Intervention).where(Intervention.dedupe_key == dedupe))
    if existing:
        return existing
    item = Intervention(
        dedupe_key=dedupe,
        group_id=group.id,
        phase_id=group.phase_id,
        group_version=group.version,
        rule=candidate["rule"],
        skill_slug=slug,
        skill_version=skill.version,
        config_version=topic.config_version,
        model=connection.model,
        mode="approval" if force else rules["mode"],
        evidence=evidence,
        target_user_id=candidate.get("target_user_id"),
    )
    db.add(item)
    db.flush()
    if item.mode == "notify":
        item.status = "notify"
        group.intervention_state = "needs-teacher"
    else:
        db.add(
            AnalysisJob(
                dedupe_key=f"generate:{item.id}",
                group_id=group.id,
                phase_id=group.phase_id,
                kind="intervention",
                payload={
                    "intervention_id": item.id,
                    "skill": skill_dict(skill),
                    "connection": connection_dict(connection),
                    "topic_version": topic.config_version,
                    "topic": {
                        "title": topic.title,
                        "instructions": topic.description,
                        "references": topic.references,
                    },
                },
            )
        )
        group.intervention_state = "generating"
    db.add(
        AuditEvent(
            topic_id=topic.id,
            group_id=group.id,
            event="intervention.requested",
            data={
                "intervention_id": item.id,
                "rule": item.rule,
                "skill": slug,
                "skill_version": skill.version,
                "mode": item.mode,
            },
        )
    )
    return item


class AnalysisWorker:
    def __init__(self):
        self.task: asyncio.Task | None = None
        self.running: dict[str, asyncio.Task] = {}
        self.last_evaluation: dict[str, float] = {}

    async def start(self):
        if settings().worker_enabled:
            # The classroom deployment runs one worker process. Recover its previous leases on restart.
            with SessionLocal() as db:
                for job in db.scalars(select(AnalysisJob).where(AnalysisJob.status == "running")):
                    job.status, job.lease_until = "pending", None
                db.commit()
            self.task = asyncio.create_task(self.loop())

    async def stop(self):
        tasks = [task for task in [self.task, *self.running.values()] if task]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task

    def claim(self) -> str | None:
        with SessionLocal() as db:
            now = time.time()
            expired = db.scalars(
                select(AnalysisJob).where(AnalysisJob.status == "running", AnalysisJob.lease_until < now)
            ).all()
            for job in expired:
                job.status, job.lease_until = "pending", None
            db.flush()
            query = select(AnalysisJob).where(
                AnalysisJob.status == "pending", AnalysisJob.available_at <= now
            )
            if self.running:
                query = query.where(AnalysisJob.group_id.not_in(list(self.running)))
            job = db.scalar(
                query.order_by(AnalysisJob.available_at).with_for_update(skip_locked=True).limit(1)
            )
            if not job:
                db.commit()
                return None
            job.status, job.lease_until = "running", now + 240
            job.attempts += 1
            db.commit()
            return job.id

    async def process(self, job_id: str):
        topic_id = None
        try:
            with SessionLocal() as db:
                job = db.get(AnalysisJob, job_id)
                if job.status == "complete":
                    return
                group = db.get(Group, job.group_id)
                topic = db.get(Topic, group.topic_id)
                topic_id = topic.id
                if job.kind == "analysis":
                    connection = db.scalar(
                        select(ModelConnection).where(ModelConnection.teacher_id == topic.teacher_id)
                    )
                    if not connection or not connection.enabled:
                        job.status = "blocked"
                        job.error = "模型尚未配置或未启用"
                        for message in db.scalars(
                            select(Message).where(Message.id.in_(job.payload["message_ids"]))
                        ):
                            message.analysis_status = "unconfigured"
                        db.commit()
                        return
                    skill = latest_skills(db, topic.teacher_id)["engagement-coding"]
                    phase = db.get(Phase, job.phase_id)
                    messages = db.scalars(
                        select(Message)
                        .where(Message.id.in_(job.payload["message_ids"]))
                        .order_by(Message.created_at)
                    ).all()
                    to_code = [
                        {
                            "id": message.id,
                            "content": message.content,
                            "author_id": message.author_id,
                            "reply_to": message.reply_to,
                        }
                        for message in messages
                    ]
                    context = db.scalars(
                        select(Message)
                        .where(
                            Message.group_id == group.id,
                            Message.phase_id == phase.id,
                            Message.created_at < min(m.created_at for m in messages),
                        )
                        .order_by(Message.created_at.desc())
                        .limit(12)
                    ).all()
                    context_data = [
                        {"id": m.id, "author_id": m.author_id, "content": m.content, "kind": m.kind}
                        for m in reversed(context)
                    ]
                    runtime = job.payload.get("runtime") or {
                        "connection": connection_dict(connection),
                        "skill": skill_dict(skill),
                        "topic_version": topic.config_version,
                        "topic": {
                            "title": topic.title,
                            "instructions": topic.description,
                            "references": topic.references,
                        },
                    }
                    job.payload = {**job.payload, "runtime": runtime}
                    prompt = analysis_prompt(runtime["topic"], phase.name, to_code, context_data)
                    db.commit()
                else:
                    item = db.get(Intervention, job.payload["intervention_id"])
                    if (
                        item.status != "generating"
                        or group.phase_id != item.phase_id
                        or group.version != item.group_version
                        or topic.config_version != item.config_version
                        or group.state != "active"
                    ):
                        job.status = "stale"
                        if item.status == "generating":
                            item.status = "stale"
                        db.commit()
                        return
                    runtime = job.payload
                    messages = db.scalars(
                        select(Message)
                        .where(Message.group_id == group.id, Message.phase_id == group.phase_id)
                        .order_by(Message.created_at.desc())
                        .limit(30)
                    ).all()
                    prompt = json.dumps(
                        {
                            "topic": runtime.get("topic", {}).get("title", topic.title),
                            "instructions": runtime.get("topic", {}).get("instructions", topic.description),
                            "phase": topic.settings["stages"][group.phase_index]["name"],
                            "trigger": item.evidence,
                            "discussion": [
                                {"id": m.id, "content": m.content, "kind": m.kind} for m in reversed(messages)
                            ],
                        },
                        ensure_ascii=False,
                    )
                    db.commit()
            schema = AnalysisOutput if job.kind == "analysis" else InterventionOutput
            # Show the committed running task and its frozen versions before a slow model returns.
            await hub.broadcast(topic_id, {"type": "analysis"})
            output = await run_agent(runtime["connection"], runtime["skill"], prompt, schema)
            if job.kind == "analysis":
                validate_analysis(output, to_code)
            with SessionLocal() as db:
                job = db.get(AnalysisJob, job_id)
                group = db.get(Group, job.group_id)
                topic = lock_topic(db, group.topic_id)
                db.refresh(group)
                if job.kind == "analysis":
                    for coded in output.messages:
                        message = db.get(Message, coded.message_id)
                        existing = db.scalar(
                            select(MeaningUnit.id).where(MeaningUnit.message_id == message.id)
                        )
                        if existing:
                            continue
                        for unit in coded.units:
                            db.add(
                                MeaningUnit(
                                    message_id=message.id,
                                    phase_id=message.phase_id,
                                    **unit.model_dump(),
                                    skill_slug=runtime["skill"]["slug"],
                                    skill_version=runtime["skill"]["version"],
                                    config_version=runtime["topic_version"],
                                    model=runtime["connection"]["model"],
                                )
                            )
                        message.analysis_status = "complete"
                    db.flush()
                    metrics = calculate_metrics(db, group, phase_id=job.phase_id)
                    db.add(
                        MetricSnapshot(
                            group_id=group.id,
                            phase_id=job.phase_id,
                            window_start=metrics["window_start"],
                            window_end=metrics["window_end"],
                            data=metrics,
                        )
                    )
                else:
                    item = db.get(Intervention, job.payload["intervention_id"])
                    if (
                        item.status == "generating"
                        and group.version == item.group_version
                        and group.phase_id == item.phase_id
                        and group.state == "active"
                        and topic.config_version == item.config_version
                    ):
                        item.content = output.content
                        item.evidence = {**item.evidence, "agent_rationale": output.rationale}
                        item.status = "pending"
                        group.intervention_state = "needs-teacher"
                        if item.mode == "automatic":
                            try:
                                publish_intervention(db, item, group, topic)
                            except HTTPException:
                                item.status = "stale"
                    elif item.status == "generating":
                        item.status = "stale"
                job.status, job.error, job.lease_until = "complete", None, None
                db.commit()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Do not log provider bodies, URLs with query strings or decrypted credentials.
            error_type = type(error).__name__
            logger.warning("Agent job failed: %s (%s)", job_id, error_type)
            with SessionLocal() as db:
                job = db.get(AnalysisJob, job_id)
                if job:
                    job.error = f"{error_type}: 模型调用或结构校验失败，请检查连接及输出模式"
                    job.status = "failed" if job.attempts >= 3 else "pending"
                    job.available_at, job.lease_until = time.time() + 15 * job.attempts, None
                    runtime = job.payload.get("runtime", job.payload)
                    connection = runtime.get("connection", {})
                    skill = runtime.get("skill", {})
                    db.add(AuditEvent(
                        topic_id=db.get(Group, job.group_id).topic_id,
                        group_id=job.group_id,
                        event="analysis.attempt_failed",
                        data={
                            "job_id": job.id,
                            "kind": job.kind,
                            "attempt": job.attempts,
                            "status": job.status,
                            "error_type": error_type,
                            "model": connection.get("model"),
                            "connection_version": connection.get("version"),
                            "skill_slug": skill.get("slug"),
                            "skill_version": skill.get("version"),
                            "skill_digest": skill.get("digest"),
                            "config_version": runtime.get("topic_version"),
                        },
                    ))
                    if job.status == "failed":
                        if job.kind == "analysis":
                            for message in db.scalars(
                                select(Message).where(Message.id.in_(job.payload["message_ids"]))
                            ):
                                message.analysis_status = "failed"
                        else:
                            item = db.get(Intervention, job.payload["intervention_id"])
                            if item.status == "generating":
                                item.status = "failed"
                                db.get(Group, job.group_id).intervention_state = "monitoring"
                    db.commit()
        finally:
            if topic_id:
                await hub.broadcast(topic_id, {"type": "analysis"})

    async def evaluate(self):
        with SessionLocal() as db:
            now = time.time()
            groups = db.scalars(select(Group).where(Group.state == "active")).all()
            changed = set()
            for group in groups:
                if now - self.last_evaluation.get(group.id, 0) < 15:
                    continue
                self.last_evaluation[group.id] = now
                topic = lock_topic(db, group.topic_id)
                db.refresh(group)
                if group.state != "active":
                    continue
                metrics = calculate_metrics(db, group)
                candidates = rule_candidates(db, group, metrics, now)
                concerns = [{"rule": item["rule"], "reason": item["reason"]} for item in candidates]
                if group.concerns != concerns:
                    group.concerns = concerns
                    changed.add(topic.id)
                due = db.scalars(
                    select(Intervention).where(
                        Intervention.group_id == group.id,
                        Intervention.status == "published",
                        Intervention.review_at <= now,
                        or_(Intervention.effect.is_(None),
                            Intervention.effect["result"].as_string() == "insufficient-data"),
                    )
                ).all()
                for item in due:
                    if item.phase_id != group.phase_id:
                        item.effect = {"result": "phase-changed", "reviewed_at": now}
                    else:
                        still_present = item.rule in [c["rule"] for c in candidates]
                        observed = db.scalar(
                            select(func.count()).select_from(Message).where(
                                Message.group_id == group.id,
                                Message.phase_id == item.phase_id,
                                Message.kind == "student",
                                Message.analysis_status == "complete",
                                Message.created_at > (item.published_at or now),
                                Message.created_at >= metrics["window_start"],
                                Message.created_at <= metrics["window_end"],
                            )
                        )
                        required = topic.settings["rules"]["min_messages"]
                        result = (
                            "insufficient-data"
                            if metrics["pending_messages"] or metrics["failed_messages"] or observed < required
                            else "persists"
                            if still_present
                            else "not-observed"
                        )
                        previous_effect = item.effect or {}
                        previous_after = previous_effect.get("after", {})
                        if (
                            result == "insufficient-data"
                            and previous_effect.get("result") == result
                            and previous_effect.get("observed_messages") == observed
                            and previous_effect.get("required_messages") == required
                            and previous_after.get("pending_messages") == metrics["pending_messages"]
                            and previous_after.get("failed_messages") == metrics["failed_messages"]
                        ):
                            continue
                        item.effect = {
                            "result": result,
                            "reviewed_at": now,
                            "after": metrics,
                            "observed_messages": observed,
                            "required_messages": required,
                            "note": "观察窗口变化，不能据此推断因果效果",
                        }
                    group.intervention_state = "monitoring"
                    changed.add(topic.id)
                pending = db.scalar(
                    select(Intervention.id).where(
                        Intervention.group_id == group.id,
                        Intervention.status.in_(["generating", "pending", "notify"]),
                    )
                )
                if candidates and topic.settings["rules"]["enabled"] and not pending:
                    with suppress(HTTPException):
                        if schedule_intervention(db, group, candidates[0]):
                            changed.add(topic.id)
                db.commit()
            for topic_id in changed:
                await hub.broadcast(topic_id, {"type": "state"})

    async def loop(self):
        while True:
            try:
                for group_id, task in list(self.running.items()):
                    if task.done():
                        with suppress(Exception):
                            task.result()
                        self.running.pop(group_id)
                while len(self.running) < 3:
                    job_id = self.claim()
                    if not job_id:
                        break
                    with SessionLocal() as db:
                        group_id = db.get(AnalysisJob, job_id).group_id
                    self.running[group_id] = asyncio.create_task(self.process(job_id))
                await self.evaluate()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("Worker tick failed (%s)", type(error).__name__)
            await asyncio.sleep(settings().worker_interval_seconds)


worker = AnalysisWorker()
