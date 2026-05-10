"""SQLAlchemy 2.x ORM models. Mirrors PLAN.md §16 schema."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------- shared value object ----------


@dataclass
class Citation:
    doc_id: str
    chunk_id: str
    label: str
    source: str
    page: int | None = None


class CitationListType(TypeDecorator):
    """Stores list[Citation] as JSONB; rehydrates on read."""

    impl = JSONB
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if not value:
            return []
        out = []
        for c in value:
            if isinstance(c, Citation):
                out.append(
                    {
                        "doc_id": c.doc_id,
                        "chunk_id": c.chunk_id,
                        "label": c.label,
                        "source": c.source,
                        "page": c.page,
                    }
                )
            else:
                out.append(dict(c))
        return out

    def process_result_value(self, value, dialect) -> list[Citation]:
        if not value:
            return []
        return [Citation(**c) for c in value]


# ---------- tables ----------


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    acl_max: Mapped[str] = mapped_column(String(16), nullable=False, default="internal")
    monthly_token_cap: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    storage_quota_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ChatSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="新对话")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_sessions_user_updated", "user_id", "updated_at"),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    citations: Mapped[list[Citation]] = mapped_column(
        CitationListType, nullable=False, default=list
    )
    rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_cny: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_messages_session_created", "session_id", "created_at"),
    )


class Doc(Base):
    __tablename__ = "docs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(512), nullable=False)
    dept: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False, default="其他")
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    effective_date: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    acl: Mapped[str] = mapped_column(String(16), nullable=False, default="internal")
    no_llm: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embed_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    uploaded_by: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    doc_id: Mapped[str] = mapped_column(
        ForeignKey("docs.id", ondelete="CASCADE"), nullable=False
    )
    ord: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_chunks_doc_ord", "doc_id", "ord"),
    )


class OcrJob(Base):
    __tablename__ = "ocr_jobs"

    id: Mapped[int] = mapped_column(Integer, Identity(start=1), primary_key=True)
    doc_source: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    claimed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Usage(Base):
    __tablename__ = "usage_monthly"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    queries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_cny: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class UserFile(Base):
    __tablename__ = "user_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("user_files.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    is_folder: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    mime: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    acl: Mapped[str] = mapped_column(String(16), default="internal", nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    doc_id: Mapped[str | None] = mapped_column(
        ForeignKey("docs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    doc: Mapped["Doc | None"] = relationship(
        "Doc", foreign_keys=[doc_id], lazy="joined"
    )

    __table_args__ = (
        Index("ix_user_files_user_parent", "user_id", "parent_id"),
    )


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime: Mapped[str] = mapped_column(
        String(128), default="application/octet-stream", nullable=False
    )
    dept: Mapped[str] = mapped_column(String(64), default="R&D", nullable=False)
    doc_type: Mapped[str] = mapped_column(String(64), default="其他", nullable=False)
    version: Mapped[str] = mapped_column(String(32), default="v1", nullable=False)
    acl: Mapped[str] = mapped_column(String(16), default="internal", nullable=False)
    no_llm: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    doc_id: Mapped[str | None] = mapped_column(
        ForeignKey("docs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
