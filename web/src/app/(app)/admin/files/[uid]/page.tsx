import { notFound } from "next/navigation";

import { FilesPage } from "@/components/files-page";
import { ApiError, apiServer } from "@/lib/api";
import type { FilesListing } from "@/lib/types";

export default async function AdminUserFilesPage({
  params,
}: {
  params: Promise<{ uid: string }>;
}) {
  const { uid } = await params;
  let listing: FilesListing;
  try {
    listing = await apiServer<FilesListing>(`/admin/files/${uid}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  return (
    <FilesPage
      initial={listing}
      apiBase={`/api/admin/files/${uid}`}
      linkBase={`/admin/files/${uid}`}
      viewingAsAdmin
    />
  );
}
