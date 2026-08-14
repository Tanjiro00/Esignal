"use client";

import { useQuery } from "@tanstack/react-query";

import { ErrorState, PageLoading } from "@/components/ui";
import { getDemoContext } from "@/lib/api";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const query = useQuery({
    queryKey: ["admin-access"],
    queryFn: getDemoContext,
  });

  if (query.isLoading) return <PageLoading label="Checking admin access" />;
  if (query.isError)
    return (
      <ErrorState message={query.error.message} retry={() => query.refetch()} />
    );
  if (!query.data?.is_admin) {
    return (
      <div className="mx-auto max-w-[720px] px-6 py-24">
        <h1 className="editorial text-[36px]">Admin access required</h1>
        <p className="mt-3 text-[13px] leading-6 text-[var(--muted)]">
          These operational tools are available only to workspace owners and
          admins.
        </p>
      </div>
    );
  }
  return children;
}
