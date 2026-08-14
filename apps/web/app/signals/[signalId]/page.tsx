import { redirect } from "next/navigation";

export default async function SignalCompatibilityPage({
  params,
  searchParams,
}: {
  params: Promise<{ signalId: string }>;
  searchParams: Promise<{ from?: string; section?: string }>;
}) {
  const { signalId } = await params;
  const { from, section } = await searchParams;
  const preserved = new URLSearchParams();
  if (from) preserved.set("from", from);
  if (
    section === "evidence" ||
    section === "lifecycle" ||
    section === "content-gap"
  ) {
    preserved.set("section", section);
  }
  const query = preserved.toString();
  redirect(`/opportunities/${signalId}${query ? `?${query}` : ""}`);
}
