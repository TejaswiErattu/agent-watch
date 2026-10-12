"use client";

import * as React from "react";
import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { loadCredentials, type Credentials } from "@/lib/credentials";
import { AppShell } from "@/components/AppShell";
import { CredentialsForm } from "@/components/CredentialsForm";
import { Timeline } from "@/components/Timeline";
import { RulesEditor } from "@/components/RulesEditor";
import { Card, CardTitle } from "@/components/ui/card";

function BackLink() {
  return (
    <Link
      href="/"
      className="inline-flex h-9 items-center rounded-full border border-brand bg-white px-4 text-sm font-medium text-brand hover:bg-brand-mint"
    >
      Back to inventory
    </Link>
  );
}

function AgentDetail() {
  const params = useSearchParams();
  const agentId = params.get("id");
  const [creds, setCreds] = React.useState<Credentials | null>(null);
  const [loaded, setLoaded] = React.useState(false);

  React.useEffect(() => {
    setCreds(loadCredentials());
    setLoaded(true);
  }, []);

  if (!loaded) return null;

  if (!creds) {
    return (
      <AppShell title={agentId ?? "Agent"} subtitle="Enter your credentials to view this agent.">
        <Card className="mx-auto max-w-md">
          <CardTitle>Connect</CardTitle>
          <CredentialsForm onSaved={() => setCreds(loadCredentials())} />
        </Card>
      </AppShell>
    );
  }

  if (!agentId) {
    return (
      <AppShell title="Agent" actions={<BackLink />}>
        <Card>
          <p className="text-sm text-gray-700">No agent selected.</p>
        </Card>
      </AppShell>
    );
  }

  return (
    <AppShell
      title={agentId}
      subtitle="Rules and activity for this agent"
      actions={<BackLink />}
    >
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] lg:items-start">
        <Card>
          <CardTitle>Rules</CardTitle>
          <RulesEditor creds={creds} agentId={agentId} />
        </Card>
        <Card>
          <CardTitle>Timeline</CardTitle>
          <Timeline creds={creds} agentId={agentId} />
        </Card>
      </div>
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
