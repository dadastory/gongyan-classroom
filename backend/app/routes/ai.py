import hashlib
import time
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent_runtime import run_agent, validate_analysis
from ..db import get_db, lock_topic
from ..models import (
    AnalysisJob,
    AuditEvent,
    Group,
    Intervention,
    MeaningUnit,
    Message,
    ModelConnection,
    SkillVersion,
    Topic,
    User,
)
from ..realtime import hub
from ..schemas import AnalysisOutput, ConnectionInput, MessageCoding, ProviderInput, SkillInput, UnitCoding
from ..security import decrypt, encrypt, require_group, teacher
from ..skills import ensure_skills, latest_skills, parse_skill, skill_dict
from ..views import intervention_dict, unit_dict
from ..worker import publish_intervention, schedule_intervention

router = APIRouter(tags=["agents"])


def connection_key(body: ProviderInput, previous: ModelConnection | None) -> str:
    if body.api_key:
        return encrypt(body.api_key)
    if previous and previous.encrypted_key:
        original = ProviderInput(base_url=previous.base_url).base_url
        if original != body.base_url:
            raise HTTPException(422, "API 地址已更改，请重新填写密钥；已保存密钥仅用于原服务地址")
        return previous.encrypted_key
    raise HTTPException(422, "请输入 API 密钥；无鉴权的本地模型可填 local-model")


def provider_error(error: Exception, operation: str) -> HTTPException:
    if isinstance(error, APITimeoutError):
        return HTTPException(504, f"{operation}超时，请检查网络或增加请求超时后重试")
    if isinstance(error, APIConnectionError):
        return HTTPException(502, f"{operation}失败，无法连接模型服务，请检查地址和网络")
    if isinstance(error, APIStatusError):
        status = error.status_code
        if status in (401, 403):
            return HTTPException(502, f"{operation}失败，模型服务拒绝访问，请检查密钥及模型权限")
        if status in (404, 405):
            return HTTPException(502, f"{operation}失败，请检查 API 地址；服务可能不支持此接口，可手动填写模型")
        if status == 429:
            return HTTPException(502, f"{operation}失败，模型服务暂时限流，请稍后重试")
        return HTTPException(502, f"{operation}失败（服务状态 {status}），请检查配置或稍后重试")
    return HTTPException(502, f"{operation}失败（{type(error).__name__}），请检查地址、密钥、模型及输出模式")


@router.post("/ai/models")
async def list_models(body: ProviderInput, user: User = Depends(teacher), db: Session = Depends(get_db)):
    previous = db.scalar(select(ModelConnection).where(ModelConnection.teacher_id == user.id))
    key = connection_key(body, previous)
    try:
        async with AsyncOpenAI(api_key=decrypt(key), base_url=body.base_url,
                             timeout=body.timeout_seconds, max_retries=0,
                             http_client=httpx.AsyncClient(follow_redirects=False)) as client:
            page = await client.models.list()
            models = sorted({model.id for model in page.data if isinstance(model.id, str) and model.id.strip()})
        if not models:
            raise HTTPException(502, "服务未返回模型目录，可手动填写模型 ID 或稍后重试")
    except HTTPException:
        raise
    except Exception as error:
        raise provider_error(error, "获取模型") from None
    coding_plan = body.base_url == "https://ark.cn-beijing.volces.com/api/coding/v3"
    message = f"已获取 {len(models)} 个模型 ID；是否可调用请通过连接测试确认。"
    if coding_plan:
        message += "火山 Coding Plan 可手动填写套餐别名，例如 ark-code-latest。"
    return {"models": models, "base_url": body.base_url, "message": message,
            "recommended_model": "ark-code-latest" if coding_plan else None}


def sanitized_connection(connection: ModelConnection | None) -> dict:
    if not connection:
        return {
            "base_url": "",
            "model": "",
            "has_key": False,
            "output_mode": "json",
            "timeout_seconds": 60,
            "enabled": False,
            "version": 0,
            "framework": "Agno",
        }
    return {
        "base_url": connection.base_url,
        "model": connection.model,
        "has_key": bool(connection.encrypted_key),
        "output_mode": connection.output_mode,
        "timeout_seconds": connection.timeout_seconds,
        "enabled": connection.enabled,
        "version": connection.version,
        "framework": "Agno",
    }


@router.get("/ai/connection")
def get_connection(user: User = Depends(teacher), db: Session = Depends(get_db)):
    connection = db.scalar(select(ModelConnection).where(ModelConnection.teacher_id == user.id))
    return sanitized_connection(connection)


@router.put("/ai/connection")
async def save_connection(
    body: ConnectionInput, user: User = Depends(teacher), db: Session = Depends(get_db)
):
    connection = db.scalar(
        select(ModelConnection).where(ModelConnection.teacher_id == user.id).with_for_update()
    )
    if connection and not body.api_key:
        connection_key(body, connection)
    if body.enabled and not body.api_key and not (connection and connection.encrypted_key):
        raise HTTPException(422, "请填写 API Key；无鉴权的本地模型可填 local-model")
    if connection is None:
        connection = ModelConnection(
            teacher_id=user.id,
            base_url=body.base_url,
            model=body.model,
            encrypted_key=encrypt(body.api_key or "local-model"),
        )
        db.add(connection)
    else:
        connection.version += 1
        if body.api_key:
            connection.encrypted_key = encrypt(body.api_key)
    connection.base_url, connection.model = body.base_url, body.model
    connection.enabled, connection.output_mode = body.enabled, body.output_mode
    connection.timeout_seconds = body.timeout_seconds
    if body.enabled:
        jobs = db.scalars(
            select(AnalysisJob)
            .join(Group, Group.id == AnalysisJob.group_id)
            .join(Topic, Topic.id == Group.topic_id)
            .where(
                Topic.teacher_id == user.id, AnalysisJob.status == "blocked", AnalysisJob.kind == "analysis"
            )
        ).all()
        for job in jobs:
            job.status, job.available_at, job.error = "pending", time.time(), None
            job.attempts, job.lease_until = 0, None
            job.payload = {"message_ids": job.payload["message_ids"]}
            for message in db.scalars(select(Message).where(Message.id.in_(job.payload["message_ids"]))):
                message.analysis_status = "pending"
    db.commit()
    return sanitized_connection(connection)


class ConnectionProbe(BaseModel):
    status: Literal["ok"]
    message: str


@router.post("/ai/test-connection")
async def test_connection(
    body: ConnectionInput, user: User = Depends(teacher), db: Session = Depends(get_db)
):
    previous = db.scalar(select(ModelConnection).where(ModelConnection.teacher_id == user.id))
    key = connection_key(body, previous)
    connection = {**body.model_dump(exclude={"api_key"}), "encrypted_key": key, "version": 0}
    skill = {
        "slug": "connection-probe",
        "version": 1,
        "markdown": "---\nname: connection-probe\ndescription: 验证模型结构化调用是否正常。\n---\n"
        "返回 status=ok 和一条简短中文连接成功消息。",
    }
    started = time.monotonic()
    try:
        result = await run_agent(connection, skill, "请验证连接并返回指定 JSON。", ConnectionProbe)
    except Exception as error:
        raise provider_error(error, "连接测试") from None
    return {"ok": True, "message": result.message, "base_url": body.base_url,
            "latency_ms": round((time.monotonic() - started) * 1000)}


@router.get("/ai/skills")
def get_skills(user: User = Depends(teacher), db: Session = Depends(get_db)):
    ensure_skills(db, user.id)
    db.commit()
    return [skill_dict(skill) for skill in latest_skills(db, user.id).values()]


@router.get("/ai/skills/{slug}/versions")
def skill_versions(slug: str, user: User = Depends(teacher), db: Session = Depends(get_db)):
    return [
        skill_dict(skill)
        for skill in db.scalars(
            select(SkillVersion)
            .where(SkillVersion.teacher_id == user.id, SkillVersion.slug == slug)
            .order_by(SkillVersion.version.desc())
        )
    ]


@router.put("/ai/skills/{slug}")
def save_skill(slug: str, body: SkillInput, user: User = Depends(teacher), db: Session = Depends(get_db)):
    if body.slug != slug:
        raise HTTPException(422, "skill 名称与地址不一致")
    metadata, _ = parse_skill(body.markdown, slug)
    # Validate with the very loader used in production, rather than a parallel implementation.
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from agno.skills import LocalSkills, Skills

    try:
        with TemporaryDirectory() as temp:
            path = Path(temp) / slug
            path.mkdir()
            (path / "SKILL.md").write_text(body.markdown)
            loaded = Skills(loaders=[LocalSkills(str(path))])
            if slug not in loaded.get_skill_names():
                raise ValueError("未加载 skill")
    except Exception:
        raise HTTPException(422, "SKILL.md 未通过 Agno 标准校验，请检查 frontmatter") from None
    latest = latest_skills(db, user.id).get(slug)
    digest = hashlib.sha256(body.markdown.encode()).hexdigest()
    if latest and latest.digest == digest and latest.title == body.title:
        return skill_dict(latest)
    skill = SkillVersion(
        teacher_id=user.id,
        slug=slug,
        title=body.title,
        description=metadata["description"],
        markdown=body.markdown,
        digest=digest,
        version=latest.version + 1 if latest else 1,
    )
    db.add(skill)
    db.commit()
    return skill_dict(skill)


@router.get("/ai/skills/{slug}/download")
def download_skill(slug: str, user: User = Depends(teacher), db: Session = Depends(get_db)):
    skill = latest_skills(db, user.id).get(slug)
    if not skill:
        raise HTTPException(404, "skill 不存在")
    return Response(
        skill.markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{slug}-v{skill.version}-SKILL.md"'},
    )


@router.put("/units/{unit_id}")
async def correct_unit(
    unit_id: str, body: UnitCoding, user: User = Depends(teacher), db: Session = Depends(get_db)
):
    unit = db.get(MeaningUnit, unit_id)
    if not unit:
        raise HTTPException(404, "意义单元不存在")
    message = db.get(Message, unit.message_id)
    group, topic = require_group(db, message.group_id, user, manage=True)
    lock_topic(db, topic.id)
    db.refresh(unit)
    others = db.scalars(
        select(MeaningUnit).where(MeaningUnit.message_id == message.id, MeaningUnit.id != unit.id)
    ).all()
    updated = [body, *[UnitCoding.model_validate(unit_dict(item)) for item in others]]
    try:
        validate_analysis(
            AnalysisOutput(messages=[MessageCoding(message_id=message.id, units=updated)]),
            [{"id": message.id, "content": message.content}],
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    before = unit_dict(unit)
    for key, value in body.model_dump().items():
        setattr(unit, key, value)
    unit.corrected = True
    db.add(
        AuditEvent(
            topic_id=topic.id,
            group_id=group.id,
            actor_id=user.id,
            event="unit.corrected",
            data={"unit_id": unit.id, "before": before, "after": body.model_dump()},
        )
    )
    db.commit()
    await hub.broadcast(topic.id, {"type": "analysis"})
    return unit_dict(unit)


@router.post("/groups/{group_id}/summarize")
async def summarize(group_id: str, user: User = Depends(teacher), db: Session = Depends(get_db)):
    group, topic = require_group(db, group_id, user, manage=True)
    lock_topic(db, topic.id)
    db.refresh(group)
    if group.state != "active":
        raise HTTPException(409, "请在正在讨论的阶段请求总结")
    ids = list(
        db.scalars(
            select(Message.id).where(Message.group_id == group.id, Message.phase_id == group.phase_id)
        ).all()
    )
    if not ids:
        raise HTTPException(409, "当前阶段还没有讨论消息")
    item = schedule_intervention(
        db,
        group,
        {"rule": "summary", "message_ids": ids, "target_user_id": None, "reason": "老师请求阶段总结"},
        force=True,
    )
    db.commit()
    await hub.broadcast(topic.id, {"type": "state"})
    return intervention_dict(item)


@router.post("/interventions/{item_id}/{action}")
async def review_intervention(
    item_id: str, action: str, user: User = Depends(teacher), db: Session = Depends(get_db)
):
    item = db.get(Intervention, item_id)
    if not item:
        raise HTTPException(404, "干预记录不存在")
    group, topic = require_group(db, item.group_id, user, manage=True)
    lock_topic(db, topic.id)
    db.refresh(item)
    db.refresh(group)
    if action == "approve":
        if item.status not in ("pending", "published"):
            raise HTTPException(409, "此记录尚未生成或已不能发布")
        try:
            publish_intervention(db, item, group, topic, user.id)
        except HTTPException:
            if item.status == "stale":
                db.commit()
            raise
    elif action == "dismiss":
        if item.status not in ("pending", "notify", "generating"):
            raise HTTPException(409, "此记录已经处理")
        item.status = "dismissed"
        group.intervention_state = "monitoring"
        db.add(
            AuditEvent(
                topic_id=topic.id,
                group_id=group.id,
                actor_id=user.id,
                event="intervention.dismissed",
                data={"intervention_id": item.id},
            )
        )
    else:
        raise HTTPException(422, "无效操作")
    db.commit()
    await hub.broadcast(topic.id, {"type": "state"})
    return intervention_dict(item)


@router.post("/groups/{group_id}/retry-analysis")
async def retry_analysis(group_id: str, user: User = Depends(teacher), db: Session = Depends(get_db)):
    group, topic = require_group(db, group_id, user, manage=True)
    lock_topic(db, topic.id)
    jobs = db.scalars(
        select(AnalysisJob).where(
            AnalysisJob.group_id == group.id,
            AnalysisJob.kind == "analysis",
            AnalysisJob.status.in_(["failed", "blocked"]),
        )
    ).all()
    for job in jobs:
        job.status, job.attempts, job.error, job.available_at = "pending", 0, None, time.time()
        job.payload = {"message_ids": job.payload["message_ids"]}
        for message in db.scalars(select(Message).where(Message.id.in_(job.payload["message_ids"]))):
            message.analysis_status = "pending"
    db.commit()
    await hub.broadcast(topic.id, {"type": "analysis"})
    return {"retried": len(jobs)}
