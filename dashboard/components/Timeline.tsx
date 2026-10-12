"use client";

import * as React from "react";
import { getTimeline, type TimelineQuery } from "@/lib/api";
import type { Credentials } from "@/lib/credentials";
import type { EventType, TimelineItem } from "@/lib/types";
import { relativeTime } from "@/lib/time";
import { cn } from "@/lib/utils";

type Filter = "" | EventType;

export interface TimelineProps {
  creds: Credentials;
  agentId: string;
}

// The status pill carries the event type, so details skip the type prefix.
function describeEvent(e: TimelineItem): string {
  switch (e.type) {
    case "llm_call":
      return `${e.model ?? ""} (in ${e.inputTokens ?? 0}, out ${e.outputTokens ?? 0})`;
    case "tool_call":
      return `${e.tool ?? ""} -> ${e.target ?? ""}`;
    case "blocked":
      return `${e.violationType ?? ""} ${e.attemptedPath ?? ""}`.trim();
    default:
      return e.type ?? "event";
  }
}

const PILLS: Record<EventType, { label: string; className: string }> = {
  blocked: { label: "Blocked", className: "bg-red-100 text-red-800" },
  llm_call: { label: "LLM call", className: "bg-brand-mint text-brand" },
  tool_call: { label: "Tool call", className: "bg-gray-100 text-gray-700" },
};

function StatusPill({ type }: { type: EventType | null }) {
  const pill = type ? PILLS[type] : undefined;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
        pill?.className ?? "bg-gray-100 text-gray-700"
      )}
    >
      {pill?.label ?? "Event"}
    </span>
  );
}

export function Timeline({ creds, agentId }: TimelineProps) {
  const [events, setEvents] = React.useState<TimelineItem[]>([]);
  const [cursor, setCursor] = React.useState<string | null>(null);
  const [filter, setFilter] = React.useState<Filter>("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const sentinelRef = React.useRef<HTMLDivElement | null>(null);

  const load = React.useCallback(
    async (reset: boolean, cur: string | null, type: Filter) => {
      setLoading(true);
      try {
        const query: TimelineQuery = { order: "desc" };
        if (type) query.type = type;
        if (!reset && cur) query.cursor = cur;
        const res = await getTimeline(creds, agentId, query);
        setEvents((prev) => (reset ? res.events : [...prev, ...res.events]));
        setCursor(res.nextCursor);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load timeline");
      } finally {
        setLoading(false);
      }
    },
    [creds, agentId]
  );

  // Initial load and whenever the filter changes: reset the list.
  React.useEffect(() => {
    setEvents([]);
    setCursor(null);
    void load(true, null, filter);
  }, [filter, load]);

  // Infinite scroll: load the next page when the sentinel scrolls into view.
  React.useEffect(() => {
    const node = sentinelRef.current;
    if (!node) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && cursor && !loading) {
        void load(false, cursor, filter);
      }
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [cursor, loading, filter, load]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <label htmlFor="typeFilter" className="text-sm font-medium text-gray-700">
          Filter
        </label>
        <select
          id="typeFilter"
          value={filter}
          onChange={(e) => setFilter(e.target.value as Filter)}
          className="h-9 rounded-full border border-gray-300 bg-white px-3 text-sm text-gray-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-mid"
        >
          <option value="">All</option>
          <option value="llm_call">LLM calls</option>
          <option value="tool_call">Tool calls</option>
          <option value="blocked">Blocked</option>
        </select>
      </div>
      {error ? (
        <div role="alert" className="text-sm text-red-700">
          {error}
        </div>
      ) : null}
      <ul className="divide-y divide-gray-100 overflow-hidden rounded-xl border border-gray-100">
        {events.map((e, i) => (
          <li
            key={e.eventId ?? i}
            className={cn(
              "flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-3 text-sm",
              e.type === "blocked" ? "border-l-4 border-l-red-600 bg-red-50" : "bg-white"
            )}
          >
            <StatusPill type={e.type} />
            <span className="min-w-0 flex-1 break-all text-gray-900">{describeEvent(e)}</span>
            {e.ts ? (
              <time dateTime={e.ts} title={e.ts} className="shrink-0 text-xs text-gray-600">
                {relativeTime(e.ts, Date.now())}
              </time>
            ) : null}
          </li>
        ))}
      </ul>
      {!loading && events.length === 0 && !error ? (
        <p className="text-sm text-gray-600">No events yet.</p>
      ) : null}
      <div ref={sentinelRef} aria-hidden className="h-1" />
      {loading ? <p className="text-sm text-gray-600">Loading…</p> : null}
    </div>
  );
}
