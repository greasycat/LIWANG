"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  AclModal,
  FolderCreateModal,
  PreviewModal,
  RenameModal,
} from "@/components/files-modals";
import { apiClient } from "@/lib/api";
import { formatBytes, formatDateTime } from "@/lib/format";
import type { FilesListing, UserFile } from "@/lib/types";

interface Props {
  initial: FilesListing;
  apiBase: string; // e.g. "/files" or "/admin/files/3"
  linkBase: string; // e.g. "/files" or "/admin/files/3" — Next.js routes
  viewingAsAdmin: boolean;
}

const PREVIEWABLE_EXT = [".pdf", ".docx", ".txt", ".md", ".markdown"];
function isPreviewable(f: UserFile): boolean {
  if (f.is_folder) return false;
  const m = (f.mime || "").toLowerCase();
  const n = f.name.toLowerCase();
  return (
    m.startsWith("text/") ||
    m.includes("pdf") ||
    m.includes("wordprocessingml") ||
    PREVIEWABLE_EXT.some((e) => n.endsWith(e))
  );
}

function fileEmoji(f: UserFile): string {
  const m = (f.mime || "").toLowerCase();
  const n = f.name.toLowerCase();
  if (m.includes("pdf")) return "📄";
  if (m.includes("word") || m.includes("document")) return "📝";
  if (m.includes("sheet") || m.includes("excel")) return "📊";
  if (m.includes("presentation")) return "📑";
  if (m.includes("image")) return "🖼️";
  if (m.includes("markdown") || n.endsWith(".md")) return "📋";
  if (m.includes("text")) return "📃";
  return "📎";
}

function aclBadge(acl: string) {
  if (acl === "restricted") return { label: "受限", cls: "badge-error" };
  if (acl === "internal") return { label: "内部", cls: "badge-warning" };
  return { label: "公开", cls: "badge-success" };
}

export function FilesPage({ initial, apiBase, linkBase, viewingAsAdmin }: Props) {
  const [listing, setListing] = useState<FilesListing>(initial);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [quotaError, setQuotaError] = useState<string | null>(null);
  const [folderOpen, setFolderOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<UserFile | null>(null);
  const [aclTarget, setAclTarget] = useState<UserFile | null>(null);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  useEffect(() => setListing(initial), [initial]);

  // Prune selection when listing changes.
  useEffect(() => {
    const live = new Set(listing.items.map((f) => f.id));
    setSelected((prev) => {
      const next = new Set<string>();
      for (const id of prev) if (live.has(id)) next.add(id);
      return next;
    });
  }, [listing]);

  // Poll while any embed is in-flight.
  const hasRunning = useMemo(
    () =>
      listing.items.some(
        (f) => f.embed_status === "embedding" || f.embed_status === "pending",
      ),
    [listing],
  );
  useEffect(() => {
    if (!hasRunning) return;
    const t = setInterval(async () => {
      try {
        const fresh = await apiClient<FilesListing>(
          `${apiBase}${listing.parent_id ? `?parent_id=${listing.parent_id}` : ""}`,
        );
        setListing(fresh);
      } catch {
        /* ignore */
      }
    }, 3000);
    return () => clearInterval(t);
  }, [hasRunning, apiBase, listing.parent_id]);

  async function uploadFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList);
    if (!files.length) return;
    setUploading(true);
    setQuotaError(null);
    try {
      const fd = new FormData();
      for (const f of files) fd.append("files", f);
      if (listing.parent_id) fd.append("parent_id", listing.parent_id);
      const res = await fetch(`${apiBase}/upload`, {
        method: "POST",
        body: fd,
        credentials: "same-origin",
      });
      if (res.status === 413) {
        const j = await res.json();
        const d = j.detail ?? j;
        setQuotaError(
          `本次需 ${formatBytes(d.needed)}，剩余 ${formatBytes(d.remaining)} (上限 ${formatBytes(d.quota)})`,
        );
        setTimeout(() => setQuotaError(null), 8000);
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setListing((await res.json()) as FilesListing);
    } catch (e) {
      setQuotaError(e instanceof Error ? e.message : "上传失败");
    } finally {
      setUploading(false);
    }
  }

  async function createFolder(name: string) {
    const updated = await apiClient<FilesListing>(`${apiBase}/folder`, {
      method: "POST",
      body: JSON.stringify({ name, parent_id: listing.parent_id }),
    });
    setListing(updated);
  }

  async function deleteOne(file: UserFile) {
    const ok = confirm(
      file.is_folder ? `删除此文件夹及其所有内容?` : `删除「${file.name}」?`,
    );
    if (!ok) return;
    const updated = await apiClient<FilesListing>(`${apiBase}/${file.id}`, {
      method: "DELETE",
    });
    setListing(updated);
  }

  async function bulkDelete() {
    if (selected.size === 0) return;
    if (!confirm(`删除选中的 ${selected.size} 项? 文件夹会递归删除其内容。`))
      return;
    const updated = await apiClient<FilesListing>(`${apiBase}/bulk`, {
      method: "POST",
      body: JSON.stringify({ action: "delete", ids: Array.from(selected) }),
    });
    setListing(updated);
    setSelected(new Set());
  }

  async function embedOne(file: UserFile) {
    const updated = await apiClient<FilesListing>(
      `${apiBase}/${file.id}/embed`,
      { method: "POST" },
    );
    setListing(updated);
  }

  async function embedAll() {
    if (!confirm("嵌入所有未处理的文件? (PDF/DOCX/TXT/MD)")) return;
    const q = listing.parent_id ? `?parent_id=${listing.parent_id}` : "";
    const updated = await apiClient<FilesListing>(
      `${apiBase}/embed-all${q}`,
      { method: "POST" },
    );
    setListing(updated);
  }

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll(checked: boolean) {
    if (checked) {
      setSelected(new Set(listing.items.map((f) => f.id)));
    } else {
      setSelected(new Set());
    }
  }

  const pct = Math.min(100, listing.storage_pct);
  const upParent =
    listing.crumbs.length >= 2
      ? listing.crumbs[listing.crumbs.length - 2].id
      : null;
  const upHref = upParent
    ? `${linkBase}/folder/${upParent}`
    : linkBase;

  return (
    <main className="flex-1 overflow-hidden flex flex-col bg-base-200">
      {viewingAsAdmin && (
        <div className="bg-warning/15 border-b border-warning/30 px-5 py-2 flex items-center gap-3 text-sm">
          <span>
            管理员视图 · 正在浏览{" "}
            <span className="font-semibold">
              {listing.target_user.display_name}
            </span>{" "}
            (
            <span className="font-mono">{listing.target_user.username}</span>) 的个人文件
            — 所有操作都会影响该用户
          </span>
          <Link href="/admin/users" className="btn btn-ghost btn-xs ml-auto">
            返回用户管理
          </Link>
        </div>
      )}

      <header className="bg-base-100 border-b border-base-300 px-5 py-3 flex items-end justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="text-sm breadcrumbs py-0">
            <ul>
              <li>
                <Link href={linkBase} className="opacity-70 hover:text-primary">
                  {viewingAsAdmin
                    ? `${listing.target_user.display_name} 的文件`
                    : "我的文件"}
                </Link>
              </li>
              {listing.crumbs.map((c, i) => {
                const last = i === listing.crumbs.length - 1;
                return (
                  <li key={c.id}>
                    {last ? (
                      <span className="font-medium">{c.name}</span>
                    ) : (
                      <Link
                        href={`${linkBase}/folder/${c.id}`}
                        className="opacity-70 hover:text-primary"
                      >
                        {c.name}
                      </Link>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
          <div className="text-xs opacity-60 mt-0.5">
            {selected.size > 0 ? (
              <span>{selected.size} 项已选</span>
            ) : (
              <span>
                {listing.items.length} 项 · 配额已用{" "}
                {formatBytes(listing.storage_used)} /{" "}
                {formatBytes(listing.storage_quota)}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={embedAll}
            className="btn btn-sm btn-ghost gap-1.5"
            title="为所有未嵌入的文件创建索引"
          >
            ⚡ 嵌入未处理
          </button>
          <button
            type="button"
            onClick={() => setFolderOpen(true)}
            className="btn btn-sm btn-ghost gap-1.5"
          >
            📁+ 新建文件夹
          </button>
          <button
            type="button"
            onClick={() => fileInput.current?.click()}
            className="btn btn-primary btn-sm gap-1.5"
          >
            ⬆ 上传文件
          </button>
          <input
            ref={fileInput}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => {
              if (e.target.files) void uploadFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </div>
      </header>

      <div className="px-5 py-2 bg-base-100 border-b border-base-300 flex items-center gap-3">
        <div className="flex-1 max-w-md flex items-center gap-2">
          <progress
            className={`progress h-1.5 ${pct > 95 ? "progress-error" : pct > 80 ? "progress-warning" : "progress-primary"}`}
            value={listing.storage_used}
            max={listing.storage_quota}
          />
          <span className="text-xs font-mono whitespace-nowrap opacity-70">
            {formatBytes(listing.storage_used)} /{" "}
            {formatBytes(listing.storage_quota)}
          </span>
        </div>
        {viewingAsAdmin ? (
          <Link href="/admin/users" className="btn btn-ghost btn-xs">
            调整配额 →
          </Link>
        ) : (
          pct > 90 && (
            <div className="text-xs text-warning">
              配额不足，请联系管理员或清理旧文件
            </div>
          )
        )}
      </div>

      {selected.size > 0 && (
        <div className="bg-primary text-primary-content px-5 py-2 flex items-center gap-2">
          <span className="text-sm font-medium">
            已选择 <span className="font-mono">{selected.size}</span> 项
          </span>
          <span className="opacity-30">|</span>
          <button
            onClick={bulkDelete}
            className="btn btn-ghost btn-sm text-primary-content hover:bg-primary-content/10 gap-1"
          >
            🗑 删除
          </button>
          <button
            onClick={() => setSelected(new Set())}
            className="btn btn-ghost btn-sm text-primary-content hover:bg-primary-content/10 ml-auto"
          >
            取消选择 ✕
          </button>
        </div>
      )}

      <div
        className="flex-1 overflow-y-auto relative"
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={(e) => {
          if (e.target === e.currentTarget) setDragging(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (e.dataTransfer?.files) void uploadFiles(e.dataTransfer.files);
        }}
      >
        {dragging && (
          <div className="absolute inset-0 z-30 bg-primary/10 border-4 border-dashed border-primary m-3 rounded-2xl flex items-center justify-center pointer-events-none">
            <div className="text-center">
              <div className="text-5xl mb-2">📥</div>
              <div className="text-lg font-semibold text-primary">
                释放以上传到当前文件夹
              </div>
            </div>
          </div>
        )}

        <div className="px-5 py-4">
          <div className="card bg-base-100 border border-base-300 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="table table-sm">
                <thead className="text-xs uppercase tracking-wider opacity-70 bg-base-200">
                  <tr>
                    <th className="w-8">
                      <input
                        type="checkbox"
                        className="checkbox checkbox-xs"
                        checked={
                          listing.items.length > 0 &&
                          selected.size === listing.items.length
                        }
                        ref={(el) => {
                          if (el)
                            el.indeterminate =
                              selected.size > 0 &&
                              selected.size < listing.items.length;
                        }}
                        onChange={(e) => selectAll(e.target.checked)}
                      />
                    </th>
                    <th>名称</th>
                    <th>访问</th>
                    <th>嵌入状态</th>
                    <th className="text-right">大小</th>
                    <th>修改时间</th>
                    <th className="w-24"></th>
                  </tr>
                </thead>
                <tbody>
                  {listing.parent_id && (
                    <tr className="hover">
                      <td></td>
                      <td colSpan={6}>
                        <Link
                          href={upHref}
                          className="link link-hover text-sm flex items-center gap-2 opacity-70"
                        >
                          ← 返回上级
                        </Link>
                      </td>
                    </tr>
                  )}

                  {listing.items.map((f) => {
                    const previewable = isPreviewable(f);
                    const acl = aclBadge(f.acl);
                    return (
                      <tr key={f.id} className="hover">
                        <td>
                          <input
                            type="checkbox"
                            className="checkbox checkbox-xs"
                            checked={selected.has(f.id)}
                            onChange={() => toggle(f.id)}
                          />
                        </td>
                        <td>
                          {f.is_folder ? (
                            <Link
                              href={`${linkBase}/folder/${f.id}`}
                              className="flex items-center gap-2 link link-hover"
                            >
                              <span className="text-base">📁</span>
                              <span className="font-medium text-sm">
                                {f.name}
                              </span>
                            </Link>
                          ) : (
                            <div className="flex items-center gap-2">
                              <span className="text-base">{fileEmoji(f)}</span>
                              {previewable ? (
                                <button
                                  type="button"
                                  className="text-sm link link-hover text-left bg-transparent border-0 p-0"
                                  onClick={() => setPreviewId(f.id)}
                                  title="预览"
                                >
                                  {f.name}
                                </button>
                              ) : (
                                <span className="text-sm">{f.name}</span>
                              )}
                            </div>
                          )}
                        </td>
                        <td>
                          <button
                            onClick={() => setAclTarget(f)}
                            className={`badge badge-sm cursor-pointer hover:opacity-80 ${acl.cls}`}
                            title="点击修改访问级别"
                          >
                            {acl.label}
                          </button>
                        </td>
                        <td>
                          {f.is_folder || !previewable || !f.file_path ? (
                            <span className="text-xs opacity-30">—</span>
                          ) : (
                            <EmbedBadge status={f.embed_status} />
                          )}
                        </td>
                        <td className="text-right font-mono text-xs opacity-70">
                          {f.is_folder ? "—" : formatBytes(f.size)}
                        </td>
                        <td className="text-xs opacity-60">
                          {formatDateTime(f.created_at)}
                        </td>
                        <td>
                          <div className="flex justify-end">
                            <div className="dropdown dropdown-end">
                              <button
                                tabIndex={0}
                                className="btn btn-ghost btn-xs"
                              >
                                ⋯
                              </button>
                              <ul
                                tabIndex={0}
                                className="dropdown-content menu menu-xs bg-base-100 rounded-box z-50 w-32 p-1 shadow border border-base-300"
                              >
                                {!f.is_folder && previewable && (
                                  <>
                                    <li>
                                      <button onClick={() => setPreviewId(f.id)}>
                                        预览
                                      </button>
                                    </li>
                                    <li>
                                      <button
                                        onClick={() => embedOne(f)}
                                        disabled={
                                          f.embed_status === "embedding"
                                        }
                                      >
                                        {f.embed_status === "done"
                                          ? "重新嵌入"
                                          : f.embed_status === "embedding"
                                            ? "嵌入中…"
                                            : "嵌入"}
                                      </button>
                                    </li>
                                  </>
                                )}
                                {!f.is_folder && (
                                  <li>
                                    <a
                                      href={`${apiBase}/${f.id}/download`}
                                      download
                                    >
                                      下载
                                    </a>
                                  </li>
                                )}
                                <li>
                                  <button onClick={() => setRenameTarget(f)}>
                                    重命名
                                  </button>
                                </li>
                                <li>
                                  <button onClick={() => setAclTarget(f)}>
                                    修改访问
                                  </button>
                                </li>
                                <li>
                                  <button
                                    onClick={() => deleteOne(f)}
                                    className="text-error"
                                  >
                                    删除
                                  </button>
                                </li>
                              </ul>
                            </div>
                          </div>
                        </td>
                      </tr>
                    );
                  })}

                  {listing.items.length === 0 && (
                    <tr>
                      <td colSpan={7} className="text-center py-12">
                        <div className="text-4xl opacity-30">📂</div>
                        <div className="mt-2 text-sm opacity-50">
                          此文件夹为空
                        </div>
                        <div className="mt-1 text-xs opacity-40">
                          拖拽文件到此处上传
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {uploading && (
          <div className="fixed bottom-4 right-4 z-40">
            <div className="alert shadow-lg">
              <span className="loading loading-spinner loading-sm" />
              <span className="text-sm">上传中…</span>
            </div>
          </div>
        )}

        {quotaError && (
          <div className="fixed bottom-4 right-4 z-40 max-w-sm">
            <div className="alert alert-warning shadow-lg">
              <div>
                <div className="font-semibold text-sm">存储配额不足</div>
                <div className="text-xs mt-0.5">{quotaError}</div>
              </div>
              <button
                onClick={() => setQuotaError(null)}
                className="btn btn-sm btn-ghost"
              >
                关闭
              </button>
            </div>
          </div>
        )}
      </div>

      <FolderCreateModal
        open={folderOpen}
        onClose={() => setFolderOpen(false)}
        onCreate={createFolder}
      />
      <RenameModal
        file={renameTarget}
        apiBase={apiBase}
        onClose={() => setRenameTarget(null)}
        onSaved={setListing}
      />
      <AclModal
        file={aclTarget}
        apiBase={apiBase}
        onClose={() => setAclTarget(null)}
        onSaved={setListing}
      />
      <PreviewModal
        fileId={previewId}
        apiBase={apiBase}
        onClose={() => setPreviewId(null)}
      />
    </main>
  );
}

function EmbedBadge({ status }: { status: string | null }) {
  if (status === "done")
    return <span className="badge badge-success badge-sm">已嵌入</span>;
  if (status === "embedding")
    return (
      <span className="badge badge-info badge-sm gap-1">
        <span className="loading loading-spinner loading-xs" />
        嵌入中
      </span>
    );
  if (status === "pending")
    return <span className="badge badge-info badge-sm">待处理</span>;
  if (status === "failed")
    return <span className="badge badge-error badge-sm">失败</span>;
  return <span className="badge badge-ghost badge-sm">未嵌入</span>;
}
