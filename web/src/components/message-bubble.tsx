"use client";

import { useState } from "react";

import { apiClient } from "@/lib/api";
import type { Message } from "@/lib/types";

export function MessageBubble({
  message,
  streaming,
  onCitation,
}: {
  message: Message;
  streaming?: boolean;
  onCitation?: (docId: string) => void;
}) {
  const [rating, setRating] = useState(message.rating);

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="chat-bubble-user max-w-[85%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }

  async function rate(value: number) {
    setRating(value);
    try {
      await apiClient(`/messages/${message.id}/rating`, {
        method: "POST",
        body: JSON.stringify({ value }),
      });
    } catch {
      setRating(message.rating);
    }
  }

  return (
    <div className="flex gap-3">
      <div className="avatar placeholder shrink-0">
        <div className="bg-primary text-primary-content w-8 h-8 rounded-lg flex items-center justify-center">
          <span className="text-[10px] font-semibold">LIWANG</span>
        </div>
      </div>
      <div className="flex-1 min-w-0">
        <div className="prose prose-sm max-w-none text-sm leading-relaxed whitespace-pre-wrap">
          {message.content}
          {streaming && (
            <span className="inline-block ml-1 align-baseline">
              <span className="loading loading-dots loading-xs" />
            </span>
          )}
        </div>

        {message.citations.length > 0 && (
          <div className="mt-3 pt-3 border-t border-base-300/60">
            <div className="text-[10px] uppercase tracking-wider opacity-50 mb-1.5">
              来源
            </div>
            <ul className="space-y-1">
              {message.citations.map((c) => (
                <li key={`${c.doc_id}:${c.chunk_id}`}>
                  <button
                    type="button"
                    onClick={() => onCitation?.(c.doc_id)}
                    className="link link-hover text-xs flex items-center gap-1.5 text-left"
                  >
                    <span className="badge badge-sm badge-ghost font-mono">
                      {c.label}
                    </span>
                    <span>
                      {c.source}
                      {c.page ? ` · 第 ${c.page} 页` : ""}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {!streaming && (
          <div className="mt-2 flex items-center gap-1 text-xs opacity-60">
            <button
              type="button"
              aria-label="点赞"
              onClick={() => rate(rating === 1 ? 0 : 1)}
              className={`btn btn-ghost btn-xs px-1.5 ${rating === 1 ? "text-success" : ""}`}
            >
              👍
            </button>
            <button
              type="button"
              aria-label="点踩"
              onClick={() => rate(rating === -1 ? 0 : -1)}
              className={`btn btn-ghost btn-xs px-1.5 ${rating === -1 ? "text-error" : ""}`}
            >
              👎
            </button>
            <button
              type="button"
              aria-label="复制"
              onClick={() => navigator.clipboard.writeText(message.content)}
              className="btn btn-ghost btn-xs px-1.5"
            >
              📋
            </button>
            {message.prompt_tokens > 0 && (
              <span className="ml-auto font-mono text-[10px] opacity-40">
                {message.prompt_tokens}↑ {message.completion_tokens}↓ · ¥
                {message.cost_cny.toFixed(4)}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
