"use client";

import Link from "next/link";
import { useState } from "react";

import { apiClient } from "@/lib/api";
import { formatBytes, formatInt } from "@/lib/format";
import type { Acl, AdminUserRow, User } from "@/lib/types";

function aclMeta(a: Acl) {
  if (a === "restricted") return { label: "受限", cls: "badge-error" };
  if (a === "internal") return { label: "内部", cls: "badge-warning" };
  return { label: "公开", cls: "badge-success" };
}

export function UsersTable({ initial }: { initial: AdminUserRow[] }) {
  const [rows, setRows] = useState(initial);
  const [editing, setEditing] = useState<AdminUserRow | null>(null);

  async function refresh() {
    const fresh = await apiClient<AdminUserRow[]>("/admin/users");
    setRows(fresh);
  }

  return (
    <>
      <div className="card bg-base-100 border border-base-300 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="table table-sm">
            <thead className="text-xs uppercase tracking-wider opacity-70 bg-base-200">
              <tr>
                <th>用户</th>
                <th>角色</th>
                <th>访问</th>
                <th className="text-right">本月 tokens</th>
                <th className="text-right">月度上限</th>
                <th className="text-right">已用存储</th>
                <th className="text-right">存储上限</th>
                <th className="w-44 text-right pr-4">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ user: u, month_tokens, storage_used }) => {
                const acl = aclMeta(u.acl_max);
                const tokenPct =
                  u.monthly_token_cap && u.monthly_token_cap > 0
                    ? (month_tokens / u.monthly_token_cap) * 100
                    : 0;
                const storagePct =
                  u.storage_quota_bytes > 0
                    ? (storage_used / u.storage_quota_bytes) * 100
                    : 0;
                return (
                  <tr key={u.id} className="hover">
                    <td>
                      <div className="flex items-center gap-2.5">
                        <div className="avatar placeholder">
                          <div className="bg-base-300 text-base-content w-7 rounded-full flex items-center justify-center">
                            <span className="text-xs">
                              {u.display_name.charAt(0)}
                            </span>
                          </div>
                        </div>
                        <div>
                          <div className="font-medium text-sm">
                            {u.display_name}
                          </div>
                          <div className="text-[11px] opacity-60 font-mono">
                            {u.username}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td>
                      {u.role === "admin" ? (
                        <span className="badge badge-primary badge-sm">
                          管理员
                        </span>
                      ) : (
                        <span className="badge badge-ghost badge-sm">用户</span>
                      )}
                    </td>
                    <td>
                      <button
                        onClick={() =>
                          setEditing({
                            user: u,
                            month_tokens,
                            storage_used,
                          })
                        }
                        className={`badge badge-sm cursor-pointer hover:opacity-80 ${acl.cls}`}
                      >
                        {acl.label}
                      </button>
                    </td>
                    <td className="text-right font-mono text-sm">
                      {formatInt(month_tokens)}
                    </td>
                    <td className="text-right">
                      {u.monthly_token_cap ? (
                        <>
                          <div className="flex items-center gap-1.5 justify-end">
                            <span
                              className={`font-mono text-xs ${tokenPct > 100 ? "text-error" : tokenPct > 80 ? "text-warning" : ""}`}
                            >
                              {Math.round(tokenPct)}%
                            </span>
                            <progress
                              className={`progress w-16 h-1.5 ${tokenPct > 80 ? "progress-warning" : "progress-primary"}`}
                              value={month_tokens}
                              max={u.monthly_token_cap}
                            />
                          </div>
                          <div className="text-[10px] opacity-60 font-mono mt-0.5">
                            {formatInt(u.monthly_token_cap)}
                          </div>
                        </>
                      ) : (
                        <span className="opacity-40 text-xs">无限制</span>
                      )}
                    </td>
                    <td className="text-right font-mono text-sm">
                      {formatBytes(storage_used)}
                    </td>
                    <td className="text-right">
                      <div className="flex items-center gap-1.5 justify-end">
                        <span
                          className={`font-mono text-xs ${storagePct > 100 ? "text-error" : storagePct > 80 ? "text-warning" : ""}`}
                        >
                          {Math.round(storagePct)}%
                        </span>
                        <progress
                          className={`progress w-16 h-1.5 ${storagePct > 80 ? "progress-warning" : "progress-primary"}`}
                          value={storage_used}
                          max={u.storage_quota_bytes}
                        />
                      </div>
                      <div className="text-[10px] opacity-60 font-mono mt-0.5">
                        {formatBytes(u.storage_quota_bytes)}
                      </div>
                    </td>
                    <td className="pr-4">
                      <div className="flex justify-end items-center gap-1 whitespace-nowrap">
                        <Link
                          href={`/admin/files/${u.id}`}
                          className="btn btn-ghost btn-xs gap-1"
                          title="浏览此用户的个人文件"
                        >
                          📁 文件
                        </Link>
                        <button
                          onClick={() =>
                            setEditing({
                              user: u,
                              month_tokens,
                              storage_used,
                            })
                          }
                          className="btn btn-ghost btn-xs"
                        >
                          编辑配额
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {editing && (
        <UserEditModal
          row={editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await refresh();
          }}
        />
      )}
    </>
  );
}

function UserEditModal({
  row,
  onClose,
  onSaved,
}: {
  row: AdminUserRow;
  onClose: () => void;
  onSaved: () => void;
}) {
  const u = row.user;
  const [acl, setAcl] = useState<Acl>(u.acl_max);
  const [tokenCap, setTokenCap] = useState<string>(
    u.monthly_token_cap ? String(u.monthly_token_cap) : "",
  );
  const [storageMb, setStorageMb] = useState<string>(
    String(Math.floor(u.storage_quota_bytes / 1024 / 1024)),
  );

  return (
    <div className="modal modal-open">
      <div className="modal-box max-w-md">
        <div className="flex items-center justify-between mb-1">
          <h3 className="font-semibold">编辑用户配额</h3>
          <button onClick={onClose} className="btn btn-ghost btn-xs">
            ✕
          </button>
        </div>
        <p className="text-xs opacity-60 mb-4">
          {u.display_name} ·{" "}
          <span className="font-mono">{u.username}</span>
        </p>

        <form
          onSubmit={async (e) => {
            e.preventDefault();
            await apiClient<User>(`/admin/users/${u.id}/quota`, {
              method: "PATCH",
              body: JSON.stringify({
                acl_max: acl,
                monthly_token_cap: tokenCap ? parseInt(tokenCap, 10) : null,
                storage_quota_mb: storageMb
                  ? Math.max(1, parseInt(storageMb, 10))
                  : null,
              }),
            });
            onSaved();
          }}
          className="space-y-3"
        >
          <div>
            <div className="label py-1">
              <span className="label-text text-xs">最高访问级别</span>
              <span className="label-text-alt text-[10px] opacity-60">
                决定能检索的文档
              </span>
            </div>
            <div className="grid grid-cols-3 gap-1.5">
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
          </div>

          <label className="form-control">
            <div className="label py-1">
              <span className="label-text text-xs">月度 token 上限</span>
              <span className="label-text-alt text-[10px] opacity-60">
                留空 = 无限制
              </span>
            </div>
            <input
              type="number"
              min={0}
              step={1000}
              value={tokenCap}
              onChange={(e) => setTokenCap(e.target.value)}
              className="input input-bordered input-sm"
            />
          </label>

          <label className="form-control">
            <div className="label py-1">
              <span className="label-text text-xs">
                个人空间存储上限 (MB)
              </span>
              <span className="label-text-alt text-[10px] opacity-60">
                已用 {formatBytes(row.storage_used)}
              </span>
            </div>
            <input
              type="number"
              min={1}
              step={50}
              value={storageMb}
              onChange={(e) => setStorageMb(e.target.value)}
              className="input input-bordered input-sm"
            />
          </label>

          <div className="modal-action mt-4">
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={onClose}
            >
              取消
            </button>
            <button type="submit" className="btn btn-primary btn-sm">
              保存
            </button>
          </div>
        </form>
      </div>
      <div className="modal-backdrop" onClick={onClose} />
    </div>
  );
}
