import { AdminPageHeader } from "@/components/admin-header";
import { DocsTable } from "@/components/docs-table";
import { apiServer } from "@/lib/api-server";
import type { Doc } from "@/lib/types";

export default async function AdminDocsPage() {
  const docs = await apiServer<Doc[]>("/admin/docs");
  return (
    <>
      <AdminPageHeader
        title="文档库"
        subtitle={`${docs.length} 个文档`}
      />
      <DocsTable initial={docs} />
    </>
  );
}
