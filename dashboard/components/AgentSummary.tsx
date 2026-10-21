import * as React from "react";
import type { SpendResponse, StatusResponse } from "@/lib/types";
import { formatSpend, relativeTime } from "@/lib/format";

export interface AgentSummaryProps {
  spend: SpendResponse | null;
  capUsd: number | null;
  status: StatusResponse | null;
  lastSeen: string | null;
  now?: number;
}

// Percent of the cap used, clamped to 0..100. Exported for the test.
export function capPercent(spendUsd: number, capUsd: number): number {
  if (capUsd <= 0) return 100;
  return Math.min(100, Math.max(0, (spendUsd / capUsd) * 100));
}

export function AgentSummary({ spend, capUsd, status, lastSeen, now }: AgentSummaryProps) {
  const spent = spend?.rollingSpendUsd ?? 0;
  const pct = capUsd !== null ? capPercent(spent, capUsd) : null;
  const over = capUsd !== null && spent >= capUsd;

  const tile = "space-y-2 rounded-2xl border bg-surface-raised p-5";
  const caption = "text-xs font-medium uppercase tracking-wide text-muted";
  const pill = "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium";

  return (
    <div className="grid gap-4 sm:grid-cols-3" data-testid="agent-summary">
      <div className={tile}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className={caption}>Spend (last 24 h)</p>
          {pct !== null ? (
            <span className={`${pill} ${over ? "bg-danger/10 text-danger" : "bg-accent-soft text-accent"}`}>
              {over ? "over cap" : `${Math.round(pct)}% of cap`}
            </span>
          ) : null}
        </div>
        <p className="text-4xl font-bold tracking-tight" data-testid="summary-spend">
          {spend ? formatSpend(spent) : "…"}
          <span className="ml-2 block text-sm font-normal tracking-normal text-muted sm:inline" data-testid="summary-cap">
            {capUsd === null ? "no cap" : `of ${formatSpend(capUsd)} cap`}
          </span>
        </p>
        {pct !== null ? (
          <div
            role="progressbar"
            aria-label="Spend against daily cap"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(pct)}
            className="h-2 w-full overflow-hidden rounded-full bg-background"
          >
            <div
              data-testid="cap-bar"
              className={`h-2 rounded-full ${over ? "bg-danger" : "bg-cap-bar"}`}
              style={{ width: `${pct}%` }}
            />
          </div>
        ) : null}
      </div>
      <div className={tile}>
        <p className={caption}>Status</p>
        <p
          className={`text-4xl font-bold tracking-tight ${status?.paused ? "text-danger" : ""}`}
          data-testid="summary-status"
        >
          {status === null ? "…" : status.paused ? "Paused" : "Active"}
        </p>
      </div>
      <div className={tile}>
        <p className={caption}>Last activity</p>
        <p className="text-2xl font-bold tracking-tight md:text-3xl" data-testid="summary-last" title={lastSeen ?? undefined}>
          {lastSeen ? relativeTime(lastSeen, now) : "not yet reported"}
        </p>
      </div>
    </div>
  );
}
