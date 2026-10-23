"use client";

import * as React from "react";
import { getInventory, AuthError } from "@/lib/api";
import {
  loadCredentials,
  clearCredentials,
  type Credentials,
} from "@/lib/credentials";
import type { InventoryItem } from "@/lib/types";
import { CredentialsForm } from "@/components/CredentialsForm";
import { InventoryTable } from "@/components/InventoryTable";
import { AddAgentForm } from "@/components/AddAgentForm";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import { Card } from "@/components/ui/card";
import { AppShell } from "@/components/AppShell";
import { KeyRound, LayoutGrid, Search } from "lucide-react";

const POLL_MS = 30_000;

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
      <AppShell active="inventory">
        <Hero />
        <Card title="Credentials" icon={KeyRound} className="mx-auto max-w-md">
          <p className="mb-4 text-sm text-muted">
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
      active="inventory"
      ownerId={creds.ownerId}
      actions={
        <Button variant="outline" onClick={handleClear}>
          Clear credentials
        </Button>
      }
    >
      <Hero />
      <Card title="Open an agent" icon={Search}>
        <AddAgentForm />
      </Card>
      {error ? <Alert variant="destructive">{error}</Alert> : null}
      <Card title="Inventory" icon={LayoutGrid}>
        <InventoryTable agents={agents} />
      </Card>
    </AppShell>
  );
}

// Pure-CSS gradient hero (no image files): orange to amber radial glow, dark text.
function Hero() {
  return (
    <div className="relative overflow-hidden rounded-2xl bg-hero p-6 text-background shadow-glow md:p-8">
      <h1 className="text-3xl font-bold tracking-tight md:text-4xl">Agent Watch</h1>
      <p className="mt-2 text-sm font-medium md:text-base">
        See, control, and cap what your AI agents do.
      </p>
    </div>
  );
}
