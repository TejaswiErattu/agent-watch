// Shared display helpers for the inventory, summary tile, and timeline.

import type { TimelineItem } from "./types";

// 4 decimals so sub-cent LLM spend (e.g. $0.0006) is visible instead of $0.00.
// Nonzero amounts too small for 4 decimals show "<$0.0001" rather than "$0.0000".
export function formatSpend(usd: number): string {
  if (usd > 0 && usd < 0.0001) return "<$0.0001";
  return `$${usd.toFixed(4)}`;
}

// "just now", "N min ago", "N h ago", "N d ago". Future timestamps (clock skew)
// read as "just now"; an unparseable ts gives "".
export function relativeTime(ts: string, now: number = Date.now()): string {
  const t = Date.parse(ts);
  if (Number.isNaN(t)) return "";
  const s = Math.floor((now - t) / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h ago`;
  return `${Math.floor(h / 24)} d ago`;
}

function metaNum(e: TimelineItem, key: string): string {
  const v = e.meta?.[key];
  return typeof v === "number" ? String(v) : "?";
}

function metaStr(e: TimelineItem, key: string): string {
  const v = e.meta?.[key];
  return typeof v === "string" ? v : "";
}

// One line per event, with one branch per Violation_Type (Req 29.8).
export function describeEvent(e: TimelineItem): string {
  switch (e.type) {
    case "llm_call":
      return `LLM call ${e.model ?? ""} (in ${e.inputTokens ?? 0}, out ${e.outputTokens ?? 0})`;
    case "tool_call":
      return `Tool ${e.tool ?? ""} -> ${e.target ?? ""}`;
    case "blocked":
      switch (e.violationType) {
        case "blocked_path":
          return `Blocked path ${e.attemptedPath ?? ""}`;
        case "spend_cap":
          return `Spend cap: blocked a call costing about ${formatSpend(e.attemptedCostUsd ?? 0)}`;
        case "paused": {
          const what = metaStr(e, "model") || metaStr(e, "tool");
          const action = metaStr(e, "action") || "call";
          return `Paused: blocked ${action}${what ? ` ${what}` : ""}`;
        }
        case "blocked_command":
          return `Blocked command ${e.attemptedCommand ?? ""}`;
        case "rate_limit":
          return `Rate limit: ${metaNum(e, "callsInWindow")} calls in 60 s (max ${metaNum(e, "maxPerMinute")})`;
        case "secret_redacted":
          return `Redacted ${metaNum(e, "total")} secret(s) before the LLM call`;
        case "blocked_domain":
          return `Blocked domain ${e.attemptedUrl ?? ""}`;
        default:
          return `Blocked ${e.violationType ?? ""}`;
      }
    default:
      return e.type ?? "event";
  }
}
