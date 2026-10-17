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
          <TableHead>Status</TableHead>
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
