// Shared display helpers for the inventory, summary tile, and timeline.

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
