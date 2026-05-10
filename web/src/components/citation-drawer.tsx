"use client";

import { useEffect, useState } from "react";

import { ApiError, apiClient } from "@/lib/api";
import type { DocPreview } from "@/lib/types";

export function CitationDrawer({
  docId,
  onClose,
}: {
  docId: string | null;
  onClose: () => void;
}) {
  const [data, setData] = useState<DocPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!docId) return;
    setLoading(true);
    setError(null);
    setData(null);
    apiClient<DocPreview>(`/docs/${docId}/view`)
      .then(setData)
      .catch((e) => {
        if (e instanceof ApiError) setError(String(e.detail));
        else setError("加载失败");
      })
      .finally(() => setLoading(false));
  }, [docId]);

  if (!docId) return null;

  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-black/30" onClick={onClose} />
      <aside className="w-full max-w-xl bg-base-100 border-l border-base-300 flex flex-col">
        <header className="flex items-center justify-between px-4 py-3 border-b border-base-300">
          <h3 className="text-sm font-medium truncate">
            {data?.doc.source || "文档预览"}
          </h3>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            ✕
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-4 text-sm">
          {loading && (
            <div className="opacity-50">
              <span className="loading loading-dots loading-sm" /> 加载中…
            </div>
          )}
          {error && <div className="alert alert-error text-sm">{error}</div>}
          {data && data.error && (
            <div className="alert alert-warning text-sm">{data.error}</div>
          )}
          {data && data.kind === "pdf" && data.has_file && (
            <iframe
              src={data.raw_url}
              className="w-full h-[80vh] border-0"
              title={data.doc.source}
            />
          )}
          {data && data.body && (
            <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
              {data.body}
            </pre>
          )}
          {data && data.has_file && (
            <div className="mt-4 flex gap-2">
              <a
                href={data.download_url}
                className="btn btn-sm btn-outline"
                download
              >
                下载原文件
              </a>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
