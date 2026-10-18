"use client";

import * as React from "react";
import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { loadCredentials, type Credentials } from "@/lib/credentials";
import { CredentialsForm } from "@/components/CredentialsForm";
import { Timeline } from "@/components/Timeline";
import { RulesEditor } from "@/components/RulesEditor";
import { PauseButton } from "@/components/PauseButton";
import { AgentSummary } from "@/components/AgentSummary";
import { SpendChart } from "@/components/SpendChart";
import { Alert } from "@/components/ui/alert";
import { getConfig, getSpend, getStatus, getTimeline } from "@/lib/api";
import { bucketSpend, fetchWindow, HOUR_MS } from "@/lib/spend";
import type { SpendBucket, SpendResponse, StatusResponse } from "@/lib/types";

// Not exported: Next.js page modules may only export the page and route config.
const REFRESH_MS = 30_000;

interface Overview {
  status: StatusResponse;
  spend: SpendResponse;
  capUsd: number | null;
  buckets: SpendBucket[];
  lastSeen: string | null;
}

function AgentDetail() {
  const params = useSearchParams();
  const agentId = params.get("id");
  const [creds, setCreds] = React.useState<Credentials | null>(null);
  const [loaded, setLoaded] = React.useState(false);
  const [overview, setOverview] = React.useState<Overview | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    setCreds(loadCredentials());
    setLoaded(true);
  }, []);

  // One refresh for everything above the rules: status, server spend, cap,
  // the 24h chart, and last activity. Runs on load, every 30 s, and after a
  // rules save or pause/resume.
  const refresh = React.useCallback(async () => {
    if (!creds || !agentId) return;
    const end = Date.now();
    const since = new Date(end - 24 * HOUR_MS).toISOString();
    try {
      const [status, spend, config, llm, blocked, latest] = await Promise.all([
        getStatus(creds, agentId),
        getSpend(creds, agentId),
        getConfig(creds, agentId),
        fetchWindow(creds, agentId, "llm_call", since),
        fetchWindow(creds, agentId, "blocked", since),
        getTimeline(creds, agentId, { order: "desc", limit: 1 }),
      ]);
      setOverview({
        status,
        spend,
        capUsd: config.guardrails.dailySpendCapUsd,
        buckets: bucketSpend(llm, blocked, end),
        lastSeen: latest.events[0]?.ts ?? null,
      });
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load agent overview");
    }
  }, [creds, agentId]);

  React.useEffect(() => {
    void refresh();
    const id = setInterval(() => void refresh(), REFRESH_MS);
    return () => clearInterval(id);
  }, [refresh]);

  if (!loaded) return null;

  if (!creds) {
    return (
      <main className="mx-auto max-w-5xl p-8">
        <h1 className="text-2xl font-semibold">Agent Watch</h1>
        <p className="mt-2 mb-6 text-sm text-gray-600">
          Enter your credentials to view this agent.
        </p>
        <CredentialsForm onSaved={() => setCreds(loadCredentials())} />
      </main>
    );
  }

  if (!agentId) {
    return (
      <main className="mx-auto max-w-5xl p-8">
        <p className="text-sm">No agent selected.</p>
        <Link href="/" className="text-blue-600 hover:underline">
          Back to inventory
        </Link>
      </main>
    );
  }

  const status = overview?.status ?? null;

  return (
    <main className="mx-auto max-w-5xl space-y-8 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{agentId}</h1>
        <Link href="/" className="text-sm text-blue-600 hover:underline">
          Back to inventory
        </Link>
      </div>
      {error ? <Alert variant="destructive">{error}</Alert> : null}
      <section className="space-y-3">
        <h2 className="text-lg font-medium">Overview</h2>
        <AgentSummary
          spend={overview?.spend ?? null}
          capUsd={overview?.capUsd ?? null}
          status={status}
          lastSeen={overview?.lastSeen ?? null}
        />
        {overview ? <SpendChart buckets={overview.buckets} capUsd={overview.capUsd} /> : null}
      </section>
      <section className="space-y-3">
        <h2 className="text-lg font-medium">Status</h2>
        {status ? (
          <>
            <p className="text-sm">
              Pause state:{" "}
              <span data-testid="pause-state" className="font-medium">
                {status.paused ? "Paused" : "Active"}
              </span>
              {status.paused && status.pausedAt ? (
                <span className="text-gray-500"> since {status.pausedAt}</span>
              ) : null}
            </p>
            <PauseButton
              creds={creds}
              agentId={agentId}
              status={status}
              onChanged={() => void refresh()}
            />
          </>
        ) : null}
      </section>
      <section className="space-y-3">
        <h2 className="text-lg font-medium">Rules</h2>
        <RulesEditor creds={creds} agentId={agentId} onSaved={() => void refresh()} />
      </section>
      <section className="space-y-3">
        <h2 className="text-lg font-medium">Timeline</h2>
        <Timeline creds={creds} agentId={agentId} />
      </section>
    </main>
  );
}

export default function AgentPage() {
  return (
    <Suspense fallback={null}>
      <AgentDetail />
    </Suspense>
  );
}
