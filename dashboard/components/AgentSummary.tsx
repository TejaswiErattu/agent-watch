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

  return (
    <div className="grid gap-4 rounded-md border p-4 sm:grid-cols-3" data-testid="agent-summary">
      <div className="space-y-1">
        <p className="text-xs uppercase text-gray-500">Spend (last 24 h)</p>
        <p className="text-lg font-semibold" data-testid="summary-spend">
          {spend ? formatSpend(spent) : "…"}
          <span className="ml-1 text-sm font-normal text-gray-500" data-testid="summary-cap">
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
            className="h-2 w-full rounded bg-gray-200"
          >
            <div
              data-testid="cap-bar"
              className={`h-2 rounded ${over ? "bg-red-600" : "bg-blue-600"}`}
              style={{ width: `${pct}%` }}
            />
          </div>
        ) : null}
      </div>
      <div className="space-y-1">
        <p className="text-xs uppercase text-gray-500">Status</p>
        <p className="text-lg font-semibold" data-testid="summary-status">
          {status === null ? "…" : status.paused ? "Paused" : "Active"}
        </p>
      </div>
      <div className="space-y-1">
        <p className="text-xs uppercase text-gray-500">Last activity</p>
        <p className="text-lg font-semibold" data-testid="summary-last" title={lastSeen ?? undefined}>
          {lastSeen ? relativeTime(lastSeen, now) : "not yet reported"}
        </p>
      </div>
    </div>
  );
}
