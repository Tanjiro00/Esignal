export const EMPTY_TODAY_REFETCH_INTERVAL_MS = 15_000;

type TodayFeedSnapshot = {
  feed: {
    total: number;
  };
};

export function todayRefetchInterval(
  data: TodayFeedSnapshot | undefined,
): number | false {
  if (!data || data.feed.total > 0) return false;
  return EMPTY_TODAY_REFETCH_INTERVAL_MS;
}
