"use client";

import * as React from "react";
import { getTimeline, type TimelineQuery } from "@/lib/api";
import type { Credentials } from "@/lib/credentials";
import type { EventType, TimelineItem } from "@/lib/types";
import { describeEvent, formatSpend, relativeTime } from "@/lib/format";

type Filter = "" | EventType;

export interface TimelineProps {
  creds: Credentials;
  agentId: string;
}

// Left dot: gray = paused, red = any other block, orange = llm/tool call.
function dotClass(e: TimelineItem): string {
  if (e.type === "blocked") return e.violationType === "paused" ? "bg-muted" : "bg-danger";
  return "bg-accent";
}

function EventRow({ e }: { e: TimelineItem }) {
  const [open, setOpen] = React.useState(false);
  const hasMeta = e.meta !== null && Object.keys(e.meta).length > 0;
  return (
    <li className="flex gap-3 rounded-xl bg-surface-raised p-3 text-sm">
      <span aria-hidden="true" className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${dotClass(e)}`} />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="text-muted" title={e.ts ?? undefined} data-testid="event-time">
            {e.ts ? relativeTime(e.ts) : ""}
          </span>
          <span className="min-w-0 break-all">{describeEvent(e)}</span>
          {e.type === "llm_call" && e.costUsd !== null ? (
            <span className="font-medium text-foreground" data-testid="event-cost">
              {formatSpend(e.costUsd)}
            </span>
          ) : null}
          {hasMeta ? (
            <button
              type="button"
              className="rounded text-xs text-accent hover:underline"
              aria-expanded={open}
              onClick={() => setOpen((v) => !v)}
            >
              {open ? "Hide details" : "Details"}
            </button>
          ) : null}
        </div>
        {open ? (
          <pre className="overflow-x-auto rounded-lg border bg-background p-2 text-xs text-foreground">
            {JSON.stringify(e.meta, null, 2)}
          </pre>
        ) : null}
      </div>
    </li>
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
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <label htmlFor="typeFilter" className="text-sm font-medium">
          Filter
        </label>
        <select
          id="typeFilter"
          value={filter}
          onChange={(e) => setFilter(e.target.value as Filter)}
          className="h-9 rounded-xl border border-strong bg-surface-raised px-2 text-sm text-foreground focus-visible:border-accent"
        >
          <option value="">All</option>
          <option value="llm_call">LLM calls</option>
          <option value="tool_call">Tool calls</option>
          <option value="blocked">Blocked</option>
        </select>
      </div>
      {error ? (
        <div role="alert" className="text-sm text-danger">
          {error}
        </div>
      ) : null}
      <ul className="space-y-2">
        {events.map((e, i) => (
          <EventRow key={e.eventId ?? i} e={e} />
        ))}
      </ul>
      <div ref={sentinelRef} aria-hidden className="h-1" />
      {loading ? <p className="text-sm text-muted">Loading…</p> : null}
    </div>
  );
}
