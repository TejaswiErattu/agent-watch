"use client";

import * as React from "react";
import { putStatus } from "@/lib/api";
import type { Credentials } from "@/lib/credentials";
import type { StatusResponse } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";

export interface PauseButtonProps {
  creds: Credentials;
  agentId: string;
  status: StatusResponse;
  onChanged?: (status: StatusResponse) => void;
}

// Pause needs a second click ("Confirm pause") because it stops a running
// agent; resume is one click since it only restores normal operation.
export function PauseButton({ creds, agentId, status, onChanged }: PauseButtonProps) {
  const [paused, setPaused] = React.useState(status.paused);
  const [confirming, setConfirming] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Follow the parent when it refetches status.
  React.useEffect(() => {
    setPaused(status.paused);
  }, [status.paused]);

  async function send(next: boolean) {
    setBusy(true);
    try {
      const res = await putStatus(creds, agentId, next);
      setPaused(res.paused);
      setError(null);
      onChanged?.(res);
    } catch (e) {
      // Keep the previous label; the server state did not change from our view.
      setError(e instanceof Error ? e.message : "Failed to update status");
    } finally {
      setConfirming(false);
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        {paused ? (
          <Button type="button" disabled={busy} onClick={() => send(false)}>
            Resume agent
          </Button>
        ) : confirming ? (
          <>
            <Button
              type="button"
              variant="destructive"
              disabled={busy}
              onClick={() => send(true)}
            >
              Confirm pause
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => setConfirming(false)}
            >
              Cancel
            </Button>
          </>
        ) : (
          <Button type="button" variant="destructive" onClick={() => setConfirming(true)}>
            Pause agent
          </Button>
        )}
      </div>
      {error ? <Alert variant="destructive">{error}</Alert> : null}
    </div>
  );
}
