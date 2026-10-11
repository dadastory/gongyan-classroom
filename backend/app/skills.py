import hashlib
import re

import yaml
from agno.skills import LocalSkills, Skills
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import ROOT
from .models import SkillVersion

SKILLS_PATH = ROOT / "backend" / "skills"


def parse_skill(markdown: str, slug: str) -> tuple[dict, str]:
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", markdown, re.S)
    if not match:
        raise HTTPException(422, "SKILL.md 必须包含 YAML frontmatter 和正文")
    try:
        metadata = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        raise HTTPException(422, "skill 的 YAML 格式无效") from None
    if not isinstance(metadata, dict) or metadata.get("name") != slug:
        raise HTTPException(422, "frontmatter 的 name 必须与 skill 名称一致")
    description = metadata.get("description")
    if not isinstance(description, str) or not 1 <= len(description) <= 1024:
        raise HTTPException(422, "skill 必须有 1–1024 字符的 description")
    if not match.group(2).strip():
        raise HTTPException(422, "skill 正文不能为空")
    return metadata, match.group(2).strip()


def latest_skills(db: Session, teacher_id: str) -> dict[str, SkillVersion]:
    rows = db.scalars(
        select(SkillVersion).where(SkillVersion.teacher_id == teacher_id).order_by(SkillVersion.version)
    ).all()
    return {row.slug: row for row in rows}


def ensure_skills(db: Session, teacher_id: str):
    existing = latest_skills(db, teacher_id)
    loaded = Skills(loaders=[LocalSkills(str(SKILLS_PATH))])
    for path in sorted(SKILLS_PATH.glob("*/SKILL.md")):
        slug = path.parent.name
        if slug in existing:
            continue
        markdown = path.read_text()
        metadata, _ = parse_skill(markdown, slug)
        if loaded.get_skill(slug) is None:
            raise RuntimeError(f"内置 skill 加载失败: {slug}")
        db.add(
            SkillVersion(
                teacher_id=teacher_id,
                slug=slug,
                version=1,
                title=metadata.get("metadata", {}).get("title", slug),
                description=metadata["description"],
                markdown=markdown,
                digest=hashlib.sha256(markdown.encode()).hexdigest(),
            )
        )
    db.flush()


def skill_dict(skill: SkillVersion) -> dict:
    return {
        "id": skill.id,
        "slug": skill.slug,
        "title": skill.title,
        "description": skill.description,
        "version": skill.version,
        "markdown": skill.markdown,
        "digest": skill.digest,
        "created_at": skill.created_at,
    }
