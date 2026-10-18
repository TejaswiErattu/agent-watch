import * as React from "react";
import Link from "next/link";
import type { InventoryItem } from "@/lib/types";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { formatSpend } from "@/lib/format";

// Re-exported so existing imports from this module keep working.
export { formatSpend };

const STALE_MS = 24 * 3_600_000;

// Last activity strictly older than 24 h (Req 29.9).
export function isStale(lastSeen: string | null, now: number = Date.now()): boolean {
  if (lastSeen === null) return false;
  const t = Date.parse(lastSeen);
  return !Number.isNaN(t) && now - t > STALE_MS;
}

export interface InventoryTableProps {
  agents: InventoryItem[];
  now?: number;
}

export function InventoryTable({ agents, now }: InventoryTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Agent</TableHead>
          <TableHead>Model</TableHead>
          <TableHead>Last activity</TableHead>
          <TableHead>Total spend</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {agents.length === 0 ? (
          <TableRow>
            <TableCell colSpan={5} className="py-6 text-center text-gray-600">
              No agents for these credentials. Check the key, or run an agent once.
            </TableCell>
          </TableRow>
        ) : null}
        {agents.map((a) => {
          const unreported = a.lastSeen === null;
          return (
            <TableRow key={a.agentId}>
              <TableCell>
                <Link
                  href={`/agent?id=${encodeURIComponent(a.agentId)}`}
                  className="font-medium text-blue-600 hover:underline"
                >
                  {a.agentId}
                </Link>
              </TableCell>
              <TableCell>{a.model ?? ""}</TableCell>
              <TableCell>
                {unreported ? (
                  <span className="text-gray-500">not yet reported</span>
                ) : (
                  <>
                    {a.lastSeen}
                    {isStale(a.lastSeen, now) ? (
                      <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">
                        stale
                      </span>
                    ) : null}
                  </>
                )}
              </TableCell>
              <TableCell>{formatSpend(a.totalSpendUsd)}</TableCell>
              <TableCell>
                {a.paused === true ? (
                  <span className="rounded bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">
                    Paused
                  </span>
                ) : (
                  "Active"
                )}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
