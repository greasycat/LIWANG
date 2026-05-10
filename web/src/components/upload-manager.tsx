"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { apiClient } from "@/lib/api";
import { formatBytes, formatDateTime } from "@/lib/format";
import type { UploadTable, Upload as UploadItem } from "@/lib/types";

const TAB_KEYS = [
  "all",
  "queued",
  "uploading",
  "parsing",
  "embedding",
  "done",
  "failed",
] as const;

const DEPTS = ["R&D", "QA", "生产", "供应链", "HR", "采购"];
const DOC_TYPES = ["SOP", "BOM", "规格", "手册", "审核", "工艺", "合同", "其他"];

function statusBadge(s: string, label: string) {
  if (s === "done") return { label, cls: "badge-success" };
  if (s === "failed") return { label, cls: "badge-error" };
  if (["uploading", "parsing", "embedding"].includes(s))
    return { label, cls: "badge-info" };
  return { label, cls: "badge-ghost" };
}

export function UploadManager({ initial }: { initial: UploadTable }) {
  const [data, setData] = useState(initial);
  const [filter, setFilter] = useState(initial.active_filter);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement | null>(null);

  useEffect(() => setData(initial), [initial]);

  const hasActive = useMemo(
    () =>
      data.items.some((i) =>
        ["uploading", "parsing", "embedding"].includes(i.status),
      ),
    [data.items],
  );

  // Auto-refresh while jobs in flight.
  useEffect(() => {
    if (!hasActive) return;
    const t = setInterval(async () => {
      try {
        const path =
          filter && filter !== "all"
            ? `/admin/upload?status=${filter}`
            : "/admin/upload";
        const fresh = await apiClient<UploadTable>(path);
        setData(fresh);
      } catch {
        /* noop */
      }
    }, 2000);
    return () => clearInterval(t);
  }, [hasActive, filter]);

  // Prune selection when items disappear.
  useEffect(() => {
    const live = new Set(data.items.map((i) => i.id));
    setSelected((prev) => {
      const next = new Set<string>();
      for (const id of prev) if (live.has(id)) next.add(id);
      return next;
    });
  }, [data.items]);

  async function reload(nextFilter: string = filter) {
    const path =
      nextFilter && nextFilter !== "all"
        ? `/admin/upload?status=${nextFilter}`
        : "/admin/upload";
    const fresh = await apiClient<UploadTable>(path);
    setData(fresh);
    setFilter(nextFilter);
  }

  async function uploadFiles(fileList: FileList | File[]) {
    const files = Array.from(fileList);
    if (!files.length) return;
    setUploading(true);
    try {
      const fd = new FormData();
      for (const f of files) fd.append("files", f);
      const res = await fetch("/api/admin/upload/intake", {
        method: "POST",
        body: fd,
        credentials: "same-origin",
      });
      if (res.ok) {
        const fresh = (await res.json()) as UploadTable;
        setData(fresh);
        setFilter(fresh.active_filter);
      }
    } finally {
      setUploading(false);
    }
  }

  async function bulk(action: string, value?: string) {
    if (selected.size === 0 && action !== "delete") return;
    if (action === "delete") {
      if (selected.size === 0) return;
      if (!confirm(`删除选中的 ${selected.size} 项?`)) return;
    }
    const fresh = await apiClient<UploadTable>("/admin/upload/bulk", {
      method: "POST",
      body: JSON.stringify({
        action,
        ids: Array.from(selected),
        ...(value !== undefined ? { value } : {}),
      }),
    });
    setData(fresh);
    if (action === "delete") setSelected(new Set());
  }

  async function startOne(id: string) {
    await apiClient<UploadItem>(`/admin/upload/${id}/start`, {
      method: "POST",
    });
    await reload();
  }

  async function deleteOne(id: string) {
    if (!confirm("删除此项?")) return;
    const fresh = await apiClient<UploadTable>(`/admin/upload/${id}`, {
      method: "DELETE",
    });
    setData(fresh);
  }

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll(on: boolean) {
    if (on) setSelected(new Set(data.items.map((i) => i.id)));
    else setSelected(new Set());
  }

  const counts = data.counts;

  return (
    <div>
      {/* drop zone */}
      <div
        className={`mb-4 card border-2 border-dashed transition-colors bg-base-100 ${dragging ? "border-primary bg-primary/5" : "border-base-300"}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setDragging(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (e.dataTransfer?.files) void uploadFiles(e.dataTransfer.files);
        }}
      >
        <div className="card-body py-5 px-6 flex-row items-center gap-5">
          <div className="text-3xl">📤</div>
          <div className="flex-1">
            <div className="font-medium text-sm">拖拽文件到此处，或</div>
            <div className="text-xs opacity-60 mt-0.5">
              支持 PDF / Word / Excel / PPT / HTML · 上传后会进入下方暂存区，可在提交前编辑元数据
            </div>
          </div>
          <button
            type="button"
            onClick={() => fileInput.current?.click()}
            className="btn btn-primary btn-sm gap-2"
          >
            选择文件
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
          {uploading && (
            <div className="flex items-center gap-2 text-xs opacity-70">
              <span className="loading loading-spinner loading-xs" />
              <span>上传中…</span>
            </div>
          )}
        </div>
      </div>

      {/* filter tabs */}
      <div role="tablist" className="tabs tabs-bordered mb-3">
        {TAB_KEYS.map((k) => {
          const label =
            k === "all" ? "全部" : data.status_labels[k] || k;
          const n = counts[k] || 0;
          const active = filter === k || (k === "all" && filter === "all");
          return (
            <button
              key={k}
              role="tab"
              type="button"
              onClick={() => reload(k)}
              className={`tab gap-1.5 ${active ? "tab-active text-primary" : ""}`}
            >
              <span>{label}</span>
              {n > 0 && (
                <span
                  className={`badge badge-sm ${k === "failed" ? "badge-error" : ["uploading", "parsing", "embedding"].includes(k) ? "badge-info" : "badge-ghost"}`}
                >
                  {n}
                </span>
              )}
            </button>
          );
        })}
        <div className="ml-auto text-xs opacity-60 self-center">
          {counts.active > 0 && (
            <span className="flex items-center gap-1.5">
              <span className="loading loading-ring loading-xs" />
              <span>{counts.active} 个进行中</span>
            </span>
          )}
        </div>
      </div>

      {/* bulk actions */}
      {selected.size > 0 && (
        <div className="sticky top-2 z-20 mb-3 rounded-xl bg-primary text-primary-content shadow-lg">
          <div className="px-4 py-2.5 flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">
              已选择 <span className="font-mono">{selected.size}</span> 项
            </span>
            <span className="opacity-30">|</span>

            <BulkPicker label="部门">
              {DEPTS.map((d) => (
                <li key={d}>
                  <button onClick={() => bulk("set_dept", d)}>{d}</button>
                </li>
              ))}
            </BulkPicker>
            <BulkPicker label="类型">
              {DOC_TYPES.map((t) => (
                <li key={t}>
                  <button onClick={() => bulk("set_type", t)}>{t}</button>
                </li>
              ))}
            </BulkPicker>
            <BulkPicker label="访问">
              <li>
                <button onClick={() => bulk("set_acl", "public")}>公开</button>
              </li>
              <li>
                <button onClick={() => bulk("set_acl", "internal")}>
                  内部
                </button>
              </li>
              <li>
                <button onClick={() => bulk("set_acl", "restricted")}>
                  受限
                </button>
              </li>
            </BulkPicker>
            <BulkPicker label="仅检索">
              <li>
                <button onClick={() => bulk("set_no_llm", "true")}>开启</button>
              </li>
              <li>
                <button onClick={() => bulk("set_no_llm", "false")}>关闭</button>
              </li>
            </BulkPicker>

            <span className="opacity-30">|</span>

            <button
              onClick={() => bulk("start")}
              className="btn btn-sm bg-primary-content/20 hover:bg-primary-content/30 border-0 text-primary-content"
            >
              ▶ 提交处理
            </button>

            <button
              onClick={() => bulk("delete")}
              className="btn btn-sm bg-error/80 hover:bg-error border-0 text-error-content ml-auto"
            >
              🗑 删除
            </button>

            <button
              onClick={() => setSelected(new Set())}
              className="btn btn-ghost btn-sm text-primary-content hover:bg-primary-content/10"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* table */}
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
                      data.items.length > 0 &&
                      selected.size === data.items.length
                    }
                    ref={(el) => {
                      if (el)
                        el.indeterminate =
                          selected.size > 0 &&
                          selected.size < data.items.length;
                    }}
                    onChange={(e) => selectAll(e.target.checked)}
                  />
                </th>
                <th>文件</th>
                <th>部门</th>
                <th>类型</th>
                <th>版本</th>
                <th>访问</th>
                <th className="text-center">仅检索</th>
                <th className="text-right">大小</th>
                <th>状态</th>
                <th>上传时间</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((it) => {
                const status = statusBadge(
                  it.status,
                  data.status_labels[it.status] || it.status,
                );
                return (
                  <tr key={it.id} className="hover">
                    <td>
                      <input
                        type="checkbox"
                        className="checkbox checkbox-xs"
                        checked={selected.has(it.id)}
                        onChange={() => toggle(it.id)}
                      />
                    </td>
                    <td>
                      <div className="flex items-center gap-2">
                        <span className="text-base">📎</span>
                        <span className="text-sm">{it.filename}</span>
                      </div>
                    </td>
                    <td className="text-sm opacity-80">{it.dept}</td>
                    <td>
                      <span className="badge badge-ghost badge-sm">
                        {it.doc_type}
                      </span>
                    </td>
                    <td className="font-mono text-xs">{it.version}</td>
                    <td>
                      <span
                        className={`badge badge-sm ${it.acl === "restricted" ? "badge-error" : it.acl === "internal" ? "badge-warning" : "badge-success"}`}
                      >
                        {it.acl === "restricted"
                          ? "受限"
                          : it.acl === "internal"
                            ? "内部"
                            : "公开"}
                      </span>
                    </td>
                    <td className="text-center">
                      <input
                        type="checkbox"
                        className="toggle toggle-xs toggle-primary"
                        checked={it.no_llm}
                        readOnly
                      />
                    </td>
                    <td className="text-right font-mono text-xs">
                      {formatBytes(it.size)}
                    </td>
                    <td>
                      <div className="flex flex-col gap-0.5">
                        <span className={`badge badge-sm ${status.cls}`}>
                          {status.label}
                        </span>
                        {it.error && (
                          <span
                            className="text-[10px] text-error truncate max-w-[160px]"
                            title={it.error}
                          >
                            {it.error}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="text-xs opacity-60">
                      {formatDateTime(it.created_at)}
                    </td>
                    <td>
                      <div className="dropdown dropdown-end">
                        <button tabIndex={0} className="btn btn-ghost btn-xs">
                          ⋯
                        </button>
                        <ul
                          tabIndex={0}
                          className="dropdown-content menu menu-xs bg-base-100 rounded-box z-50 w-32 p-1 shadow border border-base-300"
                        >
                          {(it.status === "queued" ||
                            it.status === "failed") && (
                            <li>
                              <button onClick={() => startOne(it.id)}>
                                提交处理
                              </button>
                            </li>
                          )}
                          <li>
                            <button
                              onClick={() => deleteOne(it.id)}
                              className="text-error"
                            >
                              删除
                            </button>
                          </li>
                        </ul>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {data.items.length === 0 && (
                <tr>
                  <td colSpan={11} className="text-center py-12 opacity-50 text-sm">
                    暂存区为空，拖拽文件以开始
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function BulkPicker({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="dropdown">
      <button
        tabIndex={0}
        className="btn btn-sm btn-ghost text-primary-content hover:bg-primary-content/10"
      >
        {label} ▾
      </button>
      <ul
        tabIndex={0}
        className="dropdown-content menu menu-sm bg-base-100 text-base-content rounded-box w-40 p-1 shadow-lg border border-base-300 mt-1 z-50"
      >
        {children}
      </ul>
    </div>
  );
}
