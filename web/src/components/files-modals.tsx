"use client";

import { useEffect, useState } from "react";

import { ApiError, apiClient } from "@/lib/api";
import type { Acl, FilePreview, FilesListing, UserFile } from "@/lib/types";

export function FolderCreateModal({
  open,
  onClose,
  onCreate,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (name: string) => Promise<void>;
}) {
  const [name, setName] = useState("");
  if (!open) return null;
  return (
    <Modal onClose={onClose} title="新建文件夹">
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const v = name.trim();
          if (!v) return;
          await onCreate(v);
          setName("");
          onClose();
        }}
      >
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="文件夹名称"
          className="input input-bordered w-full"
        />
        <div className="modal-action">
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
            取消
          </button>
          <button type="submit" className="btn btn-primary btn-sm">
            创建
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function RenameModal({
  file,
  apiBase,
  onClose,
  onSaved,
}: {
  file: UserFile | null;
  apiBase: string;
  onClose: () => void;
  onSaved: (listing: FilesListing) => void;
}) {
  const [name, setName] = useState(file?.name || "");
  useEffect(() => setName(file?.name || ""), [file]);
  if (!file) return null;
  return (
    <Modal onClose={onClose} title={`重命名「${file.name}」`}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const updated = await apiClient<FilesListing>(
            `${apiBase}/${file.id}`,
            { method: "PATCH", body: JSON.stringify({ name }) },
          );
          onSaved(updated);
          onClose();
        }}
      >
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="input input-bordered w-full"
        />
        <div className="modal-action">
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
            取消
          </button>
          <button type="submit" className="btn btn-primary btn-sm">
            保存
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function AclModal({
  file,
  apiBase,
  onClose,
  onSaved,
}: {
  file: UserFile | null;
  apiBase: string;
  onClose: () => void;
  onSaved: (listing: FilesListing) => void;
}) {
  const [acl, setAcl] = useState<Acl>(file?.acl || "internal");
  const [recursive, setRecursive] = useState(false);
  useEffect(() => setAcl(file?.acl || "internal"), [file]);
  if (!file) return null;
  return (
    <Modal onClose={onClose} title={`访问权限 · ${file.name}`}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const updated = await apiClient<FilesListing>(
            `${apiBase}/${file.id}/acl`,
            {
              method: "POST",
              body: JSON.stringify({ acl, recursive }),
            },
          );
          onSaved(updated);
          onClose();
        }}
        className="space-y-3 text-sm"
      >
        <div className="form-control">
          <label className="label py-1 cursor-pointer justify-start gap-2">
            <input
              type="radio"
              name="acl"
              className="radio radio-sm"
              checked={acl === "public"}
              onChange={() => setAcl("public")}
            />
            <span>
              <span className="badge badge-success badge-sm mr-2">公开</span>
              所有人可见
            </span>
          </label>
          <label className="label py-1 cursor-pointer justify-start gap-2">
            <input
              type="radio"
              name="acl"
              className="radio radio-sm"
              checked={acl === "internal"}
              onChange={() => setAcl("internal")}
            />
            <span>
              <span className="badge badge-warning badge-sm mr-2">内部</span>
              内部员工可见
            </span>
          </label>
          <label className="label py-1 cursor-pointer justify-start gap-2">
            <input
              type="radio"
              name="acl"
              className="radio radio-sm"
              checked={acl === "restricted"}
              onChange={() => setAcl("restricted")}
            />
            <span>
              <span className="badge badge-error badge-sm mr-2">受限</span>
              仅授权角色
            </span>
          </label>
        </div>
        {file.is_folder && (
          <label className="label py-1 cursor-pointer justify-start gap-2">
            <input
              type="checkbox"
              className="checkbox checkbox-sm"
              checked={recursive}
              onChange={(e) => setRecursive(e.target.checked)}
            />
            <span className="text-xs">同时应用到此文件夹下所有子项</span>
          </label>
        )}
        <div className="modal-action">
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
            取消
          </button>
          <button type="submit" className="btn btn-primary btn-sm">
            保存
          </button>
        </div>
      </form>
    </Modal>
  );
}

export function PreviewModal({
  fileId,
  apiBase,
  onClose,
}: {
  fileId: string | null;
  apiBase: string;
  onClose: () => void;
}) {
  const [data, setData] = useState<FilePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!fileId) {
      setData(null);
      return;
    }
    setLoading(true);
    setError(null);
    apiClient<FilePreview>(`${apiBase}/${fileId}/preview`)
      .then(setData)
      .catch((e) => {
        if (e instanceof ApiError) setError(String(e.detail));
        else setError("加载失败");
      })
      .finally(() => setLoading(false));
  }, [fileId, apiBase]);

  if (!fileId) return null;

  return (
    <Modal onClose={onClose} title={data?.file.name || "文件预览"} wide>
      {loading && (
        <div className="opacity-50 text-sm">
          <span className="loading loading-dots loading-sm" /> 加载中…
        </div>
      )}
      {error && <div className="alert alert-error text-sm">{error}</div>}
      {data?.error && (
        <div className="alert alert-warning text-sm">{data.error}</div>
      )}
      {data?.kind === "pdf" && (
        <iframe
          src={data.raw_url}
          className="w-full h-[70vh] border-0"
          title={data.file.name}
        />
      )}
      {data?.body && (
        <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed max-h-[70vh] overflow-auto">
          {data.body}
        </pre>
      )}
      {data?.file.file_path && (
        <div className="modal-action">
          <a href={data.download_url} className="btn btn-sm btn-outline" download>
            下载原文件
          </a>
        </div>
      )}
    </Modal>
  );
}

function Modal({
  title,
  children,
  onClose,
  wide,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  return (
    <div className="modal modal-open">
      <div className={`modal-box ${wide ? "max-w-3xl" : "max-w-md"}`}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-sm truncate">{title}</h3>
          <button onClick={onClose} className="btn btn-ghost btn-xs">
            ✕
          </button>
        </div>
        {children}
      </div>
      <div className="modal-backdrop" onClick={onClose} />
    </div>
  );
}
