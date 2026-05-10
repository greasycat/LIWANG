"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const SECTIONS = [
  {
    title: "概览",
    items: [{ href: "/admin", label: "仪表板", match: ["/admin"] }],
  },
  {
    title: "用户与配额",
    items: [
      { href: "/admin/users", label: "用户管理", match: ["/admin/users"] },
      { href: "/admin/usage", label: "Token 用量", match: ["/admin/usage"] },
    ],
  },
  {
    title: "知识库",
    items: [
      { href: "/admin/docs", label: "文档库", match: ["/admin/docs"] },
      { href: "/admin/upload", label: "批量上传", match: ["/admin/upload"] },
      { href: "/admin/ocr", label: "OCR 队列", match: ["/admin/ocr"] },
    ],
  },
];

export function AdminNav() {
  const pathname = usePathname();
  return (
    <div className="h-full flex flex-col">
      <div className="p-3 border-b border-base-300">
        <Link href="/" className="btn btn-ghost btn-sm w-full justify-start gap-2">
          ← 返回对话
        </Link>
      </div>
      <nav className="flex-1 overflow-y-auto px-2 py-2">
        {SECTIONS.map((s) => (
          <div key={s.title} className="mb-3">
            <div className="text-[10px] uppercase tracking-wider opacity-50 font-medium px-2 mb-1">
              {s.title}
            </div>
            <ul className="menu menu-sm gap-0.5 p-0">
              {s.items.map((it) => {
                const active =
                  pathname === it.href ||
                  (it.href !== "/admin" && pathname.startsWith(it.href + "/"));
                return (
                  <li key={it.href}>
                    <Link
                      href={it.href}
                      className={active ? "menu-active" : ""}
                    >
                      {it.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
      <div className="p-3 border-t border-base-300 text-xs opacity-60">
        <span>管理后台 v0.2</span>
      </div>
    </div>
  );
}
