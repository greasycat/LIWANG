import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";
import { apiServer } from "@/lib/api";
import { requireMe } from "@/lib/auth";
import type { ChatSession } from "@/lib/types";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const me = await requireMe();
  const sessions = await apiServer<ChatSession[]>("/sessions");

  return (
    <div className="h-screen flex flex-col">
      <Topbar me={me} />
      <div className="drawer md:drawer-open flex-1 min-h-0">
        <input id="sidebar-drawer" type="checkbox" className="drawer-toggle" />
        <div className="drawer-content flex flex-col bg-base-200">{children}</div>
        <aside className="drawer-side z-30">
          <label htmlFor="sidebar-drawer" className="drawer-overlay" />
          <div className="w-72 h-full bg-base-100 border-r border-base-300">
            <Sidebar sessions={sessions} />
          </div>
        </aside>
      </div>
    </div>
  );
}
