"use client";

import * as React from "react";
import { getInventory, AuthError } from "@/lib/api";
import {
  loadCredentials,
  clearCredentials,
  type Credentials,
} from "@/lib/credentials";
import type { InventoryItem } from "@/lib/types";
import { AppShell } from "@/components/AppShell";
import { CredentialsForm } from "@/components/CredentialsForm";
import { InventoryTable } from "@/components/InventoryTable";
import { AddAgentForm } from "@/components/AddAgentForm";
import { StatTiles } from "@/components/StatTiles";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { Card, CardTitle } from "@/components/ui/card";

const POLL_MS = 30_000;
const SUBTITLE = "Watch what your agents do and what they cost";

export default function Home() {
  const [creds, setCreds] = React.useState<Credentials | null>(null);
  const [agents, setAgents] = React.useState<InventoryItem[]>([]);
  const [authFailed, setAuthFailed] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [loaded, setLoaded] = React.useState(false);

  React.useEffect(() => {
    setCreds(loadCredentials());
    setLoaded(true);
  }, []);

  const refresh = React.useCallback(async (c: Credentials) => {
    try {
      const res = await getInventory(c);
      setAgents(res.agents);
      setError(null);
      setAuthFailed(false);
    } catch (e) {
      if (e instanceof AuthError) {
        setAuthFailed(true);
      } else {
        // Keep the last data; surface an inline alert only.
        setError(e instanceof Error ? e.message : "Failed to load inventory");
      }
    }
  }, []);

  React.useEffect(() => {
    if (!creds || authFailed) return;
    void refresh(creds);
    const id = setInterval(() => void refresh(creds), POLL_MS);
    return () => clearInterval(id);
  }, [creds, authFailed, refresh]);

  function handleClear() {
    clearCredentials();
    setCreds(null);
    setAgents([]);
    setAuthFailed(false);
    setError(null);
  }

  function handleSaved() {
    setAuthFailed(false);
    setCreds(loadCredentials());
  }

  if (!loaded) return null;

  if (!creds || authFailed) {
    return (
      <AppShell title="Dashboard" subtitle={SUBTITLE}>
        <Card className="mx-auto max-w-md">
          <CardTitle>Connect</CardTitle>
          <p className="mb-4 text-sm text-gray-600">
            Enter your owner ID and API key to see your agents.
          </p>
          <CredentialsForm
            onSaved={handleSaved}
            error={authFailed ? "Credentials not accepted" : undefined}
          />
        </Card>
      </AppShell>
    );
  }

  return (
    <AppShell
      title="Dashboard"
      subtitle={SUBTITLE}
      sidebarFooter={
        <Button variant="outline" size="sm" onClick={handleClear} className="md:w-full">
          Clear credentials
        </Button>
      }
    >
      <StatTiles agents={agents} now={Date.now()} />
      {error ? <Alert variant="destructive">{error}</Alert> : null}
      <Card>
        <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
          <h2 className="text-lg font-semibold text-gray-900">Agents</h2>
          <AddAgentForm />
        </div>
        <InventoryTable agents={agents} />
      </Card>
    </AppShell>
  );
}
