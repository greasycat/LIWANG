# LIWANG RAG System — Project Plan

> Status: Draft v0.5 (lean + UI spec) · Owner: TBD · Last updated: 2026-05-09
> Scale target: ~20 users, ~10k–50k docs, single VPS + 1 local GPU box (OCR only).

## 1. Goal

Internal Q&A over LIWANG manufacturing docs. Chinese corpus. DeepSeek for generation. Keep stack as small as possible — single VPS runs everything except OCR.

## 2. Users & Use Cases

~20 internal staff: R&D, QA, production, supply chain, new hires. Examples:
- "X 系列电机绕组用的漆包线规格?"
- "焊接气孔率超标的复检流程?"
- "型号 A123 的注塑温度区间?"
- "302 不锈钢的认可替代供应商?"

## 3. Doc Sources (Phase 1)

- PDFs — native + scanned
- Office — Word, Excel (BOM/参数表), PPT
- Wiki / 内网 export (HTML)

Out of scope: CAD, ERP/MES live data, video.

## 4. Architecture (minimal)

```
                ┌────────────────────────────┐
                │  Local GPU box (OCR only)  │
                │  ─ PaddleOCR + MinerU      │
                │  ─ Polls VPS for jobs      │
                └─────────────┬──────────────┘
                              │ HTTPS poll/push
                              ▼
┌─────────────────────────────────────────────┐
│  VPS  (single box, ~4 vCPU / 8 GB RAM)      │
│  ┌─────────────┐  ┌──────────────────────┐  │
│  │  FastAPI    │  │  Postgres 16         │  │
│  │  + LlamaIdx │←→│  + pgvector          │  │
│  │  /query     │  │  + zhparser/pg_jieba │  │
│  │  /ingest    │  │  + tsvector (zh FTS) │  │
│  │  /ocr-jobs  │  │  all tables: users,  │  │
│  └──────┬──────┘  │  docs, chunks,       │  │
│         │         │  ocr_jobs, query_log │  │
│  ┌──────▼──────┐  └──────────────────────┘  │
│  │  Static UI  │                            │
│  │  HTMX/Tail. │                            │
│  └─────────────┘                            │
└─────┬────────────────────────────┬──────────┘
      │ HTTPS                      │ HTTPS
      ▼                            ▼
  DeepSeek API           DashScope Embedding API
  (chat / reasoning)     (text-embedding-v3, via LlamaIndex)
```

### 4.1 OCR Runner (only thing not on VPS)

GPU is the one piece the VPS can't host. Everything else stays on the VPS to keep ops trivial.

- **Where**: local machine w/ GPU (office or home).
- **How it gets work**: polls VPS `GET /ocr-jobs/next` every N seconds; downloads PDF; runs PaddleOCR + MinerU; `POST /ocr-jobs/{id}/result` w/ markdown + tables. No queue infra — `ocr_jobs` table in Postgres uses `SELECT ... FOR UPDATE SKIP LOCKED` for safe concurrent claims.
- **Auth**: single API token in env var.
- **Failure**: VPS marks job `failed` after N retries; surfaces in admin UI for manual review.
- **Backfill**: same endpoint, just bulk-enqueue from CLI.

That's it. No Redis, no RabbitMQ, no S3 — VPS holds the originals + OCR output in a local `data/` dir (with daily backup). Job state lives in Postgres.

## 5. Tech Stack (lean)

| Layer | Choice | Notes |
|---|---|---|
| Web | FastAPI | One process, uvicorn |
| Storage | **Postgres 16 + pgvector** | One DB for everything: vectors, metadata, users, sessions, ocr_jobs, query_log. No Milvus, no ES, no separate metadata store. |
| Lexical | Postgres FTS (`tsvector`) + **zhparser** or **pg_jieba** | zh tokenization extension; same DB as vectors → single hybrid query |
| File store | Local disk on VPS (`data/originals/`, `data/ocr/`) | Postgres holds DB + extracted text; raw blobs on disk. Daily rsync backup |
| PDF native | PyMuPDF | Fast, pure Python |
| Office | `python-docx`, `openpyxl`, `python-pptx` | |
| Wiki | One-off importer script (HTML → markdown) | |
| OCR | PaddleOCR + MinerU | On GPU box, see §4.1 |
| Embeddings | **DashScope `text-embedding-v3`** via **LlamaIndex `DashScopeEmbedding`** | Hosted API (Alibaba Cloud, serves Qwen embedding family). 1024 dims default (configurable 64–1024 for v3; switch to `text-embedding-v4` if higher dim needed). No GPU. Tokens billed → log in `embed_log`. |
| Orchestration | **LlamaIndex** | Used for embedding adapter + chunking helpers + ingestion pipeline. Avoid heavy abstractions; thin wrapper. |
| Reranker | bge-reranker-v2-m3 (small) on VPS CPU; or skip in P0 | Optional. Alternative: DashScope rerank API if added later. |
| LLM | DeepSeek-V3 (chat), R1 only when needed | Public API. Called direct (not via LlamaIndex LLM wrapper) to keep streaming + token capture explicit. |
| UI | Jinja2 templates + **HTMX** (partials + SSE) + **Alpine.js** (client state) + **Tailwind CSS** + **daisyUI** components + **Chart.js** (admin) | No SPA, no Node build. Tailwind via standalone binary in CI for purged CSS; everything else via CDN. See §8.2. |
| Auth | Username/password (bcrypt) — `users` table in Postgres | 20 users — overkill avoided |
| Migrations | Alembic | Single source of truth for schema |
| Logs | stdout → systemd journal; `query_log` table in Postgres | |

## 6. Data Pipeline

1. **Upload** — user/admin uploads file via UI, or import script ingests folder.
2. **Classify** — native PDF? → parse directly. Scanned? → write OCR job row, wait for runner.
3. **Parse** — extract text + tables (tables kept as markdown).
4. **Chunk** — ~500 zh chars, 50 overlap, never split tables, prepend headings.
5. **Embed** — `DashScopeEmbedding(model_name=DashScopeTextEmbeddingModels.TEXT_EMBEDDING_V3)` via LlamaIndex; batch chunks (DashScope v3 caps ~10 per request — LlamaIndex chunks across calls); INSERT vectors into `chunks.embedding vector(1024)` (pgvector, HNSW index). Log `tokens` + `cost_cny` per call into `embed_log`.
6. **Index lexical** — populate `chunks.tsv tsvector` via zhparser/pg_jieba; GIN index for FTS.
7. **Done** — `chunks` row carries: doc_id, chunk_id, dept, doc_type, version, effective_date, acl, ocr_confidence, embedding, tsv, content.

Re-ingest = hash check; only changed docs re-processed.

## 7. Retrieval

- Single SQL query does both: pgvector cosine top 20 (`<=>` operator) UNION FTS top 20 (`ts_rank`) → RRF fuse in SQL → top 10
- Optional rerank w/ bge-reranker → top 5
- Filter by ACL in `WHERE` before retrieval (public/internal/restricted)
- Indexes: HNSW on `embedding`, GIN on `tsv`, btree on `(acl, doc_type, effective_date)`

## 8. Generation

- Prompt (zh-CN): "LIWANG公司内部知识助手", cite `[doc:chunk]`, refuse if no context.
- Stream response to UI via SSE.
- Citations link to original file viewer (PDF.js inline, others download).
- **Token accounting**: capture `usage.{prompt_tokens, completion_tokens}` from DeepSeek response (final SSE chunk carries it); compute `cost_cny` from current price table (cache hit / miss separately — DeepSeek bills them differently). Write to `query_log` per request.

## 8.1 Per-User Token Tracking & Quota

- Every query stores: `user_id`, `model`, `prompt_tokens`, `completion_tokens`, `cached_tokens`, `cost_cny`, `created_at` in `query_log`.
- Embedding calls (if billed via hosted API) logged separately in `embed_log` so chat ≠ embed cost.
- **Monthly view**: `usage_monthly` materialized view aggregates per `(user_id, year_month)` → tokens in/out, cost, query count. Refreshed nightly via cron.
- **Quota** (optional, off by default): per-user `monthly_token_cap` on `users` table. Pre-flight check before LLM call; if exceeded, return friendly error + admin notification. Admin can raise cap inline.
- **Admin UI page** `/admin/usage`: table of users × months, sortable; CSV export for finance.
- **User self-view** in UI header: "本月用量 X / Y tokens (¥Z)".

## 8.2 Frontend (UI Spec)

Modern, responsive, ChatGPT-style. Server-rendered (Jinja2 + HTMX) — no SPA, no Node toolchain. Built with Tailwind + daisyUI for polished components without writing CSS.

### 8.2.1 Layout (3-pane on desktop, drawer on mobile)

```
┌─────────────────────────────────────────────────────────────┐
│ Top bar                                                     │
│  LIWANG 知识助手 │           本月 12.4k tokens (¥0.18) │ 👤 ▾ │
├──────────────┬──────────────────────────────────────────────┤
│  Sidebar     │                                              │
│ ┌──────────┐ │       ┌────────────────────────────┐        │
│ │+ 新对话  │ │       │  Centered chat column      │        │
│ └──────────┘ │       │  max-w-3xl mx-auto         │        │
│              │       │                            │        │
│ 🔍 搜索对话  │       │  ┌─ user 询问 ─────────┐  │        │
│              │       │  └──────────────────────┘  │        │
│ ─ 今天       │       │                            │        │
│   • 焊接气孔 │       │  ┌─ assistant ──────────┐ │        │
│   • 注塑温度 │       │  │ 答案 streaming…       │ │        │
│ ─ 昨天       │       │  │                       │ │        │
│   • 304 替代 │       │  │ 来源:                 │ │        │
│ ─ 7 天前     │       │  │  [1] SOP-焊接.pdf p3  │ │        │
│   • 漆包线   │       │  │  [2] BOM-A123.xlsx    │ │        │
│              │       │  └───────────────────────┘ │        │
│              │       │  👍 👎  📋 复制  🔄 重答   │        │
│              │       │                            │        │
│              │       │  ┌─ sticky composer ────┐ │        │
│              │       │  │ [textarea autogrow ] │ │        │
│              │       │  │ 部门▾ 类型▾ 时间▾ ⏎│ │        │
│              │       │  └──────────────────────┘ │        │
│              │       └────────────────────────────┘        │
└──────────────┴──────────────────────────────────────────────┘
```

- **Desktop (≥ md)**: sidebar 280px fixed left + centered chat column (`max-w-3xl mx-auto px-4`).
- **Mobile (< md)**: sidebar collapses to drawer (daisyUI `drawer`); top bar shows ☰ to open.
- Color: light + dark mode (Tailwind `dark:`); toggle in user menu; default = system pref.
- Font: system zh stack — `system-ui, -apple-system, "Microsoft YaHei", "PingFang SC", sans-serif`.
- Empty state on `/`: centered hero "LIWANG知识助手 · 问任何关于公司的问题" + 4 example query chips.

### 8.2.2 Chat session UX (left sidebar)

- **List**: grouped by date bucket — 今天 / 昨天 / 本周 / 本月 / 更早. Each row: title (truncated) + timestamp on hover.
- **Title**: auto-generated from first user message (DeepSeek prompt: "用 6-12 个汉字概括"). Editable inline (HTMX `hx-patch`).
- **Active row**: highlighted (daisyUI `menu-active`).
- **Search**: top of sidebar — filters titles via `hx-get /sessions?q=…` w/ 200ms debounce.
- **Actions per row** (hover or right-click): 重命名 / 删除 / 归档 / 导出 markdown.
- **New chat**: top button — POST `/sessions` returns new id, navigates to `/c/{id}`.
- **Persistence**: scroll position + draft input restored when switching sessions (Alpine `$persist`).

### 8.2.3 Chat column

- Streaming answers via SSE: `<div hx-ext="sse" sse-connect="/c/{id}/stream" sse-swap="message">`.
- Markdown rendering server-side (`markdown-it-py` w/ table + code support) on each chunk; client only appends.
- Citations as inline badges `[1][2]` linking to a side-drawer viewer:
  - PDF → PDF.js iframe at the cited page.
  - Office → download link + raw text preview.
- Per-message actions: 👍 👎 (writes `query_log.rating`), 📋 copy, 🔄 regenerate.
- Composer: textarea autogrow (Alpine), Shift+Enter newline / Enter send, slash menu for filter chips (`/部门 R&D`, `/类型 SOP`, `/年 2024`).
- Quota banner if user near `monthly_token_cap` (>80%): warning toast.

### 8.2.4 Admin Dashboard `/admin`

Admin role only (middleware check). Same layout shell but sidebar shows admin nav instead of chat list.

| Page | Purpose | Key elements |
|---|---|---|
| `/admin` | Overview | KPI cards: total queries (today/month), active users, token spend (¥), failed OCR jobs, low-rated answers. Two charts: queries/day (Chart.js line), spend/day stacked (chat vs embed). |
| `/admin/users` | User management | Table: username, role, ACL tier, monthly cap, this-month tokens, last seen. Inline edit (HTMX). Add / disable user. |
| `/admin/usage` | Token usage | Pivot: rows = users, cols = months, cells = tokens + ¥. Sortable. CSV export. Drill-down per user → daily breakdown chart. |
| `/admin/docs` | Document library | Searchable table of `docs`: source, dept, doc_type, version, ACL, no-LLM toggle, chunks count, embed status, uploaded_by. Bulk actions: re-embed, set ACL, delete. |
| `/admin/upload` | Bulk upload | Drag-drop multi-file (HTMX `hx-encoding="multipart/form-data"`); progress per file; auto-classify; assign metadata in form. |
| `/admin/ocr` | OCR queue | Table of `ocr_jobs` w/ status (pending/claimed/done/failed). Retry failed. Live status via HTMX polling (5s). |
| `/admin/eval` | Evaluation | List of golden Q/A pairs; "run eval" button → executes against current pipeline; results table (correct / partial / wrong) + diff vs last run. |
| `/admin/settings` | System settings | Price tables (DeepSeek + DashScope per-token rates), default cap, prompt templates (editable), feature flags. |

### 8.2.5 Pages & routes

| Route | Method | Purpose |
|---|---|---|
| `/login`, `/logout` | GET, POST | Auth |
| `/` | GET | Empty new-chat view |
| `/c/{session_id}` | GET | Render session w/ history |
| `/c/{session_id}/stream` | GET (SSE) | Stream assistant reply |
| `/sessions` | GET, POST | Sidebar list / create |
| `/sessions/{id}` | PATCH, DELETE | Rename / delete |
| `/messages/{id}/rating` | POST | 👍/👎 |
| `/docs/{id}/view` | GET | PDF.js viewer or download |
| `/admin/*` | GET / POST | Admin pages above |

### 8.2.6 Accessibility & i18n

- All UI strings in zh-CN; design for future EN via Jinja `{% trans %}` (Babel).
- Keyboard: `Ctrl/Cmd+K` opens session search; `Ctrl/Cmd+N` new chat; arrow keys nav sidebar.
- ARIA labels on all icon buttons; focus rings preserved (Tailwind `focus-visible:`).
- Honor `prefers-reduced-motion`.

## 9. Security (small-team appropriate)

- HTTPS via Caddy (auto-cert).
- Username/password login; session cookie.
- 3 ACL tiers: `public` / `internal` / `restricted` — set per doc on upload.
- DeepSeek API call sends chunk text off-prem → admin can mark docs "no-LLM" (retrieval only, no generation). Confirm w/ leadership which classes (HR, finance, supplier contracts) are restricted.
- Daily `pg_dump` (compressed) + originals rsync to backup target. Test restore monthly.

## 10. Open Decisions

- [ ] DashScope model + dim: `text-embedding-v3` @ 1024 (default plan, mature) vs `text-embedding-v4` @ 2048 (newer, larger vectors → more storage + cost). Decide before first batch embed; switching later requires full re-embed.
- [ ] Query at retrieval time also goes through DashScope embedding — confirm latency budget is OK (1 extra HTTPS hop per query).
- [ ] Reranker in P0 or P1? (bge-reranker on VPS CPU vs DashScope rerank API.)
- [ ] Which doc classes are "no-LLM" (retrieval-only)?
- [ ] Backup target — second VPS, NAS, or cloud bucket.
- [ ] Default monthly token cap per user (or off entirely)? Price tables (DeepSeek + DashScope) — config file vs DB.

## 11. Evaluation

Small scale → keep it simple:
- 30–50 zh Q&A pairs total across departments (one expert per dept contributes 10).
- Manual scoring: answer correct / partial / wrong + citations valid y/n.
- Thumbs up/down in UI.
- Re-run eval set after any prompt or retrieval change.

No RAGAS / Langfuse infra unless needed later.

## 12. Roadmap

| Phase | Time | Deliverable |
|---|---|---|
| **P0 — Spike** | 1 week | 100 sample docs on local laptop; FastAPI + SQLite + DeepSeek; manual OCR; prove zh-CN pipeline |
| **P1 — MVP** | 2–3 weeks | VPS deploy; OCR runner on GPU box; real corpus subset (~1k docs); 5 pilot users; chat UI w/ sidebar + multi-session + streaming |
| **P2 — Rollout** | +2 weeks | Full corpus; all 20 users; auth + ACL + backups; admin dashboard (users/usage/docs/ocr); eval set passing |
| **P3 — Polish** | as needed | Reranker tuning, query rewrite, glossary, dark mode polish, mobile QA, charts on overview |

No 12+ week multi-team plan. One developer can ship P0–P2.

## 13. Risks

| Risk | Mitigation |
|---|---|
| GPU box offline → no OCR | Queue jobs on VPS, retry; ingestion of native PDFs / Office docs unaffected |
| DashScope API outage → no embed / no query | Cache last query embeddings briefly; fail-fast w/ clear error; consider local BGE-M3 fallback later if uptime issue |
| Embedding cost growth (hosted, per-token) | Log every call in `embed_log`; monthly cost report; switch to 1024-dim or self-host if budget pressure |
| VPS disk fills (PDFs heavy + Postgres) | Monitor disk; archive originals to NAS once embedded; vacuum + reindex schedule |
| pgvector slow at scale | HNSW (not IVFFlat); tune `ef_search`; partition `chunks` by year if >1M rows |
| zh-CN OCR poor on scanned tables | Per-doc manual review for high-value docs; flag low-confidence chunks in UI |
| Confidential leakage to DeepSeek | "no-LLM" flag per doc class |
| Stale SOPs cited | Show effective date + version in citations |
| Single VPS = SPOF | Daily backup; doc the restore procedure; 20 users tolerate brief outage |

## 14. Repo Layout

```
LIWANG/
├── PLAN.md
├── app/                       # FastAPI
│   ├── routes/
│   │   ├── chat.py            # /, /c/{id}, /c/{id}/stream
│   │   ├── sessions.py        # /sessions CRUD
│   │   ├── docs.py            # /docs/{id}/view
│   │   ├── auth.py            # /login /logout
│   │   ├── admin.py           # /admin/*
│   │   └── ocr_jobs.py        # /ocr-jobs/*
│   ├── ingest.py              # upload + parse + chunk + embed + index
│   ├── retrieve.py            # hybrid search + rerank
│   ├── generate.py            # DeepSeek call + prompt + SSE
│   ├── llm/                   # deepseek client, prompt templates
│   ├── embed/                 # DashScope wrapper, embed_log writer
│   └── templates/             # Jinja2 + HTMX
│       ├── _layout.html       # top bar + sidebar shell
│       ├── _sidebar.html      # session list partial
│       ├── chat.html          # main chat column
│       ├── _message.html      # message partial (SSE swap target)
│       ├── _citations.html    # citation drawer partial
│       └── admin/
│           ├── overview.html
│           ├── users.html
│           ├── usage.html
│           ├── docs.html
│           ├── upload.html
│           ├── ocr.html
│           ├── eval.html
│           └── settings.html
├── app/static/                # tailwind-built css, htmx + alpine + chart.js (vendored), pdfjs
├── ocr_runner/                # standalone — runs on GPU box
│   ├── runner.py              # poll loop
│   └── pipeline.py            # PaddleOCR + MinerU
├── eval/                      # 30–50 Q&A pairs + scoring script
├── migrations/                # alembic — users, sessions, docs, chunks, ocr_jobs, query_log, embed_log
├── data/                      # gitignored: originals/, ocr/
├── scripts/                   # backup.sh, import_folder.py, build_css.sh (tailwind purge)
├── tailwind.config.js         # content globs → templates/**/*.html
└── deploy/                    # Caddyfile, systemd unit, docker-compose (optional)
```

## 15. Next Actions

1. Get DeepSeek + DashScope API keys; confirm rate limits + per-token pricing for both.
2. Get sample corpus (~100 docs).
3. Pick GPU box (existing hardware?) and check PaddleOCR/MinerU run there.
4. Confirm DashScope model + dim choice (`text-embedding-v3` @ 1024 default; v4 if higher dim wanted).
5. P0 spike on laptop: Postgres + pgvector + zhparser in Docker; LlamaIndex `DashScopeEmbedding` for embed; DeepSeek for chat; prove hybrid query end-to-end before touching VPS.

## 16a. Embedding Wiring (LlamaIndex)

```python
# settings.py — initialised once, reused for ingest + query
import os
from llama_index.embeddings.dashscope import (
    DashScopeEmbedding,
    DashScopeTextEmbeddingModels,
)
from llama_index.core import Settings

EMBED_DIM = 1024  # text-embedding-v3 default/max

embed_model = DashScopeEmbedding(
    model_name=DashScopeTextEmbeddingModels.TEXT_EMBEDDING_V3,
    api_key=os.environ["DASHSCOPE_API_KEY"],
    embed_batch_size=10,  # DashScope v3 per-request batch ceiling
)
Settings.embed_model = embed_model
```

```python
# ingest.py — embed chunks, persist to pgvector
texts = [c.content for c in chunks]
vectors = embed_model.get_text_embedding_batch(texts, show_progress=False)
# usage = embed_model.last_token_count  (track via callback if SDK exposes)
# bulk INSERT into chunks(embedding) + INSERT embed_log row
```

```python
# retrieve.py — embed the user query the same way
qvec = embed_model.get_query_embedding(user_query)
# SQL: SELECT ... ORDER BY embedding <=> %s::vector LIMIT 20
```

Same `embed_model` instance for ingest and query → guaranteed dimension + model parity. If switching dims/model later, requires full re-embed → bump `EMBED_DIM` and run a migration.

## 16. Initial Schema Sketch

```sql
CREATE EXTENSION vector;
CREATE EXTENSION zhparser;  -- or pg_jieba

CREATE TABLE users (
  id serial PRIMARY KEY,
  username text UNIQUE NOT NULL,
  password_hash text NOT NULL,
  role text NOT NULL,                       -- admin | user
  acl_max text NOT NULL,                    -- public | internal | restricted
  monthly_token_cap bigint,                 -- NULL = unlimited
  created_at timestamptz DEFAULT now()
);

CREATE TABLE docs (
  id uuid PRIMARY KEY,
  source text NOT NULL,          -- path or URL
  hash text UNIQUE NOT NULL,
  mime text, dept text, doc_type text,
  version text, effective_date date,
  acl text NOT NULL,             -- public | internal | restricted
  no_llm boolean DEFAULT false,
  uploaded_by int REFERENCES users(id),
  uploaded_at timestamptz DEFAULT now()
);

CREATE TABLE chunks (
  id bigserial PRIMARY KEY,
  doc_id uuid REFERENCES docs(id) ON DELETE CASCADE,
  ord int NOT NULL,
  content text NOT NULL,
  heading_path text,
  ocr_confidence real,
  embedding vector(1024),                   -- DashScope text-embedding-v3 (1024 dim); migrate to vector(2048) if switching to text-embedding-v4
  tsv tsvector
);
CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON chunks USING gin (tsv);
CREATE INDEX ON chunks (doc_id);

CREATE TABLE ocr_jobs (
  id bigserial PRIMARY KEY,
  doc_id uuid REFERENCES docs(id),
  status text NOT NULL,          -- pending | claimed | done | failed
  claimed_at timestamptz, claimed_by text,
  attempts int DEFAULT 0,
  error text
);

CREATE TABLE sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id int REFERENCES users(id) ON DELETE CASCADE,
  title text NOT NULL DEFAULT '新对话',
  archived boolean DEFAULT false,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);
CREATE INDEX ON sessions (user_id, updated_at DESC);

CREATE TABLE query_log (
  id bigserial PRIMARY KEY,
  session_id uuid REFERENCES sessions(id) ON DELETE CASCADE,
  user_id int REFERENCES users(id),
  query text,
  retrieved jsonb,                          -- chunk ids + scores
  answer text,
  model text NOT NULL,                      -- e.g. deepseek-chat, deepseek-reasoner
  prompt_tokens int NOT NULL DEFAULT 0,
  completion_tokens int NOT NULL DEFAULT 0,
  cached_tokens int NOT NULL DEFAULT 0,     -- DeepSeek context-cache hits
  cost_cny numeric(10,4) NOT NULL DEFAULT 0,
  rating smallint,                          -- -1, 0, 1
  latency_ms int,
  created_at timestamptz DEFAULT now()
);
CREATE INDEX ON query_log (user_id, created_at);
CREATE INDEX ON query_log (session_id, created_at);

CREATE TABLE embed_log (
  id bigserial PRIMARY KEY,
  doc_id uuid REFERENCES docs(id),
  provider text NOT NULL,                   -- dashscope | local | siliconflow
  model text NOT NULL DEFAULT 'text-embedding-v3',
  tokens int NOT NULL DEFAULT 0,
  cost_cny numeric(10,4) NOT NULL DEFAULT 0,
  created_at timestamptz DEFAULT now()
);

-- Monthly aggregate, refreshed nightly
CREATE MATERIALIZED VIEW usage_monthly AS
SELECT
  user_id,
  date_trunc('month', created_at) AS month,
  count(*)                       AS queries,
  sum(prompt_tokens)             AS prompt_tokens,
  sum(completion_tokens)         AS completion_tokens,
  sum(cached_tokens)             AS cached_tokens,
  sum(prompt_tokens + completion_tokens) AS total_tokens,
  sum(cost_cny)                  AS cost_cny
FROM query_log
GROUP BY user_id, date_trunc('month', created_at);
CREATE UNIQUE INDEX ON usage_monthly (user_id, month);
```
