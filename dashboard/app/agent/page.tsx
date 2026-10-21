"use client";

import * as React from "react";
import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { clearCredentials, loadCredentials, type Credentials } from "@/lib/credentials";
import { CredentialsForm } from "@/components/CredentialsForm";
import { Timeline } from "@/components/Timeline";
import { RulesEditor } from "@/components/RulesEditor";
import { PauseButton } from "@/components/PauseButton";
import { AgentSummary } from "@/components/AgentSummary";
import { SpendChart } from "@/components/SpendChart";
import { Alert } from "@/components/ui/alert";
import { AuthError, getConfig, getSpend, getStatus, getTimeline } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { AppShell } from "@/components/AppShell";
import { Activity, Gauge, KeyRound, ListChecks, ShieldCheck } from "lucide-react";
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
  const [authFailed, setAuthFailed] = React.useState(false);

  React.useEffect(() => {
    setCreds(loadCredentials());
    setLoaded(true);
  }, []);

  function handleClear() {
    clearCredentials();
    setCreds(null);
    setOverview(null);
    setError(null);
    setAuthFailed(false);
  }

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
      setAuthFailed(false);
    } catch (e) {
      setAuthFailed(e instanceof AuthError);
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
      <AppShell active="agent" agentId={agentId}>
        <Card className="mx-auto max-w-md">
          <div className="mb-4 flex items-center gap-2">
            <span
              aria-hidden="true"
              className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft text-accent"
            >
              <KeyRound className="h-4 w-4" />
            </span>
            <h1 className="text-xl font-semibold">Agent Watch</h1>
          </div>
          <p className="mb-4 text-sm text-muted">Enter your credentials to view this agent.</p>
          <CredentialsForm onSaved={() => setCreds(loadCredentials())} />
        </Card>
      </AppShell>
    );
  }

  if (!agentId) {
    return (
      <AppShell active="agent" ownerId={creds.ownerId}>
        <Card className="space-y-2">
          <p className="text-sm">No agent selected.</p>
          <Link href="/" className="text-sm text-accent hover:underline">
            Back to inventory
          </Link>
        </Card>
      </AppShell>
    );
  }

  const status = overview?.status ?? null;

  return (
    <AppShell active="agent" ownerId={creds.ownerId} agentId={agentId}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="min-w-0 break-all text-2xl font-bold tracking-tight md:text-3xl">{agentId}</h1>
        <Link
          href="/"
          className="inline-flex h-7 items-center rounded-full border border-strong px-3 text-xs font-medium text-foreground hover:bg-surface-raised"
        >
          Back to inventory
        </Link>
      </div>
      {error ? <Alert variant="destructive">{error}</Alert> : null}
      {authFailed ? (
        <Button variant="outline" onClick={handleClear}>
          Clear credentials
        </Button>
      ) : null}
      <Card title="Overview" icon={Gauge} className="space-y-4">
        <AgentSummary
          spend={overview?.spend ?? null}
          capUsd={overview?.capUsd ?? null}
          status={status}
          lastSeen={overview?.lastSeen ?? null}
        />
        {overview ? <SpendChart buckets={overview.buckets} capUsd={overview.capUsd} /> : null}
      </Card>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Status" icon={Activity}>
          {status ? (
            <div className="space-y-3">
              <p className="text-sm">
                Pause state:{" "}
                <span
                  data-testid="pause-state"
                  className={status.paused ? "font-medium text-danger" : "font-medium text-success"}
                >
                  {status.paused ? "Paused" : "Active"}
                </span>
                {status.paused && status.pausedAt ? (
                  <span className="text-muted"> since {status.pausedAt}</span>
                ) : null}
              </p>
              <PauseButton
                creds={creds}
                agentId={agentId}
                status={status}
                onChanged={() => void refresh()}
              />
            </div>
          ) : null}
        </Card>
        <Card title="Rules" icon={ShieldCheck}>
          <RulesEditor creds={creds} agentId={agentId} onSaved={() => void refresh()} />
        </Card>
      </div>
      <Card title="Timeline" icon={ListChecks}>
        <Timeline creds={creds} agentId={agentId} />
      </Card>
    </AppShell>
  );
}

export default function AgentPage() {
  return (
    <Suspense fallback={null}>
      <AgentDetail />
    </Suspense>
  );
}
