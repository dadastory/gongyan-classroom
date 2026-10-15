"""Packaged, read-only classroom records; never queries users' classroom databases."""

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

router = APIRouter(prefix="/examples", tags=["examples"])
EXAMPLE_FILE = Path(__file__).resolve().parents[2] / "examples" / "classroom.json"


class ClassroomExample(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    title: str
    description: str
    recorded_at: float
    source_note: str
    model: str
    student_count: int
    settings: dict
    analysis_runs: list[dict]
    groups: list[dict]
    checkpoints: list[dict]
    events: list[dict]
    phases: list[dict]
    skills: list[dict]
    checks: list[dict]
    provenance: dict


class ExampleBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    cases: list[ClassroomExample]


@lru_cache
def load_examples() -> dict[str, ClassroomExample]:
    try:
        bundle = ExampleBundle.model_validate_json(EXAMPLE_FILE.read_text(encoding="utf-8"))
        result = {item.id: item for item in bundle.cases}
        if bundle.schema_version != "1.0" or len(result) != len(bundle.cases):
            raise ValueError("Invalid example manifest")
        return result
    except (OSError, ValueError, ValidationError):
        raise HTTPException(503, "课堂案例资源暂不可用，请检查安装文件是否完整") from None


def example_summary(item: ClassroomExample) -> dict:
    return {key: getattr(item, key) for key in (
        "id", "title", "description", "recorded_at", "source_note", "model", "student_count"
    )} | {
        "group_count": len(item.groups),
        "message_count": sum(len(g["messages"]) for g in item.groups),
        "unit_count": sum(len(m.get("units", [])) for g in item.groups for m in g["messages"]),
        "checkpoint_count": len(item.checkpoints),
    }


@router.get("")
def list_examples():
    return [example_summary(item) for item in load_examples().values()]


def get_example(example_id: str) -> ClassroomExample:
    item = load_examples().get(example_id)
    if item is None:
        raise HTTPException(404, "没有找到这个课堂案例")
    return item


@router.get("/{example_id}")
def example_detail(example_id: str):
    return get_example(example_id)


@router.get("/{example_id}/download")
def download_example(example_id: str):
    item = get_example(example_id)
    return Response(
        json.dumps(item.model_dump(), ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{item.id}.json"'},
    )
