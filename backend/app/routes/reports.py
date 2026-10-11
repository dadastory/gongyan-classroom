import csv
import io
import json
import time

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    AnalysisJob,
    AuditEvent,
    Enrollment,
    Group,
    Intervention,
    MeaningUnit,
    Message,
    MetricSnapshot,
    Outcome,
    Phase,
    SkillVersion,
    User,
)
from ..security import require_topic, teacher
from ..skills import skill_dict
from ..views import entity_dict, intervention_dict, message_list, presentation, topic_detail, unit_dict

router = APIRouter(tags=["observatory"])


@router.get("/topics/{topic_id}/presentation")
def get_presentation(topic_id: str, user: User = Depends(teacher), db: Session = Depends(get_db)):
    topic = require_topic(db, topic_id, user, manage=True)
    return presentation(db, topic)


@router.get("/topics/{topic_id}/export.json")
def export_json(topic_id: str, user: User = Depends(teacher), db: Session = Depends(get_db)):
    topic = require_topic(db, topic_id, user, manage=True)
    group_ids = list(db.scalars(select(Group.id).where(Group.topic_id == topic.id)).all())
    messages = db.scalars(
        select(Message).where(Message.group_id.in_(group_ids)).order_by(Message.created_at)
    ).all()
    data = {
        "schema_version": "1.0",
        "exported_at": time.time(),
        "topic": topic_detail(db, topic, user),
        "messages": message_list(db, messages, include_analysis=True),
        "meaning_units": [
            unit_dict(unit)
            for unit in db.scalars(
                select(MeaningUnit).where(MeaningUnit.message_id.in_([m.id for m in messages]))
            )
        ],
        "outcomes": [
            entity_dict(item, ["id", "group_id", "phase_id", "author_id", "content", "created_at"])
            for item in db.scalars(select(Outcome).where(Outcome.group_id.in_(group_ids)))
        ],
        "phases": [
            entity_dict(phase, ["id", "group_id", "index", "name", "started_at", "ended_at", "member_ids"])
            for phase in db.scalars(select(Phase).where(Phase.group_id.in_(group_ids)))
        ],
        "analysis_runs": [
            public_analysis_run(job, db)
            for job in db.scalars(select(AnalysisJob).where(AnalysisJob.group_id.in_(group_ids)))
        ],
        "metric_snapshots": [
            entity_dict(
                item, ["id", "group_id", "phase_id", "window_start", "window_end", "data", "created_at"]
            )
            for item in db.scalars(select(MetricSnapshot).where(MetricSnapshot.group_id.in_(group_ids)))
        ],
        "interventions": [
            intervention_dict(item)
            for item in db.scalars(select(Intervention).where(Intervention.group_id.in_(group_ids)))
        ],
        "events": [
            entity_dict(item, ["id", "group_id", "actor_id", "event", "data", "created_at"])
            for item in db.scalars(select(AuditEvent).where(AuditEvent.topic_id == topic.id))
        ],
        "skills": [
            skill_dict(skill)
            for skill in db.scalars(
                select(SkillVersion)
                .where(SkillVersion.teacher_id == user.id)
                .order_by(SkillVersion.slug, SkillVersion.version)
            )
        ],
    }
    return Response(
        json.dumps(data, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="topic-{topic.id}-research.json"'},
    )


def public_analysis_run(job: AnalysisJob, db: Session) -> dict:
    result = entity_dict(job, ["id", "group_id", "phase_id", "kind", "status", "attempts", "created_at"])
    runtime = job.payload.get("runtime", job.payload)
    connection = runtime.get("connection", {})
    skill = runtime.get("skill", {})
    intervention = db.get(Intervention, job.payload["intervention_id"]) if job.kind == "intervention" else None
    result.update(
        {
            "message_ids": job.payload.get("message_ids", []),
            "intervention_id": job.payload.get("intervention_id"),
            "model": connection.get("model"),
            "connection_version": connection.get("version"),
            "skill_slug": skill.get("slug"),
            "skill_version": skill.get("version"),
            "skill_digest": skill.get("digest"),
            "config_version": runtime.get("topic_version", intervention.config_version if intervention else None),
            "topic_snapshot": runtime.get("topic"),
        }
    )
    return result


def safe_csv(value):
    value = str(value) if value is not None else ""
    return (
        "'" + value
        if value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r"))
        else value
    )


@router.get("/topics/{topic_id}/export.csv")
def export_csv(topic_id: str, user: User = Depends(teacher), db: Session = Depends(get_db)):
    topic = require_topic(db, topic_id, user, manage=True)
    groups = {group.id: group for group in db.scalars(select(Group).where(Group.topic_id == topic.id))}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "消息ID",
            "小组",
            "阶段ID",
            "作者",
            "类型",
            "时间戳",
            "原文",
            "回复ID",
            "认知编码",
            "情感编码",
            "有效任务发言",
            "分析状态",
        ]
    )
    messages = db.scalars(
        select(Message).where(Message.group_id.in_(list(groups))).order_by(Message.created_at, Message.id)
    ).all()
    for message in message_list(db, messages, include_analysis=True):
        units = message["units"]
        values = [
            message["id"],
            groups[message["group_id"]].name,
            message["phase_id"],
            message["author_name"],
            message["kind"],
            message["created_at"],
            message["content"],
            message["reply_to"],
            "|".join(unit["cognitive"] for unit in units),
            "|".join(unit["emotion"] for unit in units),
            any(unit["task_relevant"] for unit in units)
            if message["analysis_status"] == "complete"
            else None,
            message["analysis_status"],
        ]
        writer.writerow([safe_csv(value) for value in values])
    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="topic-{topic.id}-messages.csv"'},
    )


@router.delete("/topics/{topic_id}/students/{student_id}")
async def remove_student(
    topic_id: str, student_id: str, user: User = Depends(teacher), db: Session = Depends(get_db)
):
    from fastapi import HTTPException

    from ..db import lock_topic
    from ..realtime import hub

    require_topic(db, topic_id, user, manage=True)
    topic = lock_topic(db, topic_id)
    if topic.status != "preparing":
        raise HTTPException(409, "讨论开始后保留成员记录，不能移除学生")
    enrollment = db.scalar(
        select(Enrollment).where(Enrollment.topic_id == topic.id, Enrollment.user_id == student_id)
    )
    if enrollment:
        db.delete(enrollment)
        db.add(
            AuditEvent(
                topic_id=topic.id, actor_id=user.id, event="student.removed", data={"user_id": student_id}
            )
        )
        db.commit()
        await hub.revoke_topic_member(topic.id, student_id)
        await hub.broadcast(topic.id, {"type": "membership"})
    return {"ok": True}
