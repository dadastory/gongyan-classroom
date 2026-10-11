import hashlib
import secrets
import time
from collections import defaultdict, deque
from threading import Lock

from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request, Response
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import AuthSession, Enrollment, Group, Topic, User

PASSWORDS = PasswordHash.recommended()
COOKIE = "classroom_session"
_login_attempts: dict[str, deque] = defaultdict(deque)
_rate_lock = Lock()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def cipher() -> Fernet:
    return Fernet(settings().encryption_key.encode())


def encrypt(value: str) -> str:
    return cipher().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return cipher().decrypt(value.encode()).decode()


def user_from_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == token_hash(token), AuthSession.expires_at > time.time()
        )
    )
    return db.get(User, session.user_id) if session else None


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = user_from_token(db, request.cookies.get(COOKIE))
    if not user:
        raise HTTPException(401, "请先登录")
    return user


def teacher(user: User = Depends(current_user)) -> User:
    if user.role != "teacher":
        raise HTTPException(403, "此操作需要老师身份")
    return user


def public_user(user: User) -> dict:
    return {"id": user.id, "name": user.name, "username": user.username, "role": user.role}


def set_session(db: Session, response: Response, user: User):
    token = secrets.token_urlsafe(32)
    seconds = settings().session_hours * 3600
    db.add(AuthSession(token_hash=token_hash(token), user_id=user.id, expires_at=time.time() + seconds))
    response.set_cookie(
        COOKIE,
        token,
        max_age=seconds,
        httponly=True,
        secure=settings().cookie_secure,
        samesite="strict",
        path="/",
    )


def check_login_rate(key: str, limit: int = 10):
    now = time.time()
    with _rate_lock:
        attempts = _login_attempts[key]
        while attempts and attempts[0] < now - 60:
            attempts.popleft()
        if len(attempts) >= limit:
            raise HTTPException(429, "尝试次数较多，请一分钟后重试")
        attempts.append(now)
        if len(_login_attempts) > 2000:
            stale = [key for key, value in _login_attempts.items() if not value or value[-1] < now - 60]
            for item in stale:
                _login_attempts.pop(item, None)


def require_topic(db: Session, topic_id: str, user: User, *, manage: bool = False) -> Topic:
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(404, "课题不存在")
    if user.role == "teacher" and topic.teacher_id == user.id:
        return topic
    if not manage and user.role == "student":
        enrolled = db.scalar(
            select(Enrollment).where(Enrollment.topic_id == topic.id, Enrollment.user_id == user.id)
        )
        if enrolled:
            return topic
    raise HTTPException(403, "你没有访问此课题的权限")


def require_group(db: Session, group_id: str, user: User, *, manage: bool = False) -> tuple[Group, Topic]:
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(404, "小组不存在")
    topic = require_topic(db, group.topic_id, user, manage=manage)
    if user.role == "student":
        enrollment = db.scalar(
            select(Enrollment).where(Enrollment.topic_id == topic.id, Enrollment.user_id == user.id)
        )
        if enrollment.group_id != group.id:
            raise HTTPException(403, "只能访问自己所在小组")
    return group, topic
