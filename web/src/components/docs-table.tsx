"use client";

import { useMemo, useState } from "react";

import { apiClient } from "@/lib/api";
import type { Acl, Doc } from "@/lib/types";

function aclMeta(a: string) {
  if (a === "restricted") return { label: "受限", cls: "badge-error" };
  if (a === "internal") return { label: "内部", cls: "badge-warning" };
  if (a === "private") return { label: "私有", cls: "badge-ghost" };
  return { label: "公开", cls: "badge-success" };
}

function statusBadge(s: string) {
  if (s === "done") return { label: "已索引", cls: "badge-success" };
  if (s === "embedding") return { label: "嵌入中", cls: "badge-info" };
  if (s === "failed") return { label: "失败", cls: "badge-error" };
  return { label: s, cls: "badge-ghost" };
}

export function DocsTable({ initial }: { initial: Doc[] }) {
  const [docs, setDocs] = useState(initial);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [aclTarget, setAclTarget] = useState<Doc | null>(null);
  const [search, setSearch] = useState("");

  const filtered = useMemo(
    () =>
      search
        ? docs.filter((d) =>
            d.source.toLowerCase().includes(search.toLowerCase()),
          )
        : docs,
    [docs, search],
  );

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll(on: boolean) {
    if (on) setSelected(new Set(filtered.map((d) => d.id)));
    else setSelected(new Set());
  }

  async function bulk(action: string, value?: string) {
    if (selected.size === 0) return;
    if (action === "delete") {
      if (!confirm(`删除选中的 ${selected.size} 个文档? 此操作不可撤销。`))
        return;
    }
    const fresh = await apiClient<Doc[]>("/admin/docs/bulk", {
      method: "POST",
      body: JSON.stringify({
        action,
        ids: Array.from(selected),
        ...(value !== undefined ? { value } : {}),
      }),
    });
    setDocs(fresh);
    if (action === "delete") setSelected(new Set());
  }

  async function setSingleAcl(doc: Doc, acl: Acl) {
    await apiClient<Doc>(`/admin/docs/${doc.id}/acl`, {
      method: "POST",
      body: JSON.stringify({ acl }),
    });
    const fresh = await apiClient<Doc[]>("/admin/docs");
    setDocs(fresh);
    setAclTarget(null);
  }

  return (
    <>
      <div className="flex items-center justify-between gap-2 mb-3">
        <label className="input input-sm input-bordered flex items-center gap-2">
          🔍
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索文档名…"
            className="grow w-48"
          />
        </label>
      </div>

      {selected.size > 0 && (
        <div className="sticky top-2 z-20 mb-3 rounded-xl bg-primary text-primary-content shadow-lg">
          <div className="px-4 py-2.5 flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">
              已选择 <span className="font-mono">{selected.size}</span> 个文档
            </span>
            <span className="opacity-30">|</span>

            <div className="dropdown">
              <button
                tabIndex={0}
                className="btn btn-sm btn-ghost text-primary-content hover:bg-primary-content/10"
              >
                访问级别 ▾
              </button>
              <ul
                tabIndex={0}
                className="dropdown-content menu menu-sm bg-base-100 text-base-content rounded-box w-32 p-1 shadow-lg border border-base-300 mt-1 z-50"
              >
                <li>
                  <button onClick={() => bulk("set_acl", "public")}>
                    <span className="badge badge-success badge-sm">公开</span>
                  </button>
                </li>
                <li>
                  <button onClick={() => bulk("set_acl", "internal")}>
                    <span className="badge badge-warning badge-sm">内部</span>
                  </button>
                </li>
                <li>
                  <button onClick={() => bulk("set_acl", "restricted")}>
                    <span className="badge badge-error badge-sm">受限</span>
                  </button>
                </li>
              </ul>
            </div>

            <div className="dropdown">
              <button
                tabIndex={0}
                className="btn btn-sm btn-ghost text-primary-content hover:bg-primary-content/10"
              >
                仅检索 ▾
              </button>
              <ul
                tabIndex={0}
                className="dropdown-content menu menu-sm bg-base-100 text-base-content rounded-box w-32 p-1 shadow-lg border border-base-300 mt-1 z-50"
              >
                <li>
                  <button onClick={() => bulk("set_no_llm", "true")}>开启</button>
                </li>
                <li>
                  <button onClick={() => bulk("set_no_llm", "false")}>关闭</button>
                </li>
              </ul>
            </div>

            <span className="opacity-30">|</span>

            <button
              onClick={() => bulk("reembed")}
              className="btn btn-sm bg-primary-content/20 hover:bg-primary-content/30 border-0 text-primary-content"
            >
              ↻ 重新嵌入
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
              title="取消选择"
            >
              ✕
            </button>
          </div>
        </div>
      )}

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
                      filtered.length > 0 && selected.size === filtered.length
                    }
                    ref={(el) => {
                      if (el)
                        el.indeterminate =
                          selected.size > 0 && selected.size < filtered.length;
                    }}
                    onChange={(e) => selectAll(e.target.checked)}
                  />
                </th>
                <th>名称</th>
                <th>部门</th>
                <th>类型</th>
                <th>版本</th>
                <th>生效日期</th>
                <th>访问</th>
                <th className="text-center">仅检索</th>
                <th className="text-right">分块</th>
                <th>状态</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((d) => {
                const acl = aclMeta(d.acl);
                const status = statusBadge(d.embed_status);
                return (
                  <tr key={d.id} className="hover">
                    <td>
                      <input
                        type="checkbox"
                        className="checkbox checkbox-xs"
                        checked={selected.has(d.id)}
                        onChange={() => toggle(d.id)}
                      />
                    </td>
                    <td>
                      <div className="flex items-center gap-2">
                        <span className="text-base">📄</span>
                        <span className="font-medium text-sm">{d.source}</span>
                      </div>
                    </td>
                    <td>
                      <span className="text-sm opacity-80">{d.dept}</span>
                    </td>
                    <td>
                      <span className="badge badge-ghost badge-sm">
                        {d.doc_type}
                      </span>
                    </td>
                    <td className="font-mono text-xs">{d.version}</td>
                    <td className="font-mono text-xs opacity-70">
                      {d.effective_date}
                    </td>
                    <td>
                      <button
                        onClick={() => setAclTarget(d)}
                        className={`badge badge-sm cursor-pointer hover:opacity-80 ${acl.cls}`}
                      >
                        {acl.label}
                      </button>
                    </td>
                    <td className="text-center">
                      <input
                        type="checkbox"
                        className="toggle toggle-xs toggle-primary"
                        checked={d.no_llm}
                        readOnly
                      />
                    </td>
                    <td className="text-right font-mono text-xs">{d.chunks}</td>
                    <td>
                      <span className={`badge badge-sm ${status.cls}`}>
                        {status.label}
                      </span>
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
                          <li>
                            <button onClick={() => setAclTarget(d)}>
                              修改访问
                            </button>
                          </li>
                        </ul>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={11} className="text-center py-12 opacity-50 text-sm">
                    没有匹配的文档
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {aclTarget && (
        <DocAclModal
          doc={aclTarget}
          onClose={() => setAclTarget(null)}
          onSave={(v) => setSingleAcl(aclTarget, v)}
        />
      )}
    </>
  );
}

function DocAclModal({
  doc,
  onClose,
  onSave,
}: {
  doc: Doc;
  onClose: () => void;
  onSave: (v: Acl) => Promise<void>;
}) {
  const initial: Acl = (doc.acl === "private" ? "internal" : doc.acl) as Acl;
  const [acl, setAcl] = useState<Acl>(initial);
  return (
    <div className="modal modal-open">
      <div className="modal-box max-w-md">
        <div className="flex items-center justify-between mb-1">
          <h3 className="font-semibold">访问权限</h3>
          <button onClick={onClose} className="btn btn-ghost btn-xs">
            ✕
          </button>
        </div>
        <p className="text-xs opacity-60 mb-4">{doc.source}</p>

        <div className="grid grid-cols-3 gap-1.5 mb-4">
          {(
            [
              ["public", "公开", "badge-success"],
              ["internal", "内部", "badge-warning"],
              ["restricted", "受限", "badge-error"],
            ] as [Acl, string, string][]
          ).map(([v, label, cls]) => (
            <label
              key={v}
              className={`cursor-pointer flex items-center justify-center gap-1.5 px-2 py-2 rounded-lg border-2 transition-colors text-sm ${acl === v ? "border-primary bg-primary/5" : "border-base-300 hover:bg-base-200"}`}
            >
              <input
                type="radio"
                className="hidden"
                checked={acl === v}
                onChange={() => setAcl(v)}
              />
              <span className={`badge badge-sm ${cls}`}>{label}</span>
            </label>
          ))}
        </div>

        <div className="modal-action">
          <button onClick={onClose} className="btn btn-ghost btn-sm">
            取消
          </button>
          <button
            onClick={() => onSave(acl)}
            className="btn btn-primary btn-sm"
          >
            保存
          </button>
        </div>
      </div>
      <div className="modal-backdrop" onClick={onClose} />
    </div>
  );
}
