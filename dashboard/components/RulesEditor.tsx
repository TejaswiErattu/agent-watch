"use client";

import * as React from "react";
import { getConfig, putConfig } from "@/lib/api";
import type { Credentials } from "@/lib/credentials";
import type { GuardrailConfig, GuardrailConfigIn } from "@/lib/types";
import { COMMAND_PRESETS } from "@/lib/commandPresets";
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
  const [commands, setCommands] = React.useState<string[]>([]);
  const [newCommand, setNewCommand] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [saved, setSaved] = React.useState(false);

  // An older backend omits blockedCommands, so read it as [] (Req 36.4).
  function applyConfig(g: GuardrailConfigIn) {
    const cap = g.dailySpendCapUsd;
    setCapInput(cap === null ? "" : String(cap));
    setPaths(g.blockedPaths);
    setCommands(g.blockedCommands ?? []);
  }

  React.useEffect(() => {
    let active = true;
    getConfig(creds, agentId)
      .then((res) => {
        if (active) applyConfig(res.guardrails);
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

  function addCommand() {
    const c = newCommand.trim();
    if (c && !commands.includes(c)) {
      setCommands((prev) => [...prev, c]);
    }
    setNewCommand("");
  }

  function removeCommand(c: string) {
    setCommands((prev) => prev.filter((x) => x !== c));
  }

  // Appends every preset pattern not already in the list, in preset order.
  function addPresets() {
    setCommands((prev) => {
      const missing = COMMAND_PRESETS.map((p) => p.pattern).filter((p) => !prev.includes(p));
      return [...prev, ...missing];
    });
  }

  async function handleSave() {
    const trimmed = capInput.trim();
    const config: GuardrailConfig = {
      dailySpendCapUsd: trimmed === "" ? null : Number(trimmed),
      blockedPaths: paths,
      blockedCommands: commands,
    };
    try {
      const res = await putConfig(creds, agentId, config);
      applyConfig(res.guardrails);
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

      <div className="space-y-2">
        <span className="text-sm font-medium">Blocked commands (regex, case-insensitive)</span>
        <ul className="space-y-1">
          {commands.map((c) => (
            <li key={c} className="flex items-center justify-between gap-2 text-sm">
              <code className="break-all">{c}</code>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={`Remove pattern ${c}`}
                onClick={() => removeCommand(c)}
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <label htmlFor="newCommand" className="text-sm font-medium">
              Add pattern
            </label>
            <Input
              id="newCommand"
              value={newCommand}
              onChange={(e) => setNewCommand(e.target.value)}
              placeholder="\bsudo\b"
            />
          </div>
          <Button type="button" variant="outline" onClick={addCommand}>
            Add pattern
          </Button>
          <Button type="button" variant="outline" onClick={addPresets}>
            Add presets
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
