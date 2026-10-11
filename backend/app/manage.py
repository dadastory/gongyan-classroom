import argparse
import getpass
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from .db import SessionLocal, engine
from .models import AuditEvent, Enrollment, Group, MeaningUnit, Message, Outcome, Phase, Topic, User
from .schemas import TopicSettings
from .security import PASSWORDS
from .skills import ensure_skills

BACKEND = Path(__file__).resolve().parents[1]


def migrate():
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(config, "head")


def seed_demo():
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == "teacher")):
            print("演示账号已经存在，未覆盖任何现有数据。")
            return
        password_hash = PASSWORDS.hash("Classroom2026!")
        teacher = User(username="teacher", name="陈老师", role="teacher", password_hash=password_hash)
        db.add(teacher)
        db.flush()
        ensure_skills(db, teacher.id)
        names = [
            "林晓",
            "周予",
            "陈思",
            "许言",
            "张宁",
            "李乐",
            "王悦",
            "赵辰",
            "刘雨",
            "孙然",
            "郑禾",
            "吴桐",
            "何一",
            "宋语",
            "唐可",
            "杨帆",
            "黄知",
            "徐明",
            "罗安",
            "高远",
            "方圆",
            "谢文",
            "苏禾",
            "叶青",
            "程新",
            "陆瑶",
            "白露",
            "沈知",
            "秦月",
            "江南",
        ]
        students = []
        for index, name in enumerate(names, start=1):
            student = User(
                username=f"student{index:02}", name=name, role="student", password_hash=password_hash
            )
            db.add(student)
            students.append(student)
        db.flush()
        now = time.time()
        config = TopicSettings().model_dump()
        config["rules"]["enabled"] = False
        topic = Topic(
            teacher_id=teacher.id,
            title="生成式 AI 应该走进课堂吗？",
            description="结合学习体验，讨论生成式 AI 对课堂学习的价值与风险。请围绕学习效果、"
            "思考能力与公平性提供具体依据，比较不同观点，最终形成一份有条件的使用建议。",
            references="讨论材料：学校拟允许学生在探究任务中使用生成式 AI，但要求说明使用过程。\n"
            "思考：哪些环节适合使用？哪些环节需要独立完成？如何验证生成内容？",
            join_code="GY2026",
            join_open=False,
            status="active",
            settings=config,
            is_demo=True,
            created_at=now - 1800,
        )
        db.add(topic)
        db.flush()
        group_names = ["思辨小组", "探索小组", "知行小组", "求证小组", "共创小组"]
        for index, name in enumerate(group_names):
            members = students[index * 6 : (index + 1) * 6]
            group = Group(
                topic_id=topic.id,
                name=name,
                capacity=6,
                state="active",
                phase_index=2,
                version=3,
                deadline=now + (8 - index) * 60,
            )
            db.add(group)
            db.flush()
            phase = Phase(
                group_id=group.id,
                index=2,
                name="论证协商",
                started_at=now - 180,
                member_ids=[student.id for student in members],
            )
            db.add(phase)
            db.flush()
            group.phase_id = phase.id
            for student in members:
                db.add(Enrollment(topic_id=topic.id, user_id=student.id, group_id=group.id))
            db.add(
                AuditEvent(
                    topic_id=topic.id,
                    group_id=group.id,
                    actor_id=teacher.id,
                    event="group.start",
                    data={"demo_fixture": True},
                    created_at=now - 180,
                )
            )
            texts = [
                ("我认为 AI 可以帮助我们快速整理资料。", "C1", "E0", True),
                ("但如果直接接受答案，会不会影响独立思考？", "C2", "E0", True),
                ("例如做这次探究时，我们用它列出观点，再自己查证来源，这样能节省时间。", "C3", "E0", True),
                ("对，需要把资料整理和观点判断分开，判断仍由我们完成。", "C3", "E0", True),
                (
                    "综合大家的观点，可以允许它辅助搜集思路，同时要求学生验证依据并说明使用过程。",
                    "C4",
                    "E1",
                    True,
                ),
                ("我们还可以拿一个具体任务测试这套建议，检查哪些环节确实提高了学习效果。", "C5", "E0", True),
            ]
            if index == 1:
                texts = [
                    ("我不太明白这两个要求有什么区别。", "C2", "E2", True),
                    ("还是没有理解，感觉任务要求有点模糊。", "C2", "E2", True),
                    ("我仍然不知道该从哪个问题开始，有点困惑。", "C2", "E2", True),
                    ("我们先各自列一个观点吧。", "C1", "E0", True),
                ]
            if index == 3:
                texts = [
                    ("今天中午想吃什么？", "C0", "E1", False),
                    ("听说食堂出了新菜。", "C0", "E0", False),
                    ("我也想试试看！", "C0", "E1", False),
                    ("那等会儿一起去吧。", "C0", "E1", False),
                ]
            previous = None
            for turn, (content, cognitive, emotion, relevant) in enumerate(texts):
                author = members[0] if index == 1 and turn < 3 else members[turn % len(members)]
                message = Message(
                    group_id=group.id,
                    phase_id=phase.id,
                    author_id=author.id,
                    kind="student",
                    content=content,
                    client_id=f"demo-{index}-{turn}",
                    reply_to=previous.id if previous else None,
                    analysis_status="complete",
                    created_at=now - 160 + turn * 24,
                )
                db.add(message)
                db.flush()
                db.add(
                    MeaningUnit(
                        message_id=message.id,
                        phase_id=phase.id,
                        start=0,
                        end=len(content),
                        quote=content,
                        cognitive=cognitive,
                        emotion=emotion,
                        task_relevant=relevant,
                        metacognitive=[],
                        social=[],
                        reason="演示数据的人工示例标注，非真实模型分析结果。",
                        confidence=1,
                        skill_slug="engagement-coding",
                        skill_version=1,
                        config_version=1,
                        model="demo-fixture",
                        created_at=message.created_at + 1,
                    )
                )
                previous = message
            if index == 4:
                db.add(
                    Outcome(
                        group_id=group.id,
                        phase_id=phase.id,
                        author_id=members[0].id,
                        content="建议有条件地使用生成式 AI：辅助生成思路、核对信息来源、记录使用过程，"
                        "并保留独立思考和最终判断环节。",
                    )
                )
        preparing = Topic(
            teacher_id=teacher.id,
            title="校园节能方案设计",
            description="观察校园日常能源使用，寻找一项可以改进的场景，提出方案、估算影响，并讨论实施条件。",
            references="可从照明、空调、用水和出行等场景入手。",
            join_code="JOIN26",
            join_open=True,
            settings=TopicSettings(grouping_mode="self").model_dump(),
            is_demo=True,
            created_at=now - 1200,
        )
        db.add(preparing)
        db.flush()
        for student in students[:12]:
            db.add(Enrollment(topic_id=preparing.id, user_id=student.id))
        for name, direction in [("照明与用电", "教室照明和设备待机"), ("绿色出行", "校园通勤与低碳出行")]:
            db.add(Group(topic_id=preparing.id, name=name, direction=direction, capacity=6))
        db.commit()
    print("演示数据已创建。老师 teacher / 学生 student01–student30；密码 Classroom2026!。")


def create_teacher(username: str, name: str):
    password = getpass.getpass("老师密码（至少 8 位）: ")
    if len(password) < 8:
        raise SystemExit("密码至少需要 8 位")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == username.lower())):
            raise SystemExit("账号已存在")
        user = User(
            username=username.lower(), name=name, role="teacher", password_hash=PASSWORDS.hash(password)
        )
        db.add(user)
        db.flush()
        ensure_skills(db, user.id)
        db.commit()
    print("老师账号已创建。")


def main():
    parser = argparse.ArgumentParser(description="课堂平台数据库与账号管理")
    parser.add_argument("command", choices=["migrate", "seed-demo", "create-teacher", "export-sqlite", "backup"])
    parser.add_argument("--username", default="")
    parser.add_argument("--name", default="老师")
    parser.add_argument("--output", type=Path, help="迁移或备份的目标文件，不能覆盖已有文件")
    args = parser.parse_args()
    if args.command == "migrate":
        migrate()
    elif args.command == "seed-demo":
        seed_demo()
    elif args.command in ("export-sqlite", "backup"):
        if not args.output:
            parser.error(f"{args.command} 需要 --output")
        import json

        from .storage import backup_sqlite, copy_to_sqlite

        operation = copy_to_sqlite if args.command == "export-sqlite" else backup_sqlite
        try:
            result = operation(engine, args.output)
        except (ValueError, FileExistsError) as error:
            parser.error(str(error))
        print(json.dumps(result, ensure_ascii=False))
    elif args.username:
        create_teacher(args.username, args.name)
    else:
        parser.error("create-teacher 需要 --username")


if __name__ == "__main__":
    main()
