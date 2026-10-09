"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/alert";

const AGENT_ID_RE = /^[A-Za-z0-9._-]{1,128}$/;

export function AddAgentForm() {
  const router = useRouter();
  const [agentId, setAgentId] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!AGENT_ID_RE.test(agentId)) {
      setError("Agent ID must be 1-128 chars of letters, digits, . _ -");
      return;
    }
    setError(null);
    router.push(`/agent?id=${encodeURIComponent(agentId)}`);
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-2">
      <div className="space-y-1">
        <label htmlFor="newAgentId" className="text-sm font-medium">
          Agent ID
        </label>
        <Input
          id="newAgentId"
          value={agentId}
          onChange={(e) => setAgentId(e.target.value)}
          placeholder="my-agent"
        />
      </div>
      <Button type="submit">Open</Button>
      {error ? (
        <Alert variant="destructive" className="ml-2">
          {error}
        </Alert>
      ) : null}
    </form>
  );
}
