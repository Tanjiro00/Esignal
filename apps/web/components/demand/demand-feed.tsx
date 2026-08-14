"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink, MessageCircleQuestion, Users } from "lucide-react";

import { ErrorState } from "@/components/ui";
import { getDemandFeed } from "@/lib/api";
import type { DemandItem } from "@/lib/types";

function AskedBy({ item }: { item: DemandItem }) {
  const days = Math.max(0, Math.round(item.age_days));
  return (
    <p className="text-sm text-muted-foreground">
      <Users className="mr-1 inline h-4 w-4" />
      {item.distinct_askers} viewers asked across {item.distinct_channels}{" "}
      {item.distinct_channels === 1 ? "channel" : "channels"}
      {days === 0 ? " today" : ` in the last ${days} days`}
      {item.total_likes > 0 ? ` · ${item.total_likes} likes` : ""}
    </p>
  );
}

function Evidence({ item }: { item: DemandItem }) {
  if (item.evidence.length === 0) {
    return null;
  }
  return (
    <ul className="mt-3 space-y-2 border-l-2 border-muted pl-3">
      {item.evidence.slice(0, 3).map((comment) => (
        <li key={comment.comment_id} className="text-sm">
          <span className="text-foreground">“{comment.text.slice(0, 180)}”</span>{" "}
          <a
            className="inline-flex items-center gap-1 text-muted-foreground underline"
            href={comment.video_url}
            target="_blank"
            rel="noreferrer"
          >
            {comment.channel_title}
            <ExternalLink className="h-3 w-3" />
          </a>
        </li>
      ))}
    </ul>
  );
}

export function DemandFeed({ limit = 20 }: { limit?: number }) {
  const query = useQuery({
    queryKey: ["demand-feed", limit],
    queryFn: () => getDemandFeed(limit),
  });

  if (query.isError) {
    return <ErrorState message="Could not load the demand feed." />;
  }
  if (query.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading demand…</p>;
  }

  const items = query.data?.items ?? [];
  if (items.length === 0) {
    // An empty feed is a real state, not an error: the engine abstains when the
    // evidence is thin rather than showing something it cannot support.
    return (
      <p className="text-sm text-muted-foreground">
        No unanswered demand cleared the evidence bar yet. The next collection
        pass runs within six hours.
      </p>
    );
  }

  return (
    <ol className="space-y-6">
      {items.map((item) => (
        <li key={item.id} className="rounded-lg border p-4">
          <div className="flex items-start justify-between gap-4">
            <h3 className="text-base font-medium">
              <MessageCircleQuestion className="mr-2 inline h-5 w-5" />
              {item.headline}
            </h3>
            {item.subject ? (
              <span className="shrink-0 rounded bg-muted px-2 py-1 text-xs">
                {item.subject}
              </span>
            ) : null}
          </div>
          <div className="mt-2">
            <AskedBy item={item} />
          </div>
          <Evidence item={item} />
        </li>
      ))}
    </ol>
  );
}
