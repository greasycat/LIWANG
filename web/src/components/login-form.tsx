"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { ApiError, apiClient } from "@/lib/api";
import type { User } from "@/lib/types";

export function LoginForm() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        const fd = new FormData(e.currentTarget);
        const username = String(fd.get("username") || "");
        const password = String(fd.get("password") || "");
        startTransition(async () => {
          try {
            await apiClient<User>("/auth/login", {
              method: "POST",
              body: JSON.stringify({ username, password }),
            });
            router.push("/");
            router.refresh();
          } catch (err) {
            if (err instanceof ApiError) {
              setError(typeof err.detail === "string" ? err.detail : "登录失败");
            } else {
              setError("网络错误");
            }
          }
        });
      }}
    >
      {error && <div className="alert alert-error text-sm py-2">{error}</div>}
      <label className="form-control">
        <div className="label py-1">
          <span className="label-text text-xs">用户名</span>
        </div>
        <input
          name="username"
          required
          autoFocus
          className="input input-bordered input-sm"
        />
      </label>
      <label className="form-control">
        <div className="label py-1">
          <span className="label-text text-xs">密码</span>
        </div>
        <input
          type="password"
          name="password"
          required
          className="input input-bordered input-sm"
        />
      </label>
      <button
        type="submit"
        disabled={pending}
        className="btn btn-primary btn-sm w-full"
      >
        {pending ? "登录中…" : "登录"}
      </button>
    </form>
  );
}
