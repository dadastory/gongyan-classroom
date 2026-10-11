import math
import random
import secrets
import string

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..db import get_db, lock_topic
from ..models import AuditEvent, Enrollment, Group, Intervention, Topic, User
from ..realtime import hub
from ..schemas import GroupInput, GroupPlan, JoinInput, TopicInput
from ..security import current_user, require_topic, teacher
from ..skills import latest_skills
from ..views import group_summary, topic_detail, topic_summary

router = APIRouter(prefix="/topics", tags=["topics"])


def ensure_preparing(topic: Topic):
    if topic.status != "preparing":
        raise HTTPException(409, "分组在讨论开始前完成；当前课题已经开始或结束")


def check_bindings(db: Session, teacher_id: str, body: TopicInput):
    available = latest_skills(db, teacher_id)
    if any(slug not in available for slug in body.settings.rules.bindings.values()):
        raise HTTPException(422, "规则绑定了不存在的 skill")


@router.get("")
def list_topics(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Topic)
    if user.role == "teacher":
        query = query.where(Topic.teacher_id == user.id)
    else:
        query = query.join(Enrollment, Enrollment.topic_id == Topic.id).where(Enrollment.user_id == user.id)
    topics = db.scalars(query.order_by(Topic.created_at.desc()).limit(200)).all()
    items = [topic_summary(db, topic) for topic in topics]
    if user.role == "student":
        for item in items:
            item["settings"] = {key: value for key, value in item["settings"].items() if key != "rules"}
    return items


@router.post("", status_code=201)
def create_topic(body: TopicInput, user: User = Depends(teacher), db: Session = Depends(get_db)):
    check_bindings(db, user.id, body)
    topic = Topic(
        teacher_id=user.id,
        title=body.title,
        description=body.description,
        references=body.references,
        join_open=body.join_open,
        settings=body.settings.model_dump(),
        join_code="".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6)),
    )
    db.add(topic)
    db.flush()
    db.add(AuditEvent(topic_id=topic.id, actor_id=user.id, event="topic.created", data=body.model_dump()))
    db.commit()
    return topic_summary(db, topic)


@router.post("/join")
async def join_topic(body: JoinInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "student":
        raise HTTPException(403, "请使用学生账号加入课题")
    topic = db.scalar(select(Topic).where(Topic.join_code == body.code.strip().upper()))
    if not topic:
        raise HTTPException(404, "课题码不正确")
    topic = lock_topic(db, topic.id)
    enrollment = db.scalar(
        select(Enrollment).where(Enrollment.topic_id == topic.id, Enrollment.user_id == user.id)
    )
    if not enrollment:
        if not topic.join_open or topic.status != "preparing":
            raise HTTPException(409, "课题当前未开放加入")
        count = db.scalar(select(func.count()).select_from(Enrollment).where(Enrollment.topic_id == topic.id))
        if count >= 120:
            raise HTTPException(409, "课题人数已达上限")
        db.add(Enrollment(topic_id=topic.id, user_id=user.id))
        db.add(
            AuditEvent(topic_id=topic.id, actor_id=user.id, event="student.joined", data={"user_id": user.id})
        )
        db.commit()
        await hub.broadcast(topic.id, {"type": "membership"})
    return topic_summary(db, topic)


@router.get("/{topic_id}")
def get_topic(topic_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return topic_detail(db, require_topic(db, topic_id, user), user)


@router.put("/{topic_id}")
async def update_topic(
    topic_id: str, body: TopicInput, user: User = Depends(teacher), db: Session = Depends(get_db)
):
    require_topic(db, topic_id, user, manage=True)
    topic = lock_topic(db, topic_id)
    check_bindings(db, user.id, body)
    if topic.status != "preparing":
        for key in ("grouping_mode", "group_size", "stages"):
            if topic.settings[key] != body.settings.model_dump()[key]:
                raise HTTPException(409, "讨论开始后不能更改分组方式或阶段定义")
        if body.join_open:
            raise HTTPException(409, "讨论开始后加入入口已关闭")
    topic.title, topic.description, topic.references = body.title, body.description, body.references
    topic.join_open, topic.settings = body.join_open, body.settings.model_dump()
    topic.config_version += 1
    owned_groups = list(db.scalars(select(Group.id).where(Group.topic_id == topic.id)))
    for intervention in db.scalars(
        select(Intervention).where(
            Intervention.group_id.in_(owned_groups),
            Intervention.status.in_(["generating", "pending", "notify"]),
        )
    ):
        intervention.status = "stale"
        db.get(Group, intervention.group_id).intervention_state = "monitoring"
    db.add(
        AuditEvent(
            topic_id=topic.id,
            actor_id=user.id,
            event="topic.updated",
            data={"config_version": topic.config_version, "settings_snapshot": body.model_dump()},
        )
    )
    db.commit()
    await hub.broadcast(topic.id, {"type": "topic"})
    return topic_detail(db, topic, user)


@router.post("/{topic_id}/groups", status_code=201)
async def create_group(
    topic_id: str, body: GroupInput, user: User = Depends(teacher), db: Session = Depends(get_db)
):
    require_topic(db, topic_id, user, manage=True)
    topic = lock_topic(db, topic_id)
    ensure_preparing(topic)
    if topic.settings["grouping_mode"] not in ("manual", "self"):
        raise HTTPException(409, "随机分组课题请使用随机预览并应用")
    enrollments = db.scalars(
        select(Enrollment).where(Enrollment.topic_id == topic.id, Enrollment.user_id.in_(body.member_ids))
    ).all()
    if len(set(body.member_ids)) != len(body.member_ids) or len(enrollments) != len(body.member_ids):
        raise HTTPException(422, "成员必须属于当前课题且不能重复")
    if len(body.member_ids) > body.capacity:
        raise HTTPException(409, "成员数量超过小组容量")
    group = Group(topic_id=topic.id, name=body.name, direction=body.direction, capacity=body.capacity)
    db.add(group)
    db.flush()
    for enrollment in enrollments:
        enrollment.group_id = group.id
    db.add(
        AuditEvent(
            topic_id=topic.id,
            group_id=group.id,
            actor_id=user.id,
            event="group.created",
            data={"member_ids": body.member_ids, "mode": topic.settings["grouping_mode"]},
        )
    )
    db.commit()
    await hub.broadcast(topic.id, {"type": "membership"})
    return group_summary(db, group, True)


@router.put("/{topic_id}/groups/{group_id}")
async def edit_group(
    topic_id: str,
    group_id: str,
    body: GroupInput,
    user: User = Depends(teacher),
    db: Session = Depends(get_db),
):
    require_topic(db, topic_id, user, manage=True)
    topic = lock_topic(db, topic_id)
    ensure_preparing(topic)
    group = db.get(Group, group_id)
    if not group or group.topic_id != topic.id:
        raise HTTPException(404, "小组不存在")
    if len(set(body.member_ids)) != len(body.member_ids) or len(body.member_ids) > body.capacity:
        raise HTTPException(422, "成员重复或超过容量")
    enrollments = db.scalars(select(Enrollment).where(Enrollment.topic_id == topic.id)).all()
    available = {e.user_id: e for e in enrollments}
    if not set(body.member_ids) <= available.keys():
        raise HTTPException(422, "成员必须属于当前课题")
    for enrollment in enrollments:
        if enrollment.group_id == group.id:
            enrollment.group_id = None
    for member_id in body.member_ids:
        available[member_id].group_id = group.id
    group.name, group.direction, group.capacity = body.name, body.direction, body.capacity
    db.add(
        AuditEvent(
            topic_id=topic.id,
            group_id=group.id,
            actor_id=user.id,
            event="group.assigned",
            data={"member_ids": body.member_ids},
        )
    )
    db.commit()
    await hub.broadcast(topic.id, {"type": "membership"})
    return group_summary(db, group, True)


@router.delete("/{topic_id}/groups/{group_id}")
async def delete_group(
    topic_id: str, group_id: str, user: User = Depends(teacher), db: Session = Depends(get_db)
):
    require_topic(db, topic_id, user, manage=True)
    topic = lock_topic(db, topic_id)
    ensure_preparing(topic)
    group = db.get(Group, group_id)
    if not group or group.topic_id != topic.id:
        raise HTTPException(404, "小组不存在")
    members = db.scalars(select(Enrollment).where(Enrollment.group_id == group_id)).all()
    ids = [member.user_id for member in members]
    for member in members:
        member.group_id = None
    db.flush()
    db.add(
        AuditEvent(
            topic_id=topic.id,
            actor_id=user.id,
            event="group.removed",
            data={"group_id": group.id, "name": group.name, "member_ids": ids},
        )
    )
    db.delete(group)
    db.commit()
    await hub.broadcast(topic.id, {"type": "membership"})
    return {"ok": True}


@router.post("/{topic_id}/random-preview")
def random_preview(topic_id: str, user: User = Depends(teacher), db: Session = Depends(get_db)):
    topic = require_topic(db, topic_id, user, manage=True)
    ensure_preparing(topic)
    if topic.settings["grouping_mode"] != "random":
        raise HTTPException(409, "当前课题没有启用随机分组")
    members = list(db.scalars(select(Enrollment.user_id).where(Enrollment.topic_id == topic.id)).all())
    if not members:
        raise HTTPException(409, "请等待学生加入后再分组")
    enrollment_ids = sorted(members)
    random.SystemRandom().shuffle(members)
    size = topic.settings["group_size"]
    count = math.ceil(len(members) / size)
    groups = [
        {"name": f"第 {index + 1} 组", "capacity": size, "direction": "", "member_ids": members[index::count]}
        for index in range(count)
    ]
    return {"enrollment_ids": enrollment_ids, "groups": groups}


@router.post("/{topic_id}/random-apply")
async def random_apply(
    topic_id: str, body: GroupPlan, user: User = Depends(teacher), db: Session = Depends(get_db)
):
    require_topic(db, topic_id, user, manage=True)
    topic = lock_topic(db, topic_id)
    ensure_preparing(topic)
    if topic.settings["grouping_mode"] != "random":
        raise HTTPException(409, "当前课题没有启用随机分组")
    enrollments = db.scalars(select(Enrollment).where(Enrollment.topic_id == topic.id)).all()
    current = {e.user_id for e in enrollments}
    if current != set(body.enrollment_ids) or len(body.enrollment_ids) != len(current):
        raise HTTPException(409, "学生名单已经变化，请重新预览")
    flattened = [member for group in body.groups for member in group.member_ids]
    sizes = [len(group.member_ids) for group in body.groups]
    if len(flattened) != len(set(flattened)) or set(flattened) != current:
        raise HTTPException(422, "随机方案必须包含每名学生且不能重复")
    if any(not group.member_ids or len(group.member_ids) > group.capacity for group in body.groups):
        raise HTTPException(422, "分组为空或超过容量")
    if max(sizes) - min(sizes) > 1:
        raise HTTPException(422, "随机分组的人数需要均衡")
    for enrollment in enrollments:
        enrollment.group_id = None
    db.flush()
    db.execute(delete(Group).where(Group.topic_id == topic.id))
    by_user = {e.user_id: e for e in enrollments}
    for item in body.groups:
        group = Group(topic_id=topic.id, name=item.name, capacity=item.capacity, direction=item.direction)
        db.add(group)
        db.flush()
        for member in item.member_ids:
            by_user[member].group_id = group.id
    db.add(AuditEvent(topic_id=topic.id, actor_id=user.id, event="groups.randomized", data=body.model_dump()))
    db.commit()
    await hub.broadcast(topic.id, {"type": "membership"})
    return topic_detail(db, topic, user)


@router.post("/{topic_id}/groups/{group_id}/join")
async def self_join(
    topic_id: str, group_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    require_topic(db, topic_id, user)
    if user.role != "student":
        raise HTTPException(403, "请使用学生账号选择小组")
    topic = lock_topic(db, topic_id)
    ensure_preparing(topic)
    if topic.settings["grouping_mode"] != "self":
        raise HTTPException(409, "当前课题由老师分配小组")
    group = db.get(Group, group_id)
    if not group or group.topic_id != topic.id:
        raise HTTPException(404, "小组不存在")
    enrollment = db.scalar(
        select(Enrollment).where(Enrollment.topic_id == topic.id, Enrollment.user_id == user.id)
    )
    if enrollment.group_id == group.id:
        return {"group_id": group.id}
    count = db.scalar(select(func.count()).select_from(Enrollment).where(Enrollment.group_id == group.id))
    if count >= group.capacity:
        raise HTTPException(409, "这个小组已满，请选择其他小组")
    enrollment.group_id = group.id
    db.add(
        AuditEvent(
            topic_id=topic.id,
            group_id=group.id,
            actor_id=user.id,
            event="group.self-joined",
            data={"user_id": user.id},
        )
    )
    db.commit()
    await hub.broadcast(topic.id, {"type": "membership"})
    return {"group_id": group.id}
