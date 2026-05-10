import { AdminPageHeader } from "@/components/admin-header";
import { apiServer } from "@/lib/api-server";
import { formatDateTime } from "@/lib/format";
import type { OcrJob } from "@/lib/types";

function statusBadge(s: string) {
  if (s === "done") return "badge-success";
  if (s === "failed") return "badge-error";
  if (s === "claimed") return "badge-info";
  return "badge-ghost";
}

export default async function AdminOcrPage() {
  const jobs = await apiServer<OcrJob[]>("/admin/ocr");
  const failed = jobs.filter((j) => j.status === "failed").length;
  return (
    <>
      <AdminPageHeader
        title="OCR 队列"
        subtitle={`${jobs.length} 个作业 · ${failed} 失败`}
      />
      <div className="card bg-base-100 border border-base-300 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="table table-sm">
            <thead className="text-xs uppercase tracking-wider opacity-70 bg-base-200">
              <tr>
                <th>ID</th>
                <th>文档</th>
                <th>状态</th>
                <th className="text-right">尝试次数</th>
                <th>认领者</th>
                <th>创建时间</th>
                <th>错误</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} className="hover">
                  <td className="font-mono text-xs">{j.id}</td>
                  <td className="text-sm">{j.doc_source}</td>
                  <td>
                    <span className={`badge badge-sm ${statusBadge(j.status)}`}>
                      {j.status}
                    </span>
                  </td>
                  <td className="text-right font-mono text-xs">{j.attempts}</td>
                  <td className="text-xs opacity-70">{j.claimed_by || "—"}</td>
                  <td className="text-xs opacity-60">
                    {formatDateTime(j.created_at)}
                  </td>
                  <td className="text-xs text-error truncate max-w-[200px]">
                    {j.error || ""}
                  </td>
                </tr>
              ))}
              {jobs.length === 0 && (
                <tr>
                  <td colSpan={7} className="text-center py-12 opacity-50 text-sm">
                    暂无 OCR 作业
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
