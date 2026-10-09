"use client";

import * as React from "react";
import { hashKey, saveCredentials } from "@/lib/credentials";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/alert";

export interface CredentialsFormProps {
  onSaved: () => void;
  error?: string;
}

export function CredentialsForm({ onSaved, error }: CredentialsFormProps) {
  const [ownerId, setOwnerId] = React.useState("");
  const [apiKey, setApiKey] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const keyHash = await hashKey(apiKey);
      saveCredentials({ ownerId, keyHash });
      setApiKey("");
      onSaved();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mx-auto max-w-sm space-y-4">
      <div className="space-y-1">
        <label htmlFor="ownerId" className="text-sm font-medium">
          Owner ID
        </label>
        <Input
          id="ownerId"
          value={ownerId}
          onChange={(e) => setOwnerId(e.target.value)}
          autoComplete="username"
        />
      </div>
      <div className="space-y-1">
        <label htmlFor="apiKey" className="text-sm font-medium">
          API key
        </label>
        <Input
          id="apiKey"
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          autoComplete="current-password"
        />
      </div>
      {error ? <Alert variant="destructive">{error}</Alert> : null}
      <Button type="submit" disabled={busy}>
        Save credentials
      </Button>
    </form>
  );
}
