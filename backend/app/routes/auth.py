import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import AuthSession, User
from ..realtime import hub
from ..schemas import LoginInput, RegisterInput
from ..security import COOKIE, PASSWORDS, check_login_rate, current_user, public_user, set_session, token_hash
from ..skills import ensure_skills

router = APIRouter(prefix="/auth", tags=["authentication"])
_DUMMY_HASH = PASSWORDS.hash("invalid-login-placeholder")


@router.get("/me")
def me(user: User = Depends(current_user)):
    return public_user(user)


@router.post("/register", status_code=201)
def register(body: RegisterInput, response: Response, request: Request, db: Session = Depends(get_db)):
    check_login_rate(f"register-host:{request.client.host}", limit=120)
    check_login_rate(f"register-account:{request.client.host}:{body.username.lower()}")
    if body.role == "teacher":
        invite = settings().teacher_invite_code
        if not invite or not secrets.compare_digest(body.invite_code, invite):
            raise HTTPException(403, "老师注册需要有效邀请码，请联系平台管理者")
    user = User(
        username=body.username.lower(),
        name=body.name.strip(),
        role=body.role,
        password_hash=PASSWORDS.hash(body.password),
    )
    if not user.name:
        raise HTTPException(422, "姓名不能为空")
    try:
        db.add(user)
        db.flush()
        if user.role == "teacher":
            ensure_skills(db, user.id)
        set_session(db, response, user)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "该账号已被使用") from None
    return public_user(user)


@router.post("/login")
def login(body: LoginInput, response: Response, request: Request, db: Session = Depends(get_db)):
    check_login_rate(f"login-host:{request.client.host}", limit=300)
    check_login_rate(f"login-account:{request.client.host}:{body.username.lower()}")
    user = db.scalar(select(User).where(User.username == body.username.lower()))
    correct = PASSWORDS.verify(body.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not correct:
        raise HTTPException(401, "账号或密码不正确")
    set_session(db, response, user)
    db.commit()
    return public_user(user)


@router.post("/logout")
async def logout(
    request: Request, response: Response, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    token = request.cookies.get(COOKIE)
    db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(token)))
    db.commit()
    response.delete_cookie(COOKIE, path="/")
    await hub.revoke_user(user.id)
    return {"ok": True}
