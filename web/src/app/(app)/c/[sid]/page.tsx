import { notFound } from "next/navigation";

import { ChatView } from "@/components/chat-view";
import { ApiError, apiServer } from "@/lib/api";
import type { ChatSession, Message } from "@/lib/types";

export default async function ChatPage({
  params,
}: {
  params: Promise<{ sid: string }>;
}) {
  const { sid } = await params;
  let session: ChatSession;
  let messages: Message[];
  try {
    [session, messages] = await Promise.all([
      apiServer<ChatSession>(`/sessions/${sid}`),
      apiServer<Message[]>(`/sessions/${sid}/messages`),
    ]);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  return <ChatView session={session} initialMessages={messages} />;
}
