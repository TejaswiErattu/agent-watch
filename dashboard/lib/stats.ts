import type { InventoryItem } from "./types";

const DAY_MS = 24 * 60 * 60 * 1000;

export interface InventoryStats {
  agents: number;
  totalSpendUsd: number;
  activeLast24h: number;
  notYetReported: number;
}

// Derived only from GET /agents data; nothing here is fetched or invented.
export function inventoryStats(agents: InventoryItem[], now: number): InventoryStats {
  let totalSpendUsd = 0;
  let activeLast24h = 0;
  let notYetReported = 0;
  for (const a of agents) {
    totalSpendUsd += a.totalSpendUsd;
    if (a.lastSeen === null) {
      notYetReported += 1;
      continue;
    }
    const t = Date.parse(a.lastSeen);
    if (!Number.isNaN(t) && now - t <= DAY_MS) activeLast24h += 1;
  }
  return { agents: agents.length, totalSpendUsd, activeLast24h, notYetReported };
}
