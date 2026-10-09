"use client";

import * as React from "react";
import { getTimeline, type TimelineQuery } from "@/lib/api";
import type { Credentials } from "@/lib/credentials";
import type { EventType, TimelineItem } from "@/lib/types";

type Filter = "" | EventType;

export interface TimelineProps {
  creds: Credentials;
  agentId: string;
}

function describeEvent(e: TimelineItem): string {
  switch (e.type) {
    case "llm_call":
      return `LLM call ${e.model ?? ""} (in ${e.inputTokens ?? 0}, out ${e.outputTokens ?? 0})`;
    case "tool_call":
      return `Tool ${e.tool ?? ""} -> ${e.target ?? ""}`;
    case "blocked":
      return `Blocked ${e.violationType ?? ""} ${e.attemptedPath ?? ""}`;
    default:
      return e.type ?? "event";
  }
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
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <label htmlFor="typeFilter" className="text-sm font-medium">
          Filter
        </label>
        <select
          id="typeFilter"
          value={filter}
          onChange={(e) => setFilter(e.target.value as Filter)}
          className="h-9 rounded-md border border-gray-300 bg-white px-2 text-sm"
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
      <ul className="divide-y rounded-md border">
        {events.map((e, i) => (
          <li key={e.eventId ?? i} className="p-3 text-sm">
            <span className="text-gray-500">{e.ts}</span>{" "}
            <span>{describeEvent(e)}</span>
          </li>
        ))}
      </ul>
      <div ref={sentinelRef} aria-hidden className="h-1" />
      {loading ? <p className="text-sm text-gray-500">Loading…</p> : null}
    </div>
  );
}
