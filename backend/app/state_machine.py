import time
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from transitions import Machine, MachineError

from .models import AuditEvent, Enrollment, Group, Intervention, Phase, Topic


def start_blocked_reason(db: Session, topic: Topic) -> str | None:
    missing = db.scalar(
        select(func.count())
        .select_from(Enrollment)
        .where(Enrollment.topic_id == topic.id, Enrollment.group_id.is_(None))
    )
    if missing:
        return f"{missing} 位学生尚未分组，请先为所有学生完成分组"
    groups = db.execute(
        select(Group.id, func.count(Enrollment.id))
        .outerjoin(Enrollment, Enrollment.group_id == Group.id)
        .where(Group.topic_id == topic.id)
        .group_by(Group.id)
    ).all()
    if not groups:
        return "请先创建讨论小组并完成分组"
    empty = sum(count == 0 for _, count in groups)
    if empty:
        return f"有 {empty} 个空小组，请先分配学生或移除空组"
    return None


def transition(
    db: Session,
    group: Group,
    topic: Topic,
    action: str,
    actor_id: str | None,
    expected_version: int | None = None,
):
    if expected_version is not None and group.version != expected_version:
        raise HTTPException(409, "小组状态已更新，请刷新后重试")
    if action == "start" and (reason := start_blocked_reason(db, topic)):
        raise HTTPException(409, reason)
    state = SimpleNamespace(state=group.state)
    machine = Machine(
        model=state,
        states=["waiting", "active", "paused", "completed"],
        initial=group.state,
        auto_transitions=False,
        transitions=[
            {"trigger": "start", "source": "waiting", "dest": "active"},
            {"trigger": "pause", "source": "active", "dest": "paused"},
            {"trigger": "resume", "source": "paused", "dest": "active"},
            {"trigger": "advance", "source": "active", "dest": "active"},
            {"trigger": "complete", "source": ["active", "paused"], "dest": "completed"},
        ],
    )
    try:
        machine.events[action].trigger(state)
    except (MachineError, KeyError):
        raise HTTPException(409, "当前小组状态不允许此操作") from None
    now = time.time()
    before = {"state": group.state, "phase_index": group.phase_index, "version": group.version}
    phases = topic.settings["stages"]
    if action == "start":
        members = db.scalars(select(Enrollment.user_id).where(Enrollment.group_id == group.id)).all()
        if not members:
            raise HTTPException(409, "小组至少需要一名学生才能开始")
        topic.status, topic.join_open = "active", False
    if action == "advance" and group.phase_index + 1 >= len(phases):
        action = "complete"
        state.state = "completed"
    if action in ("advance", "complete"):
        phase = db.get(Phase, group.phase_id)
        if phase:
            phase.ended_at = now
        if action == "advance":
            group.phase_index += 1
    if action in ("start", "advance"):
        members = list(db.scalars(select(Enrollment.user_id).where(Enrollment.group_id == group.id)).all())
        phase = Phase(
            group_id=group.id,
            index=group.phase_index,
            name=phases[group.phase_index]["name"],
            started_at=now,
            member_ids=members,
        )
        db.add(phase)
        db.flush()
        group.phase_id = phase.id
        group.deadline = now + phases[group.phase_index]["minutes"] * 60
        group.remaining_seconds = None
    elif action == "pause":
        group.remaining_seconds = max(0, (group.deadline or now) - now)
        group.deadline = None
    elif action == "resume":
        group.deadline = now + (group.remaining_seconds or 0)
        group.remaining_seconds = None
    elif action == "complete":
        group.deadline = None
        group.remaining_seconds = None
    group.state = state.state
    group.version += 1
    group.concerns = []
    group.intervention_state = "monitoring"
    pending = db.scalars(
        select(Intervention).where(
            Intervention.group_id == group.id, Intervention.status.in_(["generating", "pending", "notify"])
        )
    ).all()
    for intervention in pending:
        intervention.status = "stale"
    db.add(
        AuditEvent(
            topic_id=topic.id,
            group_id=group.id,
            actor_id=actor_id,
            event=f"group.{action}",
            data={
                "before": before,
                "after": {"state": group.state, "phase_index": group.phase_index, "version": group.version},
            },
        )
    )
    db.flush()
    groups = db.scalars(select(Group).where(Group.topic_id == topic.id)).all()
    if groups and all(item.state == "completed" for item in groups):
        topic.status = "completed"
    return group
