from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .metrics import calculate_metrics, rule_candidates
from .models import (
    AnalysisJob,
    AuditEvent,
    Enrollment,
    Group,
    Intervention,
    MeaningUnit,
    Message,
    MetricSnapshot,
    Outcome,
    Topic,
    User,
)
from .observation import assistant_overview, job_view
from .realtime import hub
from .state_machine import start_blocked_reason


def entity_dict(item, fields: list[str]) -> dict:
    return {field: getattr(item, field) for field in fields}


def unit_dict(unit: MeaningUnit) -> dict:
    return entity_dict(
        unit,
        [
            "id",
            "message_id",
            "start",
            "end",
            "quote",
            "cognitive",
            "emotion",
            "task_relevant",
            "metacognitive",
            "social",
            "reason",
            "confidence",
            "skill_slug",
            "skill_version",
            "config_version",
            "model",
            "corrected",
            "created_at",
        ],
    )


def message_dict(db: Session, message: Message, *, include_analysis: bool = False) -> dict:
    return message_list(db, [message], include_analysis=include_analysis)[0]


def message_list(db: Session, messages: list[Message], *, include_analysis: bool = False) -> list[dict]:
    if not messages:
        return []
    authors = {
        user.id: user.name
        for user in db.scalars(
            select(User).where(User.id.in_({m.author_id for m in messages if m.author_id}))
        )
    }
    units = defaultdict(list)
    if include_analysis:
        for unit in db.scalars(
            select(MeaningUnit)
            .where(MeaningUnit.message_id.in_([m.id for m in messages]))
            .order_by(MeaningUnit.start, MeaningUnit.id)
        ):
            units[unit.message_id].append(unit_dict(unit))
    return [
        _message_payload(
            message,
            authors.get(message.author_id, "协作学习助手"),
            units.get(message.id, []) if include_analysis else None,
        )
        for message in messages
    ]


def _message_payload(message: Message, author_name: str, units: list[dict] | None) -> dict:
    result = entity_dict(
        message,
        [
            "id",
            "group_id",
            "phase_id",
            "author_id",
            "kind",
            "content",
            "reply_to",
            "analysis_status",
            "created_at",
        ],
    )
    result["author_name"] = author_name
    if units is not None:
        result["units"] = units
    return result


def intervention_dict(item: Intervention) -> dict:
    return entity_dict(
        item,
        [
            "id",
            "group_id",
            "phase_id",
            "rule",
            "skill_slug",
            "skill_version",
            "config_version",
            "model",
            "mode",
            "status",
            "content",
            "evidence",
            "target_user_id",
            "published_at",
            "review_at",
            "effect",
            "created_at",
        ],
    )


def group_summary(db: Session, group: Group, teacher: bool = False) -> dict:
    result = entity_dict(
        group,
        [
            "id",
            "topic_id",
            "name",
            "direction",
            "capacity",
            "state",
            "phase_index",
            "version",
            "phase_id",
            "deadline",
            "remaining_seconds",
        ],
    )
    enrollments = db.scalars(
        select(Enrollment).where(Enrollment.group_id == group.id).order_by(Enrollment.created_at)
    ).all()
    result["member_count"] = len(enrollments)
    result["online_count"] = sum(
        enrollment.user_id in hub.online_ids(group.topic_id) for enrollment in enrollments
    )
    if teacher:
        result["members"] = [
            {
                "id": enrollment.user_id,
                "name": db.get(User, enrollment.user_id).name,
                "online": enrollment.user_id in hub.online_ids(group.topic_id),
            }
            for enrollment in enrollments
        ]
        result["metrics"] = calculate_metrics(db, group)
        result["concerns"] = [
            {"rule": item["rule"], "reason": item["reason"]}
            for item in rule_candidates(db, group, result["metrics"])
        ]
        result["intervention_state"] = group.intervention_state
        result["assistant"] = assistant_overview(db, group)
    return result


def topic_summary(db: Session, topic: Topic) -> dict:
    result = entity_dict(
        topic,
        [
            "id",
            "title",
            "description",
            "join_code",
            "join_open",
            "status",
            "settings",
            "config_version",
            "created_at",
            "is_demo",
        ],
    )
    result["student_count"] = db.scalar(
        select(func.count()).select_from(Enrollment).where(Enrollment.topic_id == topic.id)
    )
    result["group_count"] = db.scalar(
        select(func.count()).select_from(Group).where(Group.topic_id == topic.id)
    )
    result["online_count"] = len(
        hub.online_ids(topic.id)
        & set(db.scalars(select(Enrollment.user_id).where(Enrollment.topic_id == topic.id)).all())
    )
    return result


def topic_detail(db: Session, topic: Topic, user: User) -> dict:
    teacher = user.role == "teacher"
    result = topic_summary(db, topic)
    result["references"] = topic.references
    result["teacher_name"] = db.get(User, topic.teacher_id).name
    groups = db.scalars(select(Group).where(Group.topic_id == topic.id).order_by(Group.created_at)).all()
    result["groups"] = [group_summary(db, group, teacher) for group in groups]
    enrollments = db.scalars(
        select(Enrollment).where(Enrollment.topic_id == topic.id).order_by(Enrollment.created_at)
    ).all()
    result["my_group_id"] = next(
        (enrollment.group_id for enrollment in enrollments if enrollment.user_id == user.id), None
    )
    if teacher:
        result["start_blocked_reason"] = (
            start_blocked_reason(db, topic) if topic.status == "preparing" else None
        )
        result["students"] = [
            {
                "id": enrollment.user_id,
                "name": db.get(User, enrollment.user_id).name,
                "group_id": enrollment.group_id,
                "online": enrollment.user_id in hub.online_ids(topic.id),
            }
            for enrollment in enrollments
        ]
        group_ids = [group.id for group in groups]
        result["interventions"] = [
            intervention_dict(item)
            for item in db.scalars(
                select(Intervention)
                .where(Intervention.group_id.in_(group_ids))
                .order_by(Intervention.created_at.desc())
                .limit(40)
            )
        ]
        result["events"] = [
            entity_dict(event, ["id", "group_id", "event", "data", "created_at"])
            for event in db.scalars(
                select(AuditEvent)
                .where(AuditEvent.topic_id == topic.id)
                .order_by(AuditEvent.created_at.desc())
                .limit(30)
            )
        ]
    else:
        # Rule configuration is instructional administration, not part of student flows.
        result["settings"] = {key: value for key, value in result["settings"].items() if key != "rules"}
    return result


def group_detail(db: Session, group: Group, topic: Topic, user: User) -> dict:
    teacher = user.role == "teacher"
    result = group_summary(db, group, teacher)
    result["topic_title"] = topic.title
    result["stages"] = topic.settings["stages"]
    result["instructions"] = topic.description
    result["references"] = topic.references
    if teacher:
        result["start_blocked_reason"] = start_blocked_reason(db, topic) if group.state == "waiting" else None
    if not teacher:
        result["members"] = [
            {
                "id": enrollment.user_id,
                "name": db.get(User, enrollment.user_id).name,
                "online": enrollment.user_id in hub.online_ids(topic.id),
            }
            for enrollment in db.scalars(
                select(Enrollment).where(Enrollment.group_id == group.id).order_by(Enrollment.created_at)
            )
        ]
    messages = db.scalars(
        select(Message)
        .where(Message.group_id == group.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(100)
    ).all()
    result["messages"] = message_list(db, list(reversed(messages)), include_analysis=teacher)
    result["message_count"] = db.scalar(
        select(func.count()).select_from(Message).where(Message.group_id == group.id)
    )
    result["outcomes"] = [
        entity_dict(outcome, ["id", "phase_id", "author_id", "content", "created_at"])
        for outcome in db.scalars(
            select(Outcome).where(Outcome.group_id == group.id).order_by(Outcome.created_at.desc())
        )
    ]
    if teacher:
        result["interventions"] = [
            intervention_dict(item)
            for item in db.scalars(
                select(Intervention)
                .where(Intervention.group_id == group.id)
                .order_by(Intervention.created_at.desc())
            )
        ]
        result["snapshots"] = [
            entity_dict(snapshot, ["id", "window_start", "window_end", "data", "created_at"])
            for snapshot in db.scalars(
                select(MetricSnapshot)
                .where(MetricSnapshot.group_id == group.id)
                .order_by(MetricSnapshot.created_at.desc())
                .limit(30)
            )
        ]
        result["jobs"] = [
            job_view(job)
            for job in db.scalars(
                select(AnalysisJob)
                .where(AnalysisJob.group_id == group.id)
                .order_by(AnalysisJob.created_at.desc())
                .limit(20)
            )
        ]
    return result


def presentation(db: Session, topic: Topic) -> dict:
    groups = db.scalars(select(Group).where(Group.topic_id == topic.id).order_by(Group.created_at)).all()
    output = {
        "id": topic.id,
        "title": topic.title,
        "status": topic.status,
        "stages": topic.settings["stages"],
        "student_count": db.scalar(
            select(func.count()).select_from(Enrollment).where(Enrollment.topic_id == topic.id)
        ),
        "groups": [],
    }
    for index, group in enumerate(groups, start=1):
        metrics = calculate_metrics(db, group)
        # Deliberately construct a whitelist payload; no member IDs, names or personal emotions.
        safe_metrics = {
            key: metrics[key]
            for key in [
                "NA",
                "NS",
                "TC",
                "SD",
                "SR",
                "SE",
                "member_count",
                "total_messages",
                "pending_messages",
                "failed_messages",
                "analysis_state",
                "last_analyzed_at",
                "coverage",
                "cognitive",
            ]
        }
        assistant = assistant_overview(db, group)
        output["groups"].append(
            {
                "name": f"第 {index} 组",
                "state": group.state,
                "phase_index": group.phase_index,
                "deadline": group.deadline,
                "metrics": safe_metrics,
                "support_status": assistant["status"],
                "pending_prompts": assistant["pending_approval"] + assistant["notifications"],
                "online_count": group_summary(db, group)["online_count"],
            }
        )
    return output
