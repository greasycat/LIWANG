import { FilesPage } from "@/components/files-page";
import { apiServer } from "@/lib/api-server";
import type { FilesListing } from "@/lib/types";

export default async function MyFilesPage() {
  const listing = await apiServer<FilesListing>("/files");
  return (
    <FilesPage
      initial={listing}
      apiBase="/api/files"
      linkBase="/files"
      viewingAsAdmin={false}
    />
  );
}
