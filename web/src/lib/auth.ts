import { redirect } from "next/navigation";

import { ApiError, apiServer } from "./api-server";
import type { Me } from "./types";

/** Call from a Server Component / Route Handler. Returns null if unauth. */
export async function getMe(): Promise<Me | null> {
  try {
    return await apiServer<Me>("/auth/me");
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null;
    throw e;
  }
}

/** Convenience: enforce auth and return Me, otherwise redirect to /login. */
export async function requireMe(): Promise<Me> {
  const me = await getMe();
  if (!me) redirect("/login");
  return me;
}

export async function requireAdmin(): Promise<Me> {
  const me = await requireMe();
  if (me.user.role !== "admin") redirect("/");
  return me;
}
