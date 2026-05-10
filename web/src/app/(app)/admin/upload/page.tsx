import { AdminPageHeader } from "@/components/admin-header";
import { UploadManager } from "@/components/upload-manager";
import { apiServer } from "@/lib/api-server";
import type { UploadTable } from "@/lib/types";

export default async function AdminUploadPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;
  const path = status ? `/admin/upload?status=${status}` : "/admin/upload";
  const initial = await apiServer<UploadTable>(path);
  return (
    <>
      <AdminPageHeader
        title="批量上传"
        subtitle="拖拽文件到下方 · 上传前可批量编辑元数据"
      />
      <UploadManager initial={initial} />
    </>
  );
}
