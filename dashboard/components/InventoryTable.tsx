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
import { formatSpend, shortModel } from "@/lib/format";

// Re-exported so existing imports from this module keep working.
export { formatSpend };

const STALE_MS = 24 * 3_600_000;

// Last activity strictly older than 24 h (Req 29.9).
export function isStale(lastSeen: string | null, now: number = Date.now()): boolean {
  if (lastSeen === null) return false;
  const t = Date.parse(lastSeen);
  return !Number.isNaN(t) && now - t > STALE_MS;
}

// Short values stay on one line (no "demo" / "-bot" split). A value longer than a
// column can hold may wrap, but only between characters of that one long string.
export const NOWRAP_MAX = 24;
export function cellWrap(value: string): string {
  return value.length <= NOWRAP_MAX ? "whitespace-nowrap" : "[overflow-wrap:anywhere]";
}

// Short model name on one line, full id on hover (title) and for screen readers
// (sr-only). When the short name is the full id, one span is enough.
function ModelName({ id }: { id: string }) {
  const short = shortModel(id);
  if (short === id) {
    return (
      <span className="whitespace-nowrap" title={id || undefined}>
        {id}
      </span>
    );
  }
  return (
    <>
      <span className="whitespace-nowrap" title={id} aria-hidden="true" data-testid="model-short">
        {short}
      </span>
      <span className="sr-only">{id}</span>
    </>
  );
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
            <TableCell colSpan={5} className="py-6 text-center text-muted">
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
                  className={`rounded font-medium text-accent hover:underline ${cellWrap(a.agentId)}`}
                >
                  {a.agentId}
                </Link>
              </TableCell>
              <TableCell>
                <ModelName id={a.model ?? ""} />
              </TableCell>
              <TableCell>
                {unreported ? (
                  <span className="text-muted">not yet reported</span>
                ) : (
                  <>
                    {a.lastSeen}
                    {isStale(a.lastSeen, now) ? (
                      <span className="ml-2 rounded-full bg-amber/15 px-2 py-0.5 text-xs font-medium text-amber">
                        stale
                      </span>
                    ) : null}
                  </>
                )}
              </TableCell>
              <TableCell className="font-medium">{formatSpend(a.totalSpendUsd)}</TableCell>
              <TableCell>
                {a.paused === true ? (
                  <span className="rounded-full bg-danger/15 px-2 py-0.5 text-xs font-medium text-danger">
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
