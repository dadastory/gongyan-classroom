import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

Cognitive = Literal["C0", "C1", "C2", "C3", "C4", "C5"]
Emotion = Literal["E0", "E1", "E2", "E3"]
Metacognitive = Literal["M1", "M2", "M3"]
Social = Literal["SS1", "SS2", "SS3", "SS4", "SS5"]


class RegisterInput(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.@-]+$")
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["teacher", "student"] = "student"
    invite_code: str = ""


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)


class StageConfig(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    minutes: int = Field(default=10, ge=1, le=180)


DEFAULT_BINDINGS = {
    "persistent-confusion": "cognitive-clarification",
    "persistent-negative": "emotional-support",
    "low-participation": "participation-invitation",
    "unbalanced-interaction": "collaboration-coordination",
    "off-topic": "task-refocus",
}


class RuleSettings(BaseModel):
    enabled: bool = False
    mode: Literal["automatic", "approval", "notify"] = "approval"
    window_seconds: int = Field(default=180, ge=30, le=1800)
    cooldown_seconds: int = Field(default=180, ge=30, le=1800)
    persistent_count: int = Field(default=3, ge=2, le=10)
    silence_seconds: int = Field(default=120, ge=30, le=1800)
    min_messages: int = Field(default=4, ge=2, le=30)
    bindings: dict[str, str] = Field(default_factory=lambda: dict(DEFAULT_BINDINGS))

    @field_validator("bindings")
    @classmethod
    def validate_bindings(cls, value):
        if set(value) != set(DEFAULT_BINDINGS):
            raise ValueError("必须为全部五种状态配置 skill")
        if any(not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) for slug in value.values()):
            raise ValueError("skill 名称必须为小写字母、数字与连字符")
        return value


class TopicSettings(BaseModel):
    grouping_mode: Literal["manual", "random", "self"] = "random"
    group_size: int = Field(default=6, ge=2, le=15)
    stages: list[StageConfig] = Field(
        default_factory=lambda: [
            StageConfig(name="观点表达", minutes=8),
            StageConfig(name="问题探索", minutes=10),
            StageConfig(name="论证协商", minutes=12),
            StageConfig(name="共同总结", minutes=8),
        ],
        min_length=1,
        max_length=10,
    )
    rules: RuleSettings = Field(default_factory=RuleSettings)


class TopicInput(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=5, max_length=20000)
    references: str = Field(default="", max_length=20000)
    join_open: bool = True
    settings: TopicSettings = Field(default_factory=TopicSettings)


class JoinInput(BaseModel):
    code: str = Field(min_length=4, max_length=10)


class GroupInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    direction: str = Field(default="", max_length=1000)
    capacity: int = Field(default=6, ge=2, le=15)
    member_ids: list[str] = Field(default_factory=list, max_length=15)


class GroupPlan(BaseModel):
    enrollment_ids: list[str]
    groups: list[GroupInput] = Field(min_length=1, max_length=30)


class GroupControl(BaseModel):
    action: Literal["start", "pause", "resume", "advance", "complete"]
    expected_version: int | None = None


class MessageInput(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    client_id: str = Field(min_length=8, max_length=80)
    reply_to: str | None = None

    @field_validator("content")
    @classmethod
    def trim_content(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("消息不能为空")
        return value


class OutcomeInput(BaseModel):
    content: str = Field(min_length=5, max_length=10000)


class UnitCoding(BaseModel):
    start: int = Field(ge=0, description="原始消息中的 Python 字符索引，包含此位置")
    end: int = Field(ge=1, description="原始消息中不包含的结束字符索引")
    quote: str = Field(min_length=1)
    cognitive: Cognitive
    emotion: Emotion
    task_relevant: bool
    metacognitive: list[Metacognitive] = Field(default_factory=list)
    social: list[Social] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=1000)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def valid_span(self):
        if self.end <= self.start:
            raise ValueError("意义单元结束位置必须大于起始位置")
        return self


class MessageCoding(BaseModel):
    message_id: str
    units: list[UnitCoding] = Field(min_length=1, max_length=30)


class AnalysisOutput(BaseModel):
    messages: list[MessageCoding] = Field(min_length=1, max_length=20)


class InterventionOutput(BaseModel):
    content: str = Field(min_length=5, max_length=2000)
    rationale: str = Field(min_length=1, max_length=1000)


class ProviderInput(BaseModel):
    base_url: str = Field(min_length=8, max_length=500)
    api_key: str = Field(default="", max_length=2000, repr=False)
    timeout_seconds: int = Field(default=60, ge=10, le=180)

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme not in ("https", "http") or not parsed.hostname:
            raise ValueError("请输入 http 或 https 模型 API 地址")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("API 地址不能包含用户密码、查询参数或片段")
        value = value.rstrip("/")
        if parsed.hostname == "ark.cn-beijing.volces.com" and parsed.path.rstrip("/") == "/api/coding":
            return value + "/v3"
        return value


class ConnectionInput(ProviderInput):
    model: str = Field(min_length=1, max_length=120)
    output_mode: Literal["json", "structured"] = "json"
    enabled: bool = True


class SkillInput(BaseModel):
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=80)
    markdown: str = Field(min_length=20, max_length=30000)
