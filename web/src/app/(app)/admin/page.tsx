import { AdminPageHeader } from "@/components/admin-header";
import { apiServer } from "@/lib/api";
import { formatInt, formatMoney } from "@/lib/format";
import type { AdminOverview } from "@/lib/types";

export default async function AdminOverviewPage() {
  const data = await apiServer<AdminOverview>("/admin/overview");
  const kpis: { label: string; value: string; unit?: string }[] = [
    { label: "本月查询", value: formatInt(data.total_queries), unit: "次" },
    { label: "活跃用户", value: formatInt(data.active_users), unit: "人" },
    { label: "Token 消耗", value: formatInt(data.total_tokens), unit: "tokens" },
    { label: "本月成本", value: formatMoney(data.total_cost) },
  ];
  return (
    <>
      <AdminPageHeader
        title="仪表板"
        subtitle={`${data.month} · 系统总览`}
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        {kpis.map((k) => (
          <div
            key={k.label}
            className="card bg-base-100 border border-base-300 shadow-sm"
          >
            <div className="card-body p-4">
              <div className="text-xs opacity-60">{k.label}</div>
              <div className="mt-1 flex items-baseline gap-1">
                <span className="text-2xl font-semibold tracking-tight">
                  {k.value}
                </span>
                {k.unit && <span className="text-xs opacity-60">{k.unit}</span>}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="card bg-base-100 border border-base-300 shadow-sm">
        <div className="card-body p-5">
          <h2 className="font-semibold text-sm">系统状态</h2>
          <ul className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <li className="flex justify-between">
              <span className="opacity-70">文档总数</span>
              <span className="font-mono">{formatInt(data.doc_count)}</span>
            </li>
            <li className="flex justify-between">
              <span className="opacity-70">OCR 失败</span>
              <span
                className={`font-mono ${data.failed_jobs > 0 ? "text-error" : ""}`}
              >
                {formatInt(data.failed_jobs)}
              </span>
            </li>
            <li className="flex justify-between">
              <span className="opacity-70">DeepSeek API</span>
              <span className="badge badge-success badge-sm">正常</span>
            </li>
            <li className="flex justify-between">
              <span className="opacity-70">DashScope API</span>
              <span className="badge badge-success badge-sm">正常</span>
            </li>
          </ul>
        </div>
      </div>
    </>
  );
}
