import { notFound, redirect } from "next/navigation";

import { FilesPage } from "@/components/files-page";
import { ApiError, apiServer } from "@/lib/api";
import type { FilesListing } from "@/lib/types";

export default async function AdminUserFolderPage({
  params,
}: {
  params: Promise<{ uid: string; fid: string }>;
}) {
  const { uid, fid } = await params;
  let listing: FilesListing;
  try {
    listing = await apiServer<FilesListing>(
      `/admin/files/${uid}?parent_id=${fid}`,
    );
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  if (!listing.parent_id) redirect(`/admin/files/${uid}`);
  return (
    <FilesPage
      initial={listing}
      apiBase={`/api/admin/files/${uid}`}
      linkBase={`/admin/files/${uid}`}
      viewingAsAdmin
    />
  );
}
