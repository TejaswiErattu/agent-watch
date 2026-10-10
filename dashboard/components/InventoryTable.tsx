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

// 4 decimals so sub-cent LLM spend (e.g. $0.0006) is visible instead of $0.00.
// Nonzero amounts too small for 4 decimals show "<$0.0001" rather than "$0.0000".
export function formatSpend(usd: number): string {
  if (usd > 0 && usd < 0.0001) return "<$0.0001";
  return `$${usd.toFixed(4)}`;
}

export interface InventoryTableProps {
  agents: InventoryItem[];
}

export function InventoryTable({ agents }: InventoryTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Agent</TableHead>
          <TableHead>Model</TableHead>
          <TableHead>Last activity</TableHead>
          <TableHead>Total spend</TableHead>
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
                  a.lastSeen
                )}
              </TableCell>
              <TableCell>{formatSpend(a.totalSpendUsd)}</TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
