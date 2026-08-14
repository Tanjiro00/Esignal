import { OpportunityDetail } from "@/components/opportunities/opportunity-detail";
import { opportunityGroupFromParam } from "@/lib/opportunity-library";

export default async function OpportunityDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ signalId: string }>;
  searchParams: Promise<{ from?: string; section?: string }>;
}) {
  const { signalId } = await params;
  const { from, section } = await searchParams;
  const initialTab =
    section === "evidence"
      ? "Sources"
      : section === "lifecycle"
        ? "Timing"
        : "Overview";
  return (
    <OpportunityDetail
      initialAnalysisOpen={section === "content-gap"}
      initialTab={initialTab}
      returnGroup={opportunityGroupFromParam(from)}
      signalId={signalId}
    />
  );
}
