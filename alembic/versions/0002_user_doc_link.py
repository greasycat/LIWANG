"""link docs ↔ user_files for personal-file RAG

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-10
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "docs",
        sa.Column(
            "owner_user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_docs_owner", "docs", ["owner_user_id"])

    op.add_column(
        "user_files",
        sa.Column(
            "doc_id",
            sa.String(36),
            sa.ForeignKey("docs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_user_files_doc", "user_files", ["doc_id"])


def downgrade() -> None:
    op.drop_index("ix_user_files_doc", table_name="user_files")
    op.drop_column("user_files", "doc_id")
    op.drop_index("ix_docs_owner", table_name="docs")
    op.drop_column("docs", "owner_user_id")
