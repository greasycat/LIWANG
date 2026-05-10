import { redirect } from "next/navigation";

import { LoginForm } from "@/components/login-form";
import { getMe } from "@/lib/auth";

export default async function LoginPage() {
  const me = await getMe();
  if (me) redirect("/");
  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-base-200 font-sans">
      <div className="card w-full max-w-sm bg-base-100 shadow-xl">
        <div className="card-body">
          <div className="text-center mb-3">
            <div className="w-12 h-12 rounded-xl bg-primary text-primary-content flex items-center justify-center mx-auto mb-3">
              <span className="text-sm font-semibold">LIWANG</span>
            </div>
            <h1 className="text-lg font-semibold">登录 LIWANG的学习助手</h1>
            <p className="text-xs opacity-60 mt-1">使用账号</p>
          </div>

          <LoginForm />

          <div className="divider text-[10px] opacity-40">演示账号</div>
          <div className="text-[11px] opacity-60 space-y-0.5 font-mono">
            <div>admin / admin (管理员)</div>
            <div>alice / alice (R&amp;D)</div>
            <div>bob / bob (QA)</div>
          </div>
        </div>
      </div>
    </div>
  );
}
