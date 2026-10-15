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
import { Alert } from "@/components/ui/alert";
import { getStatus } from "@/lib/api";
import type { StatusResponse } from "@/lib/types";

function AgentDetail() {
  const params = useSearchParams();
  const agentId = params.get("id");
  const [creds, setCreds] = React.useState<Credentials | null>(null);
  const [loaded, setLoaded] = React.useState(false);

  const [status, setStatus] = React.useState<StatusResponse | null>(null);
  const [statusError, setStatusError] = React.useState<string | null>(null);

  React.useEffect(() => {
    setCreds(loadCredentials());
    setLoaded(true);
  }, []);

  // Re-read status from the server (on load and after a pause/resume) so the
  // page shows the stored Pause_State, not just what the button last sent.
  const refreshStatus = React.useCallback(() => {
    if (!creds || !agentId) return;
    getStatus(creds, agentId)
      .then((res) => {
        setStatus(res);
        setStatusError(null);
      })
      .catch((e) => {
        setStatusError(e instanceof Error ? e.message : "Failed to load status");
      });
  }, [creds, agentId]);

  React.useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

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

  return (
    <main className="mx-auto max-w-5xl space-y-8 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{agentId}</h1>
        <Link href="/" className="text-sm text-blue-600 hover:underline">
          Back to inventory
        </Link>
      </div>
      <section className="space-y-3">
        <h2 className="text-lg font-medium">Status</h2>
        {statusError ? <Alert variant="destructive">{statusError}</Alert> : null}
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
              onChanged={refreshStatus}
            />
          </>
        ) : null}
      </section>
      <section className="space-y-3">
        <h2 className="text-lg font-medium">Rules</h2>
        <RulesEditor creds={creds} agentId={agentId} />
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
