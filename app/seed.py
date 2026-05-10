"""Idempotent demo seed. Runs once when `users` table is empty."""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import store
from .models import (
    OcrJob,
    Upload,
    Usage,
    User,
    UserFile,
)


def _new_id() -> str:
    return str(uuid4())


def seed_if_empty(db: Session) -> bool:
    if db.scalar(select(func.count()).select_from(User)) > 0:
        return False
    _seed(db)
    return True


def _seed(db: Session) -> None:
    now = store.now()

    admin = User(
        username="admin",
        password_hash=store.hash_password("admin"),
        display_name="管理员",
        role="admin",
        acl_max="restricted",
        monthly_token_cap=None,
        storage_quota_bytes=500 * 1024 * 1024,
    )
    alice = User(
        username="alice",
        password_hash=store.hash_password("alice"),
        display_name="李娜 (R&D)",
        role="user",
        acl_max="internal",
        monthly_token_cap=200_000,
        storage_quota_bytes=200 * 1024 * 1024,
    )
    bob = User(
        username="bob",
        password_hash=store.hash_password("bob"),
        display_name="王伟 (QA)",
        role="user",
        acl_max="internal",
        monthly_token_cap=200_000,
        storage_quota_bytes=store.DEFAULT_STORAGE_QUOTA_BYTES,
    )
    carol = User(
        username="carol",
        password_hash=store.hash_password("carol"),
        display_name="赵敏 (生产)",
        role="user",
        acl_max="public",
        monthly_token_cap=100_000,
        storage_quota_bytes=store.DEFAULT_STORAGE_QUOTA_BYTES,
    )
    db.add_all([admin, alice, bob, carol])
    db.flush()  # populate IDs

    # Chat sessions are not seeded — every user starts with an empty history.

    # Doc library starts empty — admins upload real files via /admin/upload.

    job_seeds = [
        ("legacy/2018-焊接报告-扫描.pdf", "done", 1, None),
        ("legacy/SOP-旧版-002.pdf", "done", 1, None),
        ("legacy/质检记录-2019Q4.pdf", "claimed", 1, None),
        ("legacy/破损图纸-A2.pdf", "pending", 0, None),
        ("legacy/供应商旧合同-005.pdf", "failed", 3, "OCR confidence < 0.4"),
    ]
    for i, (src, st, attempts, err) in enumerate(job_seeds, start=1):
        claimed = st in ("claimed", "done")
        db.add(
            OcrJob(
                doc_source=src,
                status=st,
                attempts=attempts,
                claimed_by="gpu-box-01" if claimed else None,
                claimed_at=now - timedelta(hours=i) if claimed else None,
                created_at=now - timedelta(hours=i + 1),
                error=err,
            )
        )

    _seed_user_files(db, alice.id, now)

    upload_seeds = [
        ("2026Q2-工艺改进-提案.docx", 84_000, "R&D", "提案", "v1", "internal", False, "done", 100, None),
        ("供应商-华东金属-资质.pdf", 312_000, "供应链", "资质", "v3", "internal", False, "done", 100, None),
        ("注塑参数-A124-初稿.xlsx", 41_000, "生产", "参数", "v1", "internal", False, "embedding", 78, None),
        ("ISO9001-2025-内审报告.pdf", 1_840_000, "QA", "审核", "2025", "internal", False, "parsing", 42, None),
        ("legacy-员工守则-扫描.pdf", 5_900_000, "HR", "手册", "2018", "public", True, "queued", 0, None),
        ("漆包线规格-补充.docx", 67_000, "R&D", "规格", "v4.1", "internal", False, "uploading", 30, None),
        ("废品分析-2026Q1.xlsx", 28_000, "QA", "分析", "2026Q1", "internal", False, "failed", 0,
         "PDF 文本密度 < 0.1, 已转入 OCR 队列失败"),
    ]
    for idx, (fn, size, dept, dtype, ver, acl, no_llm, st, prog, err) in enumerate(upload_seeds):
        mime = (
            "application/pdf" if fn.endswith(".pdf")
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if fn.endswith(".docx")
            else "application/vnd.ms-excel"
        )
        started = now - timedelta(minutes=2) if st not in ("queued", "failed") else None
        db.add(
            Upload(
                id=_new_id(),
                filename=fn,
                size=size,
                mime=mime,
                created_at=now - timedelta(minutes=idx * 7),
                dept=dept,
                doc_type=dtype,
                version=ver,
                acl=acl,
                no_llm=no_llm,
                status=st,
                progress=prog,
                error=err,
                started_at=started,
                uploaded_by=admin.id,
            )
        )

    this_month = now.strftime("%Y-%m")
    last_month = (now - timedelta(days=32)).strftime("%Y-%m")
    db.add_all(
        [
            Usage(user_id=alice.id, month=this_month, queries=47,
                  prompt_tokens=38_200, completion_tokens=12_400,
                  cached_tokens=8_100, cost_cny=0.92),
            Usage(user_id=alice.id, month=last_month, queries=92,
                  prompt_tokens=71_500, completion_tokens=22_300,
                  cached_tokens=14_800, cost_cny=1.74),
            Usage(user_id=bob.id, month=this_month, queries=18,
                  prompt_tokens=14_800, completion_tokens=4_200,
                  cached_tokens=2_900, cost_cny=0.34),
            Usage(user_id=bob.id, month=last_month, queries=31,
                  prompt_tokens=24_900, completion_tokens=7_200,
                  cached_tokens=4_400, cost_cny=0.58),
            Usage(user_id=carol.id, month=this_month, queries=9,
                  prompt_tokens=7_400, completion_tokens=2_100,
                  cached_tokens=1_500, cost_cny=0.17),
        ]
    )

    db.commit()


def _seed_user_files(db, alice_id: int, now) -> None:
    def add_uf(name: str, parent_id: str | None, *,
               is_folder: bool = False, size: int = 0, mime: str = "",
               minutes_ago: int = 0, acl: str = "internal") -> str:
        fid = _new_id()
        db.add(
            UserFile(
                id=fid,
                user_id=alice_id,
                parent_id=parent_id,
                name=name,
                is_folder=is_folder,
                size=size,
                mime=mime if not is_folder else "folder",
                acl=acl,
                created_at=now - timedelta(minutes=minutes_ago),
            )
        )
        return fid

    proj = add_uf("项目-X 系列电机", None, is_folder=True, minutes_ago=720)
    drafts = add_uf("草稿", None, is_folder=True, minutes_ago=600)
    arch = add_uf("归档", None, is_folder=True, minutes_ago=4800)

    add_uf("X-2026-绕组方案.docx", proj, size=68_000,
           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
           minutes_ago=300)
    add_uf("X-2026-参数表.xlsx", proj, size=42_000,
           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
           minutes_ago=180)
    add_uf("实验记录-2026-04.pdf", proj, size=2_400_000,
           mime="application/pdf", minutes_ago=120)

    add_uf("提案-改进意见.md", drafts, size=4_200,
           mime="text/markdown", minutes_ago=60, acl="restricted")
    add_uf("竞品调研笔记.docx", drafts, size=120_000,
           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
           minutes_ago=30)

    add_uf("2024-旧规格-参考.pdf", arch, size=8_400_000,
           mime="application/pdf", minutes_ago=4000)

    add_uf("TODO.md", None, size=1_800,
           mime="text/markdown", minutes_ago=15, acl="public")
    add_uf("会议纪要-2026-05-08.docx", None, size=22_000,
           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
           minutes_ago=120)
