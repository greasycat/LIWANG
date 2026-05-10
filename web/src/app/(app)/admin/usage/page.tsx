import { AdminPageHeader } from "@/components/admin-header";
import { apiServer } from "@/lib/api-server";
import { formatInt, formatMoney } from "@/lib/format";
import type { UsageGrid } from "@/lib/types";

export default async function AdminUsagePage() {
  const grid = await apiServer<UsageGrid>("/admin/usage");
  return (
    <>
      <AdminPageHeader
        title="Token 用量"
        subtitle={`${grid.users.length} 用户 × ${grid.months.length} 月`}
      />
      <div className="card bg-base-100 border border-base-300 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="table table-sm">
            <thead className="text-xs uppercase tracking-wider opacity-70 bg-base-200">
              <tr>
                <th>用户</th>
                {grid.months.map((m) => (
                  <th key={m} className="text-right font-mono">
                    {m}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grid.users.map((u) => (
                <tr key={u.id} className="hover">
                  <td>
                    <div className="font-medium text-sm">{u.display_name}</div>
                    <div className="text-[11px] opacity-60 font-mono">
                      {u.username}
                    </div>
                  </td>
                  {grid.months.map((m) => {
                    const cell = grid.cells[u.id]?.[m];
                    if (!cell) {
                      return (
                        <td
                          key={m}
                          className="text-right text-xs opacity-30 font-mono"
                        >
                          —
                        </td>
                      );
                    }
                    return (
                      <td key={m} className="text-right">
                        <div className="font-mono text-sm">
                          {formatInt(cell.prompt_tokens + cell.completion_tokens)}
                        </div>
                        <div className="text-[10px] opacity-60 font-mono">
                          {formatMoney(cell.cost_cny)} · {formatInt(cell.queries)} 次
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
              {grid.users.length === 0 && (
                <tr>
                  <td
                    colSpan={grid.months.length + 1}
                    className="text-center py-12 opacity-50 text-sm"
                  >
                    暂无用量数据
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
