"use client";

import { usePathname } from "next/navigation";

import { AdminNav } from "@/components/admin-nav";
import { Sidebar } from "@/components/sidebar";
import type { ChatSession } from "@/lib/types";

export function SidebarShell({ sessions }: { sessions: ChatSession[] }) {
  const pathname = usePathname();
  const isAdmin = pathname.startsWith("/admin");
  return isAdmin ? <AdminNav /> : <Sidebar sessions={sessions} />;
}
