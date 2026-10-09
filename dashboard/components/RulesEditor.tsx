"use client";

import * as React from "react";
import { getConfig, putConfig } from "@/lib/api";
import type { Credentials } from "@/lib/credentials";
import type { GuardrailConfig } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/alert";

export interface RulesEditorProps {
  creds: Credentials;
  agentId: string;
}

export function RulesEditor({ creds, agentId }: RulesEditorProps) {
  const [capInput, setCapInput] = React.useState("");
  const [paths, setPaths] = React.useState<string[]>([]);
  const [newPath, setNewPath] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [saved, setSaved] = React.useState(false);

  React.useEffect(() => {
    let active = true;
    getConfig(creds, agentId)
      .then((res) => {
        if (!active) return;
        const cap = res.guardrails.dailySpendCapUsd;
        setCapInput(cap === null ? "" : String(cap));
        setPaths(res.guardrails.blockedPaths);
      })
      .catch((e) => {
        if (active) setError(e instanceof Error ? e.message : "Failed to load config");
      });
    return () => {
      active = false;
    };
  }, [creds, agentId]);

  function addPath() {
    const p = newPath.trim();
    if (p && !paths.includes(p)) {
      setPaths((prev) => [...prev, p]);
    }
    setNewPath("");
  }

  function removePath(p: string) {
    setPaths((prev) => prev.filter((x) => x !== p));
  }

  async function handleSave() {
    const trimmed = capInput.trim();
    const config: GuardrailConfig = {
      dailySpendCapUsd: trimmed === "" ? null : Number(trimmed),
      blockedPaths: paths,
    };
    try {
      const res = await putConfig(creds, agentId, config);
      const cap = res.guardrails.dailySpendCapUsd;
      setCapInput(cap === null ? "" : String(cap));
      setPaths(res.guardrails.blockedPaths);
      setError(null);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save config");
      setSaved(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <label htmlFor="cap" className="text-sm font-medium">
          Daily spend cap (USD)
        </label>
        <Input
          id="cap"
          value={capInput}
          onChange={(e) => setCapInput(e.target.value)}
          placeholder="no cap"
          inputMode="decimal"
        />
      </div>

      <div className="space-y-2">
        <span className="text-sm font-medium">Blocked paths</span>
        <ul className="space-y-1">
          {paths.map((p) => (
            <li key={p} className="flex items-center justify-between gap-2 text-sm">
              <span>{p}</span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={`Remove ${p}`}
                onClick={() => removePath(p)}
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
        <div className="flex items-end gap-2">
          <div className="space-y-1">
            <label htmlFor="newPath" className="text-sm font-medium">
              Add path
            </label>
            <Input
              id="newPath"
              value={newPath}
              onChange={(e) => setNewPath(e.target.value)}
              placeholder=".env"
            />
          </div>
          <Button type="button" variant="outline" onClick={addPath}>
            Add path
          </Button>
        </div>
      </div>

      {error ? <Alert variant="destructive">{error}</Alert> : null}
      {saved && !error ? (
        <p className="text-sm text-green-700">Saved.</p>
      ) : null}

      <Button type="button" onClick={handleSave}>
        Save rules
      </Button>
    </div>
  );
}
