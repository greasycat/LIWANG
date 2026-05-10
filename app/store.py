"""SQLAlchemy-backed data access. Same surface as the prior in-memory store.

Most functions take a `db: Session` as first arg. Routes wire it from
`request.state.db` (set by middleware in `app/main.py`).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Literal
from uuid import uuid4

import bcrypt
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .config import settings
from .models import (
    ChatSession,
    Chunk,
    Citation,
    Doc,
    Message,
    OcrJob,
    Upload,
    Usage,
    User,
    UserFile,
)

# ---------- shared types / constants ----------

Role = Literal["admin", "user"]
Acl = Literal["public", "internal", "restricted"]
JobStatus = Literal["pending", "claimed", "done", "failed"]
UploadStatus = Literal["queued", "uploading", "parsing", "embedding", "done", "failed"]

UPLOAD_STATUSES: tuple[UploadStatus, ...] = (
    "queued",
    "uploading",
    "parsing",
    "embedding",
    "done",
    "failed",
)
STATUS_LABELS: dict[UploadStatus, str] = {
    "queued": "待上传",
    "uploading": "上传中",
    "parsing": "解析中",
    "embedding": "嵌入中",
    "done": "已完成",
    "failed": "失败",
}

DEFAULT_STORAGE_QUOTA_BYTES = settings.default_storage_quota_bytes


def now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------- users ----------


def authenticate(db: Session, username: str, password: str) -> User | None:
    u = db.scalar(select(User).where(User.username == username))
    if u and verify_password(password, u.password_hash):
        return u
    return None


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def all_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)).all())


def set_user_acl_max(db: Session, user_id: int, acl: str) -> User | None:
    if acl not in ("public", "internal", "restricted"):
        return None
    u = db.get(User, user_id)
    if not u:
        return None
    u.acl_max = acl
    db.commit()
    return u


# ---------- chat sessions ----------


def user_sessions(db: Session, user_id: int) -> list[ChatSession]:
    return list(
        db.scalars(
            select(ChatSession)
            .where(ChatSession.user_id == user_id, ChatSession.archived.is_(False))
            .order_by(ChatSession.updated_at.desc())
        ).all()
    )


def get_session(db: Session, sid: str) -> ChatSession | None:
    return db.get(ChatSession, sid)


def create_session(db: Session, user_id: int, title: str = "新对话") -> ChatSession:
    s = ChatSession(id=_new_id(), user_id=user_id, title=title)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def rename_session(db: Session, sid: str, title: str) -> None:
    s = db.get(ChatSession, sid)
    if not s:
        return
    title = (title or "").strip()
    if title:
        s.title = title
        db.commit()


def delete_session(db: Session, sid: str) -> None:
    db.execute(delete(ChatSession).where(ChatSession.id == sid))
    db.commit()


# ---------- messages ----------


def get_messages(db: Session, sid: str) -> list[Message]:
    return list(
        db.scalars(
            select(Message)
            .where(Message.session_id == sid)
            .order_by(Message.created_at, Message.id)
        ).all()
    )


def find_message(db: Session, mid: str) -> Message | None:
    return db.get(Message, mid)


def add_message(
    db: Session,
    session_id: str,
    role: Literal["user", "assistant"],
    content: str,
    citations: list[Citation] | None = None,
    **kw,
) -> Message:
    m = Message(
        id=_new_id(),
        session_id=session_id,
        role=role,
        content=content,
        citations=citations or [],
        **kw,
    )
    db.add(m)
    s = db.get(ChatSession, session_id)
    if s:
        s.updated_at = now()
        if role == "user" and (s.title in ("", "新对话") or not s.title.strip()):
            s.title = content[:24] if len(content) > 24 else (content or s.title)
    db.commit()
    db.refresh(m)
    return m


def set_message_rating(db: Session, mid: str, value: int) -> bool:
    m = db.get(Message, mid)
    if not m:
        return False
    m.rating = max(-1, min(1, value))
    db.commit()
    return True


def add_usage(
    db: Session,
    user_id: int,
    *,
    queries: int = 0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cached_tokens: int = 0,
    cost_cny: float = 0.0,
) -> None:
    ym = now().strftime("%Y-%m")
    stmt = (
        pg_insert(Usage)
        .values(
            user_id=user_id,
            month=ym,
            queries=queries,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            cost_cny=cost_cny,
        )
        .on_conflict_do_update(
            index_elements=["user_id", "month"],
            set_={
                "queries": Usage.queries + queries,
                "prompt_tokens": Usage.prompt_tokens + prompt_tokens,
                "completion_tokens": Usage.completion_tokens + completion_tokens,
                "cached_tokens": Usage.cached_tokens + cached_tokens,
                "cost_cny": Usage.cost_cny + cost_cny,
            },
        )
    )
    db.execute(stmt)
    db.commit()


def month_tokens(db: Session, user_id: int, ym: str) -> int:
    row = db.execute(
        select(Usage.prompt_tokens, Usage.completion_tokens).where(
            Usage.user_id == user_id, Usage.month == ym
        )
    ).first()
    if not row:
        return 0
    return int(row[0] or 0) + int(row[1] or 0)


def all_usage(db: Session) -> list[Usage]:
    return list(db.scalars(select(Usage).order_by(Usage.user_id, Usage.month)).all())


# ---------- docs ----------


def get_doc(db: Session, doc_id: str) -> Doc | None:
    return db.get(Doc, doc_id)


def all_docs(db: Session) -> list[Doc]:
    return list(db.scalars(select(Doc).order_by(Doc.uploaded_at.desc())).all())


def create_doc(db: Session, **fields) -> Doc:
    d = Doc(id=_new_id(), **fields)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def update_doc(db: Session, doc_id: str, **fields) -> Doc | None:
    d = db.get(Doc, doc_id)
    if not d:
        return None
    for k, v in fields.items():
        if hasattr(d, k):
            setattr(d, k, v)
    db.commit()
    return d


def delete_doc(db: Session, doc_id: str) -> bool:
    d = db.get(Doc, doc_id)
    if not d:
        return False
    db.delete(d)
    db.commit()
    return True


def set_doc_acl(db: Session, doc_id: str, acl: str) -> Doc | None:
    if acl not in ("public", "internal", "restricted"):
        return None
    d = db.get(Doc, doc_id)
    if not d:
        return None
    d.acl = acl
    db.commit()
    return d


# ---------- ocr jobs ----------


def all_ocr_jobs(db: Session) -> list[OcrJob]:
    return list(db.scalars(select(OcrJob).order_by(OcrJob.created_at.desc())).all())


def get_ocr_job(db: Session, job_id: int) -> OcrJob | None:
    return db.get(OcrJob, job_id)


def claim_next_ocr_job(db: Session, runner_id: str) -> OcrJob | None:
    """SELECT pending FOR UPDATE SKIP LOCKED — claim and return."""
    row = db.execute(
        select(OcrJob)
        .where(OcrJob.status == "pending")
        .order_by(OcrJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if not row:
        return None
    row.status = "claimed"
    row.claimed_by = runner_id
    row.claimed_at = now()
    row.attempts = (row.attempts or 0) + 1
    db.commit()
    return row


def finish_ocr_job(
    db: Session, job_id: int, status: JobStatus, error: str | None = None
) -> OcrJob | None:
    j = db.get(OcrJob, job_id)
    if not j:
        return None
    j.status = status
    j.error = error
    db.commit()
    return j


# ---------- user files ----------


def list_files(db: Session, user_id: int, parent_id: str | None) -> list[UserFile]:
    stmt = select(UserFile).where(UserFile.user_id == user_id)
    if parent_id is None:
        stmt = stmt.where(UserFile.parent_id.is_(None))
    else:
        stmt = stmt.where(UserFile.parent_id == parent_id)
    items = list(db.scalars(stmt).all())
    items.sort(key=lambda f: (not f.is_folder, f.name.lower()))
    return items


def get_file(db: Session, file_id: str) -> UserFile | None:
    return db.get(UserFile, file_id)


def folder_path(db: Session, folder_id: str | None) -> list[UserFile]:
    chain: list[UserFile] = []
    current = db.get(UserFile, folder_id) if folder_id else None
    seen: set[str] = set()
    while current and current.id not in seen:
        seen.add(current.id)
        chain.insert(0, current)
        current = db.get(UserFile, current.parent_id) if current.parent_id else None
    return chain


def descendants(db: Session, folder_id: str) -> list[UserFile]:
    out: list[UserFile] = []
    queue: list[str] = [folder_id]
    while queue:
        pid = queue.pop()
        kids = list(db.scalars(select(UserFile).where(UserFile.parent_id == pid)).all())
        for f in kids:
            out.append(f)
            if f.is_folder:
                queue.append(f.id)
    return out


def storage_used(db: Session, user_id: int) -> int:
    total = db.scalar(
        select(func.coalesce(func.sum(UserFile.size), 0)).where(
            UserFile.user_id == user_id, UserFile.is_folder.is_(False)
        )
    )
    return int(total or 0)


def can_store(db: Session, user_id: int, additional: int, quota: int) -> bool:
    return storage_used(db, user_id) + additional <= quota


def create_folder(
    db: Session, user_id: int, name: str, parent_id: str | None
) -> UserFile:
    name = (name or "新建文件夹").strip() or "新建文件夹"
    f = UserFile(
        id=_new_id(),
        user_id=user_id,
        parent_id=parent_id,
        name=name,
        is_folder=True,
        size=0,
        mime="folder",
        acl="internal",
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def add_user_file(
    db: Session,
    user_id: int,
    name: str,
    parent_id: str | None,
    size: int,
    mime: str,
    *,
    file_path: str | None = None,
    acl: str = "internal",
) -> UserFile:
    f = UserFile(
        id=_new_id(),
        user_id=user_id,
        parent_id=parent_id,
        name=name,
        is_folder=False,
        size=size,
        mime=mime,
        acl=acl,
        file_path=file_path,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def set_user_file_acl(
    db: Session, file_id: str, acl: str, recursive: bool = False
) -> UserFile | None:
    if acl not in ("public", "internal", "restricted"):
        return None
    f = db.get(UserFile, file_id)
    if not f:
        return None
    f.acl = acl
    if f.is_folder and recursive:
        for child in descendants(db, file_id):
            child.acl = acl
    db.commit()
    return f


def rename_file(db: Session, file_id: str, new_name: str) -> UserFile | None:
    f = db.get(UserFile, file_id)
    if not f:
        return None
    new = (new_name or "").strip()
    if new:
        f.name = new
        db.commit()
    return f


def delete_file(db: Session, file_id: str) -> list[UserFile]:
    """Delete file (or folder + descendants). Returns the rows that were removed
    so callers can clean up corresponding bytes on disk."""
    f = db.get(UserFile, file_id)
    if not f:
        return []
    removed: list[UserFile] = [f]
    if f.is_folder:
        removed.extend(descendants(db, file_id))
    db.execute(delete(UserFile).where(UserFile.id == file_id))
    db.commit()
    return removed


def folder_tree(db: Session, user_id: int) -> list[tuple[UserFile, int]]:
    """Flat list of (folder, depth)."""
    all_folders = list(
        db.scalars(
            select(UserFile).where(
                UserFile.user_id == user_id, UserFile.is_folder.is_(True)
            )
        ).all()
    )
    by_parent: dict[str | None, list[UserFile]] = {}
    for f in all_folders:
        by_parent.setdefault(f.parent_id, []).append(f)
    for kids in by_parent.values():
        kids.sort(key=lambda f: f.name.lower())

    out: list[tuple[UserFile, int]] = []

    def walk(parent_id: str | None, depth: int) -> None:
        for f in by_parent.get(parent_id, []):
            out.append((f, depth))
            walk(f.id, depth + 1)

    walk(None, 0)
    return out


# ---------- uploads ----------


def add_upload(
    db: Session,
    filename: str,
    size: int,
    mime: str,
    *,
    file_path: str | None = None,
    uploaded_by: int | None = None,
) -> Upload:
    item = Upload(
        id=_new_id(),
        filename=filename,
        size=size,
        mime=mime or "application/octet-stream",
        file_path=file_path,
        uploaded_by=uploaded_by,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def get_upload(db: Session, uid: str) -> Upload | None:
    return db.get(Upload, uid)


def delete_upload(db: Session, uid: str) -> Upload | None:
    item = db.get(Upload, uid)
    if not item:
        return None
    db.delete(item)
    db.commit()
    return item


def update_upload(db: Session, uid: str, **fields) -> Upload | None:
    item = db.get(Upload, uid)
    if not item:
        return None
    for k, v in fields.items():
        if hasattr(item, k):
            setattr(item, k, v)
    db.commit()
    return item


def filter_uploads(db: Session, status: UploadStatus | None = None) -> list[Upload]:
    stmt = select(Upload)
    if status:
        stmt = stmt.where(Upload.status == status)
    stmt = stmt.order_by(Upload.created_at.desc())
    return list(db.scalars(stmt).all())


def upload_counts(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(Upload.status, func.count()).group_by(Upload.status)
    ).all()
    counts: dict[str, int] = {s: 0 for s in UPLOAD_STATUSES}
    counts["all"] = 0
    for status, n in rows:
        counts[status] = int(n)
        counts["all"] += int(n)
    counts["active"] = (
        counts["uploading"] + counts["parsing"] + counts["embedding"] + counts["queued"]
    )
    return counts


# ---------- canned answer (kept until DeepSeek wired) ----------


def _canned_answer(title: str) -> str:
    return (
        f"根据公司现行文件，关于「{title}」的要点如下：\n\n"
        "1. **适用范围** — 本流程适用于车间内所有相关工序，由 QA 部门统一归口管理。\n"
        "2. **关键指标** — 控制阈值需符合当前版本规范要求；超标记录须留痕并触发复检。\n"
        "3. **复检流程** — 由当班班长上报 QA → QA 抽检确认 → 不合格批次隔离 → 工艺/设备分析 → 整改闭环。\n"
        "4. **责任划分** — 操作员、班长、QA 工程师、车间主任分级签字确认。\n\n"
        "详见来源 [1] 第 3 节及 [2] 中相关规格条目。如需更具体型号信息，可在追问中指定。"
    )
