import { AdminPageHeader } from "@/components/admin-header";
import { UsersTable } from "@/components/users-table";
import { apiServer } from "@/lib/api-server";
import type { AdminUserRow } from "@/lib/types";

export default async function AdminUsersPage() {
  const rows = await apiServer<AdminUserRow[]>("/admin/users");
  const ym = new Date().toISOString().slice(0, 7);
  return (
    <>
      <AdminPageHeader
        title="用户管理"
        subtitle={`${rows.length} 个用户 · 当前月份 ${ym}`}
      />
      <UsersTable initial={rows} />
    </>
  );
}
