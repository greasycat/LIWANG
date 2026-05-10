// Mirrors app/schemas.py — keep in sync with Pydantic models.

export type Acl = "public" | "internal" | "restricted";
export type DocAcl = Acl | "private";
export type Role = "admin" | "user";

export interface Citation {
  doc_id: string;
  chunk_id: string;
  label: string;
  source: string;
  page: number | null;
}

export interface User {
  id: number;
  username: string;
  display_name: string;
  role: Role;
  acl_max: Acl;
  monthly_token_cap: number | null;
  storage_quota_bytes: number;
  created_at: string;
}

export interface Me {
  user: User;
  month_tokens_used: number;
  month_tokens_cap: number | null;
  month_tokens_pct: number | null;
}

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  archived: boolean;
}

export interface Message {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations: Citation[];
  rating: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_cny: number;
  model: string | null;
  created_at: string;
}

export interface PostMessageResponse {
  user_message: Message;
  pending_message: Message;
  stream_url: string;
}

export interface Doc {
  id: string;
  source: string;
  dept: string;
  doc_type: string;
  version: string;
  effective_date: string;
  acl: DocAcl;
  no_llm: boolean;
  chunks: number;
  embed_status: string;
  uploaded_by: string;
  uploaded_at: string;
  file_path: string | null;
  mime: string | null;
}

export interface DocPreview {
  doc: Doc;
  kind: "pdf" | "docx" | "text" | "unsupported";
  body: string | null;
  error: string | null;
  has_file: boolean;
  raw_url: string;
  download_url: string;
}

export interface UserFile {
  id: string;
  user_id: number;
  parent_id: string | null;
  name: string;
  is_folder: boolean;
  size: number;
  mime: string;
  acl: Acl;
  file_path: string | null;
  doc_id: string | null;
  created_at: string;
  embed_status: string | null;
}

export interface FolderCrumb {
  id: string;
  name: string;
}

export interface FolderTreeNode {
  id: string;
  name: string;
  depth: number;
  parent_id: string | null;
}

export interface FilesListing {
  items: UserFile[];
  crumbs: FolderCrumb[];
  parent_id: string | null;
  folder_tree: FolderTreeNode[];
  storage_used: number;
  storage_quota: number;
  storage_pct: number;
  target_user: User;
}

export interface FilePreview {
  file: UserFile;
  kind: "pdf" | "docx" | "text" | "unsupported";
  body: string | null;
  error: string | null;
  raw_url: string;
  download_url: string;
}

export interface Upload {
  id: string;
  filename: string;
  size: number;
  mime: string;
  dept: string;
  doc_type: string;
  version: string;
  acl: string;
  no_llm: boolean;
  status: string;
  progress: number;
  error: string | null;
  started_at: string | null;
  file_path: string | null;
  uploaded_by: number | null;
  doc_id: string | null;
  created_at: string;
}

export interface UploadTable {
  items: Upload[];
  counts: Record<string, number>;
  status_labels: Record<string, string>;
  active_filter: string;
}

export interface OcrJob {
  id: number;
  doc_source: string;
  status: string;
  attempts: number;
  claimed_by: string | null;
  claimed_at: string | null;
  created_at: string;
  error: string | null;
}

export interface UsageRow {
  user_id: number;
  month: string;
  queries: number;
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens: number;
  cost_cny: number;
}

export interface AdminOverview {
  month: string;
  total_queries: number;
  total_tokens: number;
  total_cost: number;
  active_users: number;
  failed_jobs: number;
  doc_count: number;
}

export interface AdminUserRow {
  user: User;
  month_tokens: number;
  storage_used: number;
}

export interface UsageGrid {
  months: string[];
  users: User[];
  cells: Record<number, Record<string, UsageRow>>;
}
