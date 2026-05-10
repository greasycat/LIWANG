"use client";

import { useEffect, useRef, useState } from "react";

import { CitationDrawer } from "@/components/citation-drawer";
import { MessageBubble } from "@/components/message-bubble";
import { apiClient } from "@/lib/api";
import type { ChatSession, Message, PostMessageResponse } from "@/lib/types";

const SAMPLES = [
  "焊接气孔率超标的复检流程?",
  "型号 A123 的注塑温度区间?",
  "302 不锈钢的认可替代供应商?",
  "新员工入职手续清单?",
];

export function ChatView({
  session,
  initialMessages,
}: {
  session: ChatSession;
  initialMessages: Message[];
}) {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const [streamingText, setStreamingText] = useState("");
  const [pending, setPending] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [citationDocId, setCitationDocId] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const taRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, streamingText]);

  async function send() {
    const content = draft.trim();
    if (!content || pending) return;
    setError(null);
    setDraft("");
    setPending(true);
    if (taRef.current) taRef.current.style.height = "auto";

    try {
      const r = await apiClient<PostMessageResponse>(
        `/sessions/${session.id}/messages`,
        {
          method: "POST",
          body: JSON.stringify({ content }),
        },
      );
      setMessages((prev) => [...prev, r.user_message, r.pending_message]);
      setStreamingId(r.pending_message.id);
      setStreamingText("");
      await streamInto(r.stream_url, r.pending_message.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "发送失败");
    } finally {
      setPending(false);
      setStreamingId(null);
    }
  }

  async function streamInto(url: string, messageId: string) {
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok || !res.body) {
      throw new Error(`stream failed: HTTP ${res.status}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let final: Message | null = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const handled = handleSse(block);
        if (handled?.kind === "delta") {
          setStreamingText(handled.content);
        } else if (handled?.kind === "done") {
          final = handled.message;
        }
      }
    }

    if (final) {
      const settled: Message = final;
      setMessages((prev) =>
        prev.map((m) => (m.id === messageId ? settled : m)),
      );
    }
    setStreamingText("");
  }

  return (
    <main className="flex-1 overflow-hidden flex flex-col bg-base-200">
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto w-full px-4 md:px-6 py-6">
          {messages.length === 0 && (
            <EmptyState
              onPick={(s) => {
                setDraft(s);
                taRef.current?.focus();
              }}
            />
          )}
          <div className="space-y-6">
            {messages.map((m) => {
              const isStreaming = m.id === streamingId;
              return (
                <MessageBubble
                  key={m.id}
                  message={
                    isStreaming
                      ? { ...m, content: streamingText || m.content }
                      : m
                  }
                  streaming={isStreaming}
                  onCitation={setCitationDocId}
                />
              );
            })}
          </div>
        </div>
      </div>

      <div className="border-t border-base-300 bg-base-100">
        <div className="max-w-3xl mx-auto w-full px-4 md:px-6 py-3">
          {error && (
            <div className="alert alert-error text-sm py-2 mb-2">{error}</div>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
          >
            <div className="rounded-2xl border border-base-300 focus-within:border-primary transition-colors bg-base-100 shadow-sm overflow-hidden">
              <textarea
                ref={taRef}
                value={draft}
                onChange={(e) => {
                  setDraft(e.target.value);
                  e.currentTarget.style.height = "auto";
                  e.currentTarget.style.height =
                    Math.min(e.currentTarget.scrollHeight, 240) + "px";
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void send();
                  }
                }}
                placeholder="问点什么… (Shift+Enter 换行)"
                rows={1}
                className="textarea w-full border-0 focus:outline-none resize-none bg-transparent text-sm py-3 px-4"
                style={{ minHeight: 48 }}
              />
              <div className="flex items-center justify-end px-3 pb-2 pt-1">
                <button
                  type="submit"
                  disabled={!draft.trim() || pending}
                  className="btn btn-primary btn-sm gap-1"
                >
                  发送
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-3.5 w-3.5"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M14 5l7 7m0 0l-7 7m7-7H3"
                    />
                  </svg>
                </button>
              </div>
            </div>
          </form>
          <p className="mt-1.5 text-[10px] text-center opacity-50">
            回答可能不准确 · 请核对引用来源
          </p>
        </div>
      </div>

      <CitationDrawer
        docId={citationDocId}
        onClose={() => setCitationDocId(null)}
      />
    </main>
  );
}

function EmptyState({ onPick }: { onPick: (s: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
      <div className="w-16 h-16 rounded-2xl bg-primary text-primary-content flex items-center justify-center mb-5 shadow-md">
        <span className="text-lg font-semibold tracking-tight">LIWANG</span>
      </div>
      <h1 className="text-2xl font-semibold tracking-tight">
        问任何关于公司的问题
      </h1>
      <p className="mt-2 text-sm opacity-60">
        基于内部 SOP、BOM、规范、培训材料、流程文件
      </p>

      <div className="mt-8 grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-2xl">
        {SAMPLES.map((s) => (
          <button
            key={s}
            type="button"
            className="text-left px-4 py-3 rounded-xl border border-base-300 hover:border-primary hover:bg-base-100 transition-colors text-sm"
            onClick={() => onPick(s)}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

type SseEvent =
  | { kind: "delta"; content: string }
  | { kind: "done"; message: Message }
  | { kind: "error"; error: string };

function handleSse(block: string): SseEvent | null {
  const lines = block.split("\n").filter(Boolean);
  let event = "message";
  let data = "";
  for (const ln of lines) {
    if (ln.startsWith("event:")) event = ln.slice(6).trim();
    else if (ln.startsWith("data:")) data += ln.slice(5).trim();
  }
  if (!data) return null;
  try {
    const parsed = JSON.parse(data);
    if (event === "delta") return { kind: "delta", content: parsed.content };
    if (event === "done") return { kind: "done", message: parsed.message };
    if (event === "error") return { kind: "error", error: parsed.error };
  } catch {
    return null;
  }
  return null;
}
