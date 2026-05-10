"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { apiClient } from "@/lib/api";
import type { Me } from "@/lib/types";

export function Topbar({ me }: { me: Me }) {
  const router = useRouter();
  const isAdmin = me.user.role === "admin";
  return (
    <header className="navbar bg-base-100 border-b border-base-300 min-h-[56px] px-3 gap-2">
      <div className="flex-none">
        <label htmlFor="sidebar-drawer" className="btn btn-ghost btn-sm md:hidden">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-5 w-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M4 6h16M4 12h16M4 18h16"
            />
          </svg>
        </label>
        <Link
          href="/"
          className="text-base font-semibold tracking-tight hover:opacity-80"
        >
          LIWANG <span className="opacity-60 font-normal">知识助手</span>
        </Link>
      </div>
      <div className="flex-1" />
      <nav className="hidden md:flex items-center gap-1 text-sm">
        <Link href="/" className="btn btn-ghost btn-sm">
          对话
        </Link>
        <Link href="/files" className="btn btn-ghost btn-sm">
          我的文件
        </Link>
        {isAdmin && (
          <div className="dropdown dropdown-end">
            <button tabIndex={0} className="btn btn-ghost btn-sm">
              管理
              <svg
                className="h-3 w-3 opacity-60"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M19 9l-7 7-7-7"
                />
              </svg>
            </button>
            <ul
              tabIndex={0}
              className="dropdown-content menu menu-sm bg-base-100 rounded-box z-50 w-44 p-1 shadow border border-base-300"
            >
              <li>
                <Link href="/admin">概览</Link>
              </li>
              <li>
                <Link href="/admin/users">用户</Link>
              </li>
              <li>
                <Link href="/admin/docs">文档</Link>
              </li>
              <li>
                <Link href="/admin/upload">上传</Link>
              </li>
              <li>
                <Link href="/admin/ocr">OCR 队列</Link>
              </li>
              <li>
                <Link href="/admin/usage">用量</Link>
              </li>
            </ul>
          </div>
        )}
      </nav>
      <div className="flex-none flex items-center gap-2">
        <div className="hidden sm:flex flex-col items-end leading-tight">
          <span className="text-xs font-medium">{me.user.display_name}</span>
          <span className="text-[10px] opacity-50">
            {me.user.role === "admin" ? "管理员" : me.user.username}
            {me.month_tokens_cap !== null && me.month_tokens_pct !== null && (
              <>
                {" · "}
                {Math.round(me.month_tokens_pct)}%
              </>
            )}
          </span>
        </div>
        <button
          className="btn btn-ghost btn-sm"
          onClick={async () => {
            await apiClient("/auth/logout", { method: "POST" });
            router.push("/login");
            router.refresh();
          }}
        >
          退出
        </button>
      </div>
    </header>
  );
}
