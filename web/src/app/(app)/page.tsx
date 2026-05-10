import { redirect } from "next/navigation";

import { apiServer } from "@/lib/api-server";
import type { ChatSession } from "@/lib/types";

export default async function HomePage() {
  const sessions = await apiServer<ChatSession[]>("/sessions");
  if (sessions.length > 0) {
    redirect(`/c/${sessions[0].id}`);
  }
  // No sessions — create one and redirect.
  const fresh = await apiServer<ChatSession>("/sessions", { method: "POST" });
  redirect(`/c/${fresh.id}`);
}
