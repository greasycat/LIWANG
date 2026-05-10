"""Pydantic response schemas for the JSON API consumed by the Next.js frontend."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------- shared ----------


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CitationOut(_Base):
    doc_id: str
    chunk_id: str
    label: str
    source: str
    page: Optional[int] = None


# ---------- users ----------


class UserOut(_Base):
    id: int
    username: str
    display_name: str
    role: Literal["admin", "user"]
    acl_max: Literal["public", "internal", "restricted"]
    monthly_token_cap: Optional[int] = None
    storage_quota_bytes: int
    created_at: datetime


class MeOut(_Base):
    user: UserOut
    month_tokens_used: int
    month_tokens_cap: Optional[int] = None
    month_tokens_pct: Optional[float] = None


class AdminUserRow(_Base):
    user: UserOut
    month_tokens: int
    storage_used: int


# ---------- sessions / messages ----------


class ChatSessionOut(_Base):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    archived: bool


class MessageOut(_Base):
    id: str
    session_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    citations: list[CitationOut] = Field(default_factory=list)
    rating: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_cny: float = 0.0
    model: Optional[str] = None
    created_at: datetime


class PostMessageOut(_Base):
    user_message: MessageOut
    pending_message: MessageOut
    stream_url: str


# ---------- docs ----------


class DocOut(_Base):
    id: str
    source: str
    dept: str
    doc_type: str
    version: str
    effective_date: str
    acl: Literal["public", "internal", "restricted", "private"]
    no_llm: bool
    chunks: int
    embed_status: str
    uploaded_by: str
    uploaded_at: datetime
    file_path: Optional[str] = None
    mime: Optional[str] = None


class DocPreviewOut(_Base):
    doc: DocOut
    kind: Literal["pdf", "docx", "text", "unsupported"]
    body: Optional[str] = None
    error: Optional[str] = None
    has_file: bool
    raw_url: str
    download_url: str


# ---------- user files ----------


class UserFileOut(_Base):
    id: str
    user_id: int
    parent_id: Optional[str] = None
    name: str
    is_folder: bool
    size: int
    mime: str
    acl: Literal["public", "internal", "restricted"]
    file_path: Optional[str] = None
    doc_id: Optional[str] = None
    created_at: datetime
    embed_status: Optional[str] = None  # mirrored from joined Doc when present


class FolderCrumb(_Base):
    id: str
    name: str


class FolderTreeNode(_Base):
    id: str
    name: str
    depth: int
    parent_id: Optional[str] = None


class FilesListing(_Base):
    items: list[UserFileOut]
    crumbs: list[FolderCrumb]
    parent_id: Optional[str] = None
    folder_tree: list[FolderTreeNode]
    storage_used: int
    storage_quota: int
    storage_pct: float
    target_user: UserOut


class FilePreviewOut(_Base):
    file: UserFileOut
    kind: Literal["pdf", "docx", "text", "unsupported"]
    body: Optional[str] = None
    error: Optional[str] = None
    raw_url: str
    download_url: str


# ---------- uploads (admin staging area) ----------


class UploadOut(_Base):
    id: str
    filename: str
    size: int
    mime: str
    dept: str
    doc_type: str
    version: str
    acl: str
    no_llm: bool
    status: str
    progress: int
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    file_path: Optional[str] = None
    uploaded_by: Optional[int] = None
    doc_id: Optional[str] = None
    created_at: datetime


class UploadTable(_Base):
    items: list[UploadOut]
    counts: dict[str, int]
    status_labels: dict[str, str]
    active_filter: str


# ---------- ocr ----------


class OcrJobOut(_Base):
    id: int
    doc_source: str
    status: str
    attempts: int
    claimed_by: Optional[str] = None
    claimed_at: Optional[datetime] = None
    created_at: datetime
    error: Optional[str] = None


# ---------- usage / overview ----------


class UsageRow(_Base):
    user_id: int
    month: str
    queries: int
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    cost_cny: float


class AdminOverview(_Base):
    month: str
    total_queries: int
    total_tokens: int
    total_cost: float
    active_users: int
    failed_jobs: int
    doc_count: int


class UsageGrid(_Base):
    months: list[str]
    users: list[UserOut]
    cells: dict[int, dict[str, UsageRow]]


# ---------- bulk action payload ----------


class BulkAction(BaseModel):
    action: str
    ids: list[str] = Field(default_factory=list)
    value: Optional[str] = None


class AclBody(BaseModel):
    acl: Literal["public", "internal", "restricted"]
    recursive: bool = False


class RenameBody(BaseModel):
    name: str


class RenameSessionBody(BaseModel):
    title: str


class CreateFolderBody(BaseModel):
    name: str
    parent_id: Optional[str] = None


class LoginBody(BaseModel):
    username: str
    password: str


class QuotaBody(BaseModel):
    monthly_token_cap: Optional[int] = None
    storage_quota_mb: Optional[int] = None
    acl_max: Optional[Literal["public", "internal", "restricted"]] = None


class UploadPatch(BaseModel):
    dept: Optional[str] = None
    doc_type: Optional[str] = None
    version: Optional[str] = None
    acl: Optional[Literal["public", "internal", "restricted"]] = None
    no_llm: Optional[bool] = None


class RatingBody(BaseModel):
    value: int
