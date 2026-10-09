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
      <main className="mx-auto max-w-5xl p-8">
        <h1 className="text-2xl font-semibold">Agent Watch</h1>
        <p className="mt-2 mb-6 text-sm text-gray-600">
          Enter your owner ID and API key to see your agents.
        </p>
        <CredentialsForm
          onSaved={handleSaved}
          error={authFailed ? "Credentials not accepted" : undefined}
        />
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-5xl space-y-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Agent Watch</h1>
        <Button variant="outline" onClick={handleClear}>
          Clear credentials
        </Button>
      </div>
      <AddAgentForm />
      {error ? <Alert variant="destructive">{error}</Alert> : null}
      <InventoryTable agents={agents} />
    </main>
  );
}
