"""initial schema: users, sessions, messages, docs, chunks (vector), ocr_jobs, usage_monthly, user_files, uploads

Revision ID: 0001
Revises:
Create Date: 2026-05-09

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer, sa.Identity(start=1), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="user"),
        sa.Column("acl_max", sa.String(16), nullable=False, server_default="internal"),
        sa.Column("monthly_token_cap", sa.BigInteger, nullable=True),
        sa.Column("storage_quota_bytes", sa.BigInteger, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(256), nullable=False, server_default="新对话"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("archived", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_sessions_user_updated", "sessions", ["user_id", "updated_at"])

    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False, server_default=""),
        sa.Column("citations", JSONB, nullable=False, server_default="[]"),
        sa.Column("rating", sa.Integer, nullable=False, server_default="0"),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_cny", sa.Float, nullable=False, server_default="0"),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_messages_session_created", "messages", ["session_id", "created_at"])

    op.create_table(
        "docs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source", sa.String(512), nullable=False),
        sa.Column("dept", sa.String(64), nullable=False, server_default=""),
        sa.Column("doc_type", sa.String(64), nullable=False, server_default="其他"),
        sa.Column("version", sa.String(32), nullable=False, server_default="v1"),
        sa.Column("effective_date", sa.String(32), nullable=False, server_default=""),
        sa.Column("acl", sa.String(16), nullable=False, server_default="internal"),
        sa.Column("no_llm", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("chunks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("embed_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("uploaded_by", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("file_path", sa.String(512), nullable=True),
        sa.Column("mime", sa.String(128), nullable=True),
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "doc_id",
            sa.String(36),
            sa.ForeignKey("docs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ord", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("page", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_chunks_doc_ord", "chunks", ["doc_id", "ord"])
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    op.create_table(
        "ocr_jobs",
        sa.Column("id", sa.Integer, sa.Identity(start=1), primary_key=True),
        sa.Column("doc_source", sa.String(512), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("claimed_by", sa.String(64), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("error", sa.Text, nullable=True),
    )

    op.create_table(
        "usage_monthly",
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("month", sa.String(7), primary_key=True),
        sa.Column("queries", sa.Integer, nullable=False, server_default="0"),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cached_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_cny", sa.Float, nullable=False, server_default="0"),
    )

    op.create_table(
        "user_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.String(36),
            sa.ForeignKey("user_files.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("is_folder", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("size", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("mime", sa.String(128), nullable=False, server_default=""),
        sa.Column("acl", sa.String(16), nullable=False, server_default="internal"),
        sa.Column("file_path", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_user_files_user_parent", "user_files", ["user_id", "parent_id"])

    op.create_table(
        "uploads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("size", sa.BigInteger, nullable=False),
        sa.Column(
            "mime", sa.String(128), nullable=False, server_default="application/octet-stream"
        ),
        sa.Column("dept", sa.String(64), nullable=False, server_default="R&D"),
        sa.Column("doc_type", sa.String(64), nullable=False, server_default="其他"),
        sa.Column("version", sa.String(32), nullable=False, server_default="v1"),
        sa.Column("acl", sa.String(16), nullable=False, server_default="internal"),
        sa.Column("no_llm", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_path", sa.String(512), nullable=True),
        sa.Column(
            "uploaded_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "doc_id",
            sa.String(36),
            sa.ForeignKey("docs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("uploads")
    op.drop_index("ix_user_files_user_parent", table_name="user_files")
    op.drop_table("user_files")
    op.drop_table("usage_monthly")
    op.drop_table("ocr_jobs")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.drop_index("ix_chunks_doc_ord", table_name="chunks")
    op.drop_table("chunks")
    op.drop_table("docs")
    op.drop_index("ix_messages_session_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_sessions_user_updated", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("users")
