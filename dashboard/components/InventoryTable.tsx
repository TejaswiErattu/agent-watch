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

function formatSpend(usd: number): string {
  return `$${usd.toFixed(2)}`;
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
