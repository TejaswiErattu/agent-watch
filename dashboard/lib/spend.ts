// Client-side Spend_Series: hourly buckets of llm_call cost plus blocked counts
// over the last 24 h, built from the paged timeline API (Req 29.1-29.3).

import { getTimeline } from "./api";
import type { Credentials } from "./credentials";
import type { SpendBucket, TimelineItem } from "./types";

export const HOUR_MS = 3_600_000;
const PAGE_LIMIT = 100;

// Buckets are (start, start + 1h], ending at windowEnd, matching the backend's
// rolling window `windowEnd - 24h < ts <= windowEnd`.
export function bucketSpend(
  llmEvents: TimelineItem[],
  blockedEvents: TimelineItem[],
  windowEnd: number,
  hours = 24
): SpendBucket[] {
  const windowStart = windowEnd - hours * HOUR_MS;
  const buckets: SpendBucket[] = Array.from({ length: hours }, (_, i) => ({
    start: new Date(windowStart + i * HOUR_MS).toISOString(),
    costUsd: 0,
    llmCalls: 0,
    blocked: 0,
  }));

  const indexOf = (ts: string | null): number => {
    if (ts === null) return -1;
    const t = Date.parse(ts);
    if (Number.isNaN(t) || t <= windowStart || t > windowEnd) return -1;
    // ceil(...) - 1 so a ts exactly on a boundary belongs to the earlier bucket.
    return Math.ceil((t - windowStart) / HOUR_MS) - 1;
  };

  for (const e of llmEvents) {
    const i = indexOf(e.ts);
    if (i < 0) continue;
    buckets[i].llmCalls += 1;
    buckets[i].costUsd += e.costUsd ?? 0;
  }
  for (const e of blockedEvents) {
    const i = indexOf(e.ts);
    if (i >= 0) buckets[i].blocked += 1;
  }
  return buckets;
}

// Reads one event type newest-first until the window is covered: stops when a
// page's oldest ts is older than `since`, when there's no cursor, or at maxPages.
// Returns only events with since < ts.
export async function fetchWindow(
  creds: Credentials,
  agentId: string,
  type: "llm_call" | "blocked",
  since: string,
  maxPages = 20
): Promise<TimelineItem[]> {
  const sinceMs = Date.parse(since);
  const inWindow = (e: TimelineItem) =>
    e.ts !== null && Date.parse(e.ts) > sinceMs;
  const out: TimelineItem[] = [];
  let cursor: string | undefined;

  for (let page = 0; page < maxPages; page++) {
    const res = await getTimeline(creds, agentId, {
      order: "desc",
      type,
      limit: PAGE_LIMIT,
      ...(cursor ? { cursor } : {}),
    });
    out.push(...res.events.filter(inWindow));
    // An empty page can still carry a cursor (filtered reads), so keep going.
    const oldest = res.events.at(-1);
    if (oldest && oldest.ts !== null && Date.parse(oldest.ts) <= sinceMs) break;
    if (!res.nextCursor) break;
    cursor = res.nextCursor;
  }
  return out;
}
