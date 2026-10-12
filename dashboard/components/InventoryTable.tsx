import * as React from "react";
import Link from "next/link";
import type { InventoryItem } from "@/lib/types";
import { relativeTime } from "@/lib/time";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";

// 4 decimals so sub-cent LLM spend (e.g. $0.0006) is visible instead of $0.00.
// Nonzero amounts too small for 4 decimals show "<$0.0001" rather than "$0.0000".
export function formatSpend(usd: number): string {
  if (usd > 0 && usd < 0.0001) return "<$0.0001";
  return `$${usd.toFixed(4)}`;
}

export interface InventoryTableProps {
  agents: InventoryItem[];
  now?: number;
}

export function InventoryTable({ agents, now = Date.now() }: InventoryTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>Agent</TableHead>
          <TableHead>Model</TableHead>
          <TableHead>Last activity</TableHead>
          <TableHead className="text-right">Total spend</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {agents.map((a) => {
          const unreported = a.lastSeen === null;
          return (
            <TableRow key={a.agentId}>
              <TableCell>
                <Link
                  href={`/agent?id=${encodeURIComponent(a.agentId)}`}
                  className="font-semibold text-brand underline-offset-2 hover:underline"
                >
                  {a.agentId}
                </Link>
              </TableCell>
              <TableCell>
                {a.model ? (
                  <span className="inline-block max-w-[16rem] truncate rounded-full bg-gray-100 px-2.5 py-0.5 align-middle text-xs text-gray-700">
                    {a.model}
                  </span>
                ) : null}
              </TableCell>
              <TableCell className="whitespace-nowrap">
                {unreported ? (
                  <span className="text-gray-600">not yet reported</span>
                ) : (
                  <time dateTime={a.lastSeen!} title={a.lastSeen!} className="text-gray-700">
                    {relativeTime(a.lastSeen!, now)}
                  </time>
                )}
              </TableCell>
              <TableCell className="text-right font-medium tabular-nums">
                {formatSpend(a.totalSpendUsd)}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
