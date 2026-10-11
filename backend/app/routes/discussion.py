import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal, get_db, lock_topic
from ..models import AuditEvent, Group, Message, Outcome, User
from ..realtime import hub
from ..schemas import GroupControl, MessageInput, OutcomeInput
from ..security import COOKIE, current_user, require_group, require_topic, teacher, user_from_token
from ..state_machine import transition
from ..views import group_detail, message_dict, message_list, topic_detail
from ..worker import enqueue_analysis

router = APIRouter(tags=["discussion"])


@router.get("/groups/{group_id}")
def get_group(group_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    group, topic = require_group(db, group_id, user)
    return group_detail(db, group, topic, user)


@router.post("/groups/{group_id}/control")
async def control_group(
    group_id: str, body: GroupControl, user: User = Depends(teacher), db: Session = Depends(get_db)
):
    group, topic = require_group(db, group_id, user, manage=True)
    topic = lock_topic(db, topic.id)
    db.refresh(group)
    transition(db, group, topic, body.action, user.id, body.expected_version)
    db.commit()
    await hub.broadcast(topic.id, {"type": "state"})
    return group_detail(db, group, topic, user)


@router.post("/topics/{topic_id}/control")
async def control_topic(
    topic_id: str, body: GroupControl, user: User = Depends(teacher), db: Session = Depends(get_db)
):
    require_topic(db, topic_id, user, manage=True)
    topic = lock_topic(db, topic_id)
    groups = db.scalars(select(Group).where(Group.topic_id == topic.id).order_by(Group.created_at)).all()
    if not groups:
        raise HTTPException(409, "请先完成分组")
    eligible = {
        "start": ["waiting"],
        "pause": ["active"],
        "resume": ["paused"],
        "advance": ["active"],
        "complete": ["active", "paused"],
    }[body.action]
    changed = 0
    for group in groups:
        if group.state in eligible:
            transition(db, group, topic, body.action, user.id)
            changed += 1
    if not changed:
        raise HTTPException(409, "没有处于可操作状态的小组")
    db.commit()
    await hub.broadcast(topic.id, {"type": "state"})
    return topic_detail(db, topic, user)


@router.get("/groups/{group_id}/messages")
def history(
    group_id: str,
    before: float | None = None,
    before_id: str | None = Query(None, min_length=1, max_length=80),
    after_id: str | None = Query(None, min_length=1, max_length=80),
    limit: int = Query(100, ge=1, le=200),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    require_group(db, group_id, user)
    if sum(value is not None for value in (before, before_id, after_id)) > 1:
        raise HTTPException(422, "请只指定一个消息分页游标")
    query = select(Message).where(Message.group_id == group_id)
    if before_id or after_id:
        cursor = db.get(Message, before_id or after_id)
        if not cursor or cursor.group_id != group_id:
            raise HTTPException(404, "消息分页游标不存在")
        query = query.where(
            or_(
                Message.created_at > cursor.created_at,
                and_(Message.created_at == cursor.created_at, Message.id > cursor.id),
            )
            if after_id
            else or_(
                Message.created_at < cursor.created_at,
                and_(Message.created_at == cursor.created_at, Message.id < cursor.id),
            )
        )
    if before is not None:
        query = query.where(Message.created_at < before)
    order = (Message.created_at, Message.id) if after_id else (Message.created_at.desc(), Message.id.desc())
    messages = db.scalars(query.order_by(*order).limit(limit)).all()
    return message_list(
        db, messages if after_id else list(reversed(messages)), include_analysis=user.role == "teacher"
    )


@router.post("/groups/{group_id}/messages", status_code=201)
async def post_message(
    group_id: str, body: MessageInput, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    group, topic = require_group(db, group_id, user)
    topic = lock_topic(db, topic.id)
    db.refresh(group)
    previous = db.scalar(
        select(Message).where(
            Message.group_id == group.id, Message.author_id == user.id, Message.client_id == body.client_id
        )
    )
    if previous:
        return message_dict(db, previous, include_analysis=user.role == "teacher")
    if user.role == "student" and group.state != "active":
        raise HTTPException(409, "讨论尚未开始、已暂停或已结束，请等待老师安排")
    if group.state == "completed":
        raise HTTPException(409, "讨论已结束")
    recent = db.scalar(
        select(func.count())
        .select_from(Message)
        .where(
            Message.group_id == group.id, Message.author_id == user.id, Message.created_at > time.time() - 10
        )
    )
    if recent >= 10:
        raise HTTPException(429, "发送较频繁，请稍后再试")
    if body.reply_to:
        target = db.get(Message, body.reply_to)
        if not target or target.group_id != group.id:
            raise HTTPException(422, "回复对象必须是本组消息")
    message = Message(
        group_id=group.id,
        author_id=user.id,
        phase_id=group.phase_id,
        kind=user.role,
        content=body.content,
        client_id=body.client_id,
        reply_to=body.reply_to,
        analysis_status="pending" if user.role == "student" else "not-applicable",
    )
    db.add(message)
    try:
        db.flush()
        if user.role == "student":
            enqueue_analysis(db, message)
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = db.scalar(
            select(Message).where(
                Message.group_id == group.id,
                Message.author_id == user.id,
                Message.client_id == body.client_id,
            )
        )
        if not previous:
            raise
        message = previous
    await hub.broadcast(topic.id, {"type": "message"})
    return message_dict(db, message, include_analysis=user.role == "teacher")


@router.post("/groups/{group_id}/outcomes", status_code=201)
async def submit_outcome(
    group_id: str, body: OutcomeInput, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    group, topic = require_group(db, group_id, user)
    lock_topic(db, topic.id)
    db.refresh(group)
    if group.state != "active" or not group.phase_id:
        raise HTTPException(409, "请在正在讨论的阶段提交成果")
    outcome = Outcome(group_id=group.id, phase_id=group.phase_id, author_id=user.id, content=body.content)
    db.add(outcome)
    db.flush()
    db.add(
        AuditEvent(
            topic_id=topic.id,
            group_id=group.id,
            actor_id=user.id,
            event="outcome.submitted",
            data={"outcome_id": outcome.id, "phase_id": group.phase_id},
        )
    )
    db.commit()
    await hub.broadcast(topic.id, {"type": "outcome"})
    return {"id": outcome.id, "content": outcome.content, "created_at": outcome.created_at}


@router.websocket("/ws/topics/{topic_id}")
async def topic_socket(socket: WebSocket, topic_id: str):
    origin = socket.headers.get("origin")
    if origin and origin.rstrip("/") not in settings().origins:
        await socket.close(code=4403)
        return
    token = socket.cookies.get(COOKIE)
    with SessionLocal() as db:
        user = user_from_token(db, token)
        if not user:
            await socket.close(code=4401)
            return
        try:
            require_topic(db, topic_id, user)
        except HTTPException:
            await socket.close(code=4403)
            return
        user_id = user.id
    await hub.connect(topic_id, user_id, socket)
    try:
        while True:
            try:
                payload = await asyncio.wait_for(socket.receive_text(), timeout=25)
            except TimeoutError:
                payload = "ping"
            with SessionLocal() as db:
                user = user_from_token(db, token)
                if not user:
                    await socket.close(code=4401)
                    break
                require_topic(db, topic_id, user)
            if payload == "ping":
                await socket.send_json({"type": "pong"})
    except (WebSocketDisconnect, HTTPException, RuntimeError):
        pass
    finally:
        await hub.disconnect(topic_id, socket)
