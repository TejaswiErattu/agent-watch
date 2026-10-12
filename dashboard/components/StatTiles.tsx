import * as React from "react";
import type { InventoryItem } from "@/lib/types";
import { inventoryStats } from "@/lib/stats";
import { formatSpend } from "@/components/InventoryTable";
import { cn } from "@/lib/utils";

export interface StatTilesProps {
  agents: InventoryItem[];
  now: number;
}

export function StatTiles({ agents, now }: StatTilesProps) {
  const s = inventoryStats(agents, now);
  const tiles = [
    { label: "Agents", value: String(s.agents) },
    { label: "Total spend", value: formatSpend(s.totalSpendUsd) },
    { label: "Active in last 24h", value: String(s.activeLast24h) },
    { label: "Not yet reported", value: String(s.notYetReported) },
  ];
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {tiles.map((t, i) => {
        const highlight = i === 0;
        return (
          <div
            key={t.label}
            role="group"
            aria-label={t.label}
            className={cn(
              "rounded-2xl p-5 shadow-sm",
              highlight ? "bg-brand text-white" : "bg-white text-gray-900 ring-1 ring-black/5"
            )}
          >
            <p className={cn("text-sm font-medium", highlight ? "text-brand-mint" : "text-gray-600")}>
              {t.label}
            </p>
            <p className="mt-2 break-all text-2xl font-bold tabular-nums sm:text-3xl">{t.value}</p>
          </div>
        );
      })}
    </div>
  );
}
