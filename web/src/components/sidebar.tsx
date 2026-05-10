"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useState, useTransition } from "react";

import { apiClient } from "@/lib/api";
import type { ChatSession } from "@/lib/types";
import { dateBucket } from "@/lib/format";

export function Sidebar({ sessions }: { sessions: ChatSession[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const [q, setQ] = useState("");
  const [pending, startTransition] = useTransition();

  const filtered = q
    ? sessions.filter((s) => s.title.toLowerCase().includes(q.toLowerCase()))
    : sessions;

  const buckets = new Map<string, ChatSession[]>();
  for (const s of filtered) {
    const b = dateBucket(s.updated_at);
    if (!buckets.has(b)) buckets.set(b, []);
    buckets.get(b)!.push(s);
  }

  return (
    <div className="h-full flex flex-col">
      <div className="p-3 border-b border-base-300 space-y-2">
        <button
          disabled={pending}
          className="btn btn-primary btn-sm w-full gap-2"
          onClick={() =>
            startTransition(async () => {
              const s = await apiClient<ChatSession>("/sessions", {
                method: "POST",
              });
              router.push(`/c/${s.id}`);
              router.refresh();
            })
          }
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M12 4v16m8-8H4"
            />
          </svg>
          新对话
        </button>
        <label className="input input-sm input-bordered flex items-center gap-2">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-3.5 w-3.5 opacity-60"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M21 21l-4.35-4.35M17 10a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            type="text"
            placeholder="搜索对话"
            className="grow"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-2 scroll-shadow">
        {filtered.length === 0 && (
          <div className="text-xs opacity-50 px-2 py-4">暂无对话</div>
        )}
        {Array.from(buckets.entries()).map(([bucket, items]) => (
          <div key={bucket} className="mb-3">
            <div className="text-[10px] uppercase tracking-wider opacity-40 px-2 mb-1">
              {bucket}
            </div>
            {items.map((s) => {
              const active = pathname === `/c/${s.id}`;
              return (
                <SessionRow
                  key={s.id}
                  session={s}
                  active={active}
                  onChanged={() => router.refresh()}
                />
              );
            })}
          </div>
        ))}
      </nav>

      <div className="p-3 border-t border-base-300 text-xs opacity-60">
        <div className="flex items-center justify-between">
          <span>v0.2 · Next.js</span>
          <kbd className="kbd kbd-xs">⌘K</kbd>
        </div>
      </div>
    </div>
  );
}

function SessionRow({
  session,
  active,
  onChanged,
}: {
  session: ChatSession;
  active: boolean;
  onChanged: () => void;
}) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(session.title);

  return (
    <div
      className={`group flex items-center rounded-lg px-2 py-1.5 text-sm ${
        active ? "bg-primary/10 font-medium" : "hover:bg-base-200"
      }`}
    >
      {editing ? (
        <form
          className="flex-1 flex gap-1"
          onSubmit={async (e) => {
            e.preventDefault();
            await apiClient(`/sessions/${session.id}`, {
              method: "PATCH",
              body: JSON.stringify({ title }),
            });
            setEditing(false);
            onChanged();
          }}
        >
          <input
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="input input-xs input-bordered grow"
            onBlur={() => setEditing(false)}
          />
        </form>
      ) : (
        <>
          <Link
            href={`/c/${session.id}`}
            className="flex-1 truncate"
            title={session.title}
          >
            {session.title}
          </Link>
          <div className="opacity-0 group-hover:opacity-100 flex gap-0.5 transition-opacity">
            <button
              type="button"
              className="btn btn-ghost btn-xs"
              onClick={(e) => {
                e.preventDefault();
                setEditing(true);
              }}
              title="重命名"
            >
              ✎
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-xs text-error"
              onClick={async (e) => {
                e.preventDefault();
                if (!confirm(`删除「${session.title}」？`)) return;
                await apiClient(`/sessions/${session.id}`, { method: "DELETE" });
                router.push("/");
                router.refresh();
              }}
              title="删除"
            >
              ✕
            </button>
          </div>
        </>
      )}
    </div>
  );
}
