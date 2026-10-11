import time
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AuditEvent, Enrollment, Group, MeaningUnit, Message, Outcome, Phase, Topic, User


def active_seconds(start: float, end: float, events: list[AuditEvent]) -> float:
    paused_at = None
    paused_seconds = 0.0
    for event in sorted(events, key=lambda event: event.created_at):
        if event.created_at > end:
            break
        if event.event == "group.pause":
            paused_at = event.created_at
        elif event.event == "group.resume" and paused_at is not None:
            paused_seconds += max(0, event.created_at - max(start, paused_at))
            paused_at = None
    if paused_at is not None:
        paused_seconds += max(0, end - max(start, paused_at))
    return max(0, end - start - paused_seconds)


def calculate_metrics(
    db: Session,
    group: Group,
    *,
    now: float | None = None,
    window_seconds: int | None = None,
    phase_id: str | None = None,
) -> dict:
    now = now or time.time()
    topic = db.get(Topic, group.topic_id)
    phase = db.get(Phase, phase_id or group.phase_id) if phase_id or group.phase_id else None
    member_ids = (
        phase.member_ids
        if phase
        else list(db.scalars(select(Enrollment.user_id).where(Enrollment.group_id == group.id)).all())
    )
    users = {user.id: user for user in db.scalars(select(User).where(User.id.in_(member_ids))).all()}
    events = db.scalars(
        select(AuditEvent).where(
            AuditEvent.group_id == group.id, AuditEvent.event.in_(["group.pause", "group.resume"])
        )
    ).all()
    end = min(now, phase.ended_at) if phase and phase.ended_at else now
    if group.state == "paused" and phase and phase.id == group.phase_id:
        pauses = [event.created_at for event in events if event.event == "group.pause"]
        if pauses:
            end = min(end, max(pauses))
    started = phase.started_at if phase else now
    window_seconds = window_seconds or topic.settings["rules"]["window_seconds"]
    start = max(started, end - window_seconds)
    messages = (
        db.scalars(
            select(Message)
            .where(
                Message.group_id == group.id,
                Message.phase_id == (phase.id if phase else None),
                Message.kind == "student",
                Message.created_at >= start,
                Message.created_at <= end,
            )
            .order_by(Message.created_at, Message.id)
        ).all()
        if phase
        else []
    )
    all_messages = (
        db.scalars(
            select(Message)
            .where(
                Message.group_id == group.id,
                Message.phase_id == phase.id,
                Message.kind == "student",
                Message.created_at <= end,
            )
            .order_by(Message.created_at)
        ).all()
        if phase
        else []
    )
    message_ids = [message.id for message in all_messages]
    units = db.scalars(select(MeaningUnit).where(MeaningUnit.message_id.in_(message_ids))).all()
    units_by_message = defaultdict(list)
    for unit in units:
        units_by_message[unit.message_id].append(unit)
    effective = [
        message for message in messages if any(unit.task_relevant for unit in units_by_message[message.id])
    ]
    phase_effective = [
        message
        for message in all_messages
        if any(unit.task_relevant for unit in units_by_message[message.id])
    ]
    counts = Counter(message.author_id for message in effective)
    message_map = {message.id: message for message in all_messages}
    edges = set()
    for message in effective:
        target = message_map.get(message.reply_to)
        if target and target.author_id in member_ids and target.author_id != message.author_id:
            edges.add((message.author_id, target.author_id))
    pairs = {tuple(sorted(edge)) for edge in edges}
    reciprocal = sum((a, b) in edges and (b, a) in edges for a, b in pairs)
    n, ns = len(member_ids), len(effective)
    mean = ns / n if n else 0
    variance = sum((counts[member] - mean) ** 2 for member in member_ids) / n if n and ns else None
    window_ids = {message.id for message in messages}
    window_units = [unit for unit in units if unit.message_id in window_ids]
    cognitive = Counter(unit.cognitive for unit in window_units)
    emotion = Counter(unit.emotion for unit in window_units)
    social = Counter(label for unit in window_units for label in unit.social)
    metacognitive = Counter(label for unit in window_units for label in unit.metacognitive)
    students = []
    for member_id in member_ids:
        effective_times = [message.created_at for message in effective if message.author_id == member_id]
        phase_times = [message.created_at for message in phase_effective if message.author_id == member_id]
        own_messages = [message for message in messages if message.author_id == member_id]
        own_ids = {message.id for message in own_messages}
        own_units = [unit for unit in window_units if unit.message_id in own_ids]
        intervals = [active_seconds(a, b, events) for a, b in zip(effective_times, effective_times[1:])]
        last_activity = max(
            (message.created_at for message in all_messages if message.author_id == member_id), default=None
        )
        students.append(
            {
                "user_id": member_id,
                "name": users[member_id].name if member_id in users else "已退出成员",
                "NS": counts[member_id],
                "total_messages": len(own_messages),
                "Max_TS": round(max(intervals), 1) if intervals else None,
                "silence_seconds": round(active_seconds(max(phase_times, default=started), end, events), 1)
                if phase
                else None,
                "last_activity": last_activity,
                "cognitive": {
                    f"C{i}": sum(unit.cognitive == f"C{i}" for unit in own_units) for i in range(6)
                },
                "emotion": {f"E{i}": sum(unit.emotion == f"E{i}" for unit in own_units) for i in range(4)},
            }
        )
    intervals = [student["Max_TS"] for student in students if student["Max_TS"] is not None]
    outcomes = (
        db.scalars(select(Outcome).where(Outcome.group_id == group.id, Outcome.phase_id == phase.id)).all()
        if phase
        else []
    )
    pending = sum(message.analysis_status in ("pending", "unconfigured") for message in messages)
    failed = sum(message.analysis_status == "failed" for message in messages)
    last_analyzed = max((unit.created_at for unit in units), default=None)
    return {
        "NA": len(counts),
        "NS": ns,
        "Max_TS": max(intervals) if intervals else None,
        "TC": bool(outcomes),
        "SD": round(len(edges) / (n * (n - 1)), 4) if n >= 2 else None,
        "SR": round(reciprocal / len(pairs), 4) if pairs else None,
        "SE": round(variance, 3) if variance is not None else None,
        "SC": None,
        "member_count": n,
        "total_messages": len(messages),
        "pending_messages": pending,
        "failed_messages": failed,
        "last_analyzed_at": last_analyzed,
        "coverage": round((len(messages) - pending - failed) / len(messages), 3) if messages else None,
        "cognitive": {f"C{i}": cognitive[f"C{i}"] for i in range(6)},
        "emotion": {f"E{i}": emotion[f"E{i}"] for i in range(4)},
        "social": {f"SS{i}": social[f"SS{i}"] for i in range(1, 6)},
        "metacognitive": {f"M{i}": metacognitive[f"M{i}"] for i in range(1, 4)},
        "students": students,
        "edges": [{"source": a, "target": b} for a, b in sorted(edges)],
        "window_start": start,
        "window_end": end,
        "phase_id": phase.id if phase else None,
        "analysis_state": "failed"
        if failed
        else "pending"
        if pending
        else "ready"
        if messages
        else "observing",
    }


def rule_candidates(db: Session, group: Group, metrics: dict, now: float | None = None) -> list[dict]:
    now = now or time.time()
    topic = db.get(Topic, group.topic_id)
    rules = topic.settings["rules"]
    if (
        group.state != "active"
        or not group.phase_id
        or metrics["pending_messages"]
        or metrics["failed_messages"]
    ):
        return []
    messages = db.scalars(
        select(Message)
        .where(
            Message.group_id == group.id,
            Message.phase_id == group.phase_id,
            Message.kind == "student",
            Message.analysis_status == "complete",
            Message.created_at >= metrics["window_start"],
            Message.created_at <= metrics["window_end"],
        )
        .order_by(Message.created_at)
    ).all()
    units = db.scalars(
        select(MeaningUnit).where(
            MeaningUnit.message_id.in_([m.id for m in messages]), MeaningUnit.confidence >= 0.6
        )
    ).all()
    coded = defaultdict(list)
    for unit in units:
        coded[unit.message_id].append(unit)
    candidates = []
    recent = messages[-rules["min_messages"] :]
    has_progress = any(unit.cognitive in ("C3", "C4", "C5") for unit in units)
    pause_events = db.scalars(
        select(AuditEvent).where(
            AuditEvent.group_id == group.id, AuditEvent.event.in_(["group.pause", "group.resume"])
        )
    ).all()
    for student in metrics["students"]:
        own = [message for message in messages if message.author_id == student["user_id"]]
        tail = own[-rules["persistent_count"] :]
        if len(tail) == rules["persistent_count"]:
            emotions = [{unit.emotion for unit in coded[message.id]} for message in tail]
            evidence_ids = [message.id for message in tail]
            if all("E2" in labels for labels in emotions) and not has_progress:
                candidates.append(
                    {
                        "rule": "persistent-confusion",
                        "priority": 2,
                        "message_ids": evidence_ids,
                        "target_user_id": student["user_id"],
                        "reason": "连续困惑表达，当前窗口未见充分论证或整合",
                    }
                )
            if all("E3" in labels for labels in emotions):
                effective_own = [m for m in own if any(unit.task_relevant for unit in coded[m.id])]
                window_start = metrics["window_start"]
                active_midpoint = active_seconds(window_start, metrics["window_end"], pause_events) / 2

                def is_earlier(when):
                    return active_seconds(window_start, when, pause_events) < active_midpoint

                gaps = [
                    (b.created_at, active_seconds(a.created_at, b.created_at, pause_events))
                    for a, b in zip(effective_own, effective_own[1:])
                ]
                earlier_gaps = [gap for ended, gap in gaps if is_earlier(ended)]
                later_gaps = [gap for ended, gap in gaps if not is_earlier(ended)]
                interval_increased = bool(earlier_gaps and later_gaps and max(later_gaps) > max(earlier_gaps))
                previous = [message for message in effective_own if is_earlier(message.created_at)]
                current = [message for message in effective_own if not is_earlier(message.created_at)]
                if (
                    previous
                    and len(current) < len(previous)
                    and interval_increased
                    and (student["silence_seconds"] or 0) >= 30
                ):
                    candidates.append(
                        {
                            "rule": "persistent-negative",
                            "priority": 1,
                            "message_ids": evidence_ids,
                            "target_user_id": student["user_id"],
                            "reason": "连续外显挫败，同时有效发言减少、历史间隔增大并持续沉默",
                        }
                    )
    phase = db.get(Phase, group.phase_id)
    participation_age = metrics["window_end"] - phase.started_at
    quiet = [
        student
        for student in metrics["students"]
        if student["silence_seconds"] is not None and student["silence_seconds"] >= rules["silence_seconds"]
    ]
    if participation_age >= rules["silence_seconds"] and quiet and metrics["NS"] >= rules["min_messages"]:
        candidates.append(
            {
                "rule": "low-participation",
                "priority": 3,
                "message_ids": [message.id for message in recent],
                "target_user_id": quiet[0]["user_id"],
                "reason": "部分成员持续缺少有效任务参与",
            }
        )
    if metrics["NS"] >= rules["min_messages"] * 2 and metrics["member_count"] >= 3:
        maximum = max((student["NS"] for student in metrics["students"]), default=0)
        if maximum / metrics["NS"] >= 0.7 and metrics["NA"] < metrics["member_count"]:
            candidates.append(
                {
                    "rule": "unbalanced-interaction",
                    "priority": 4,
                    "message_ids": [message.id for message in recent],
                    "target_user_id": None,
                    "reason": "发言持续集中于少数成员，部分成员尚未参与",
                }
            )
    if len(recent) >= rules["min_messages"] and all(
        coded[m.id] and all(not unit.task_relevant for unit in coded[m.id]) for m in recent
    ):
        candidates.append(
            {
                "rule": "off-topic",
                "priority": 5,
                "message_ids": [message.id for message in recent],
                "target_user_id": None,
                "reason": "连续多条消息与当前任务无关",
            }
        )
    return sorted(candidates, key=lambda candidate: candidate["priority"])
