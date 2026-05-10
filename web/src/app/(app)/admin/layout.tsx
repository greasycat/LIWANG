import { requireAdmin } from "@/lib/auth";

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireAdmin();
  return (
    <main className="flex-1 overflow-y-auto bg-base-200">
      <div className="max-w-7xl mx-auto w-full px-4 md:px-8 py-6">{children}</div>
    </main>
  );
}
