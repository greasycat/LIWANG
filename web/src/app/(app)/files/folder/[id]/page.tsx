import { notFound, redirect } from "next/navigation";

import { FilesPage } from "@/components/files-page";
import { ApiError, apiServer } from "@/lib/api";
import type { FilesListing } from "@/lib/types";

export default async function MyFilesFolderPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let listing: FilesListing;
  try {
    listing = await apiServer<FilesListing>(`/files?parent_id=${id}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  // FastAPI swallows invalid parent ids by returning root listing —
  // bounce the user back to /files in that case.
  if (!listing.parent_id) redirect("/files");
  return (
    <FilesPage
      initial={listing}
      apiBase="/api/files"
      linkBase="/files"
      viewingAsAdmin={false}
    />
  );
}
