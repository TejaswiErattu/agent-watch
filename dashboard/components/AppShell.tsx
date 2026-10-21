import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";

export interface AppShellProps {
  active: "inventory" | "agent";
  // Shown as "Hi, <ownerId>" in the top bar once credentials are stored.
  ownerId?: string | null;
  // Current agent id, so the Agent nav link returns to it.
  agentId?: string | null;
  actions?: React.ReactNode;
  children: React.ReactNode;
}

function NavLink({ href, current, children }: { href: string; current: boolean; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      aria-current={current ? "page" : undefined}
      className={cn(
        "rounded-xl px-3 py-2 text-sm font-medium transition-colors",
        current ? "bg-accent-soft text-accent" : "text-muted hover:bg-surface-raised hover:text-foreground"
      )}
    >
      {children}
    </Link>
  );
}

// Slim left sidebar on >= md; on small screens it collapses to a top row.
export function AppShell({ active, ownerId, agentId, actions, children }: AppShellProps) {
  const agentHref = agentId ? `/agent?id=${encodeURIComponent(agentId)}` : "/agent";
  return (
    <div className="min-h-screen md:flex">
      <aside className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b bg-surface px-4 py-3 md:sticky md:top-0 md:h-screen md:w-56 md:shrink-0 md:flex-col md:flex-nowrap md:items-stretch md:border-b-0 md:border-r md:px-4 md:py-6">
        <div className="flex items-center gap-2 px-1 md:px-3">
          <span aria-hidden="true" className="h-3 w-3 rounded-full bg-accent shadow-glow" />
          <span className="font-semibold tracking-tight">Agent Watch</span>
        </div>
        <nav aria-label="Main" className="flex gap-1 md:flex-col">
          <NavLink href="/" current={active === "inventory"}>
            Inventory
          </NavLink>
          <NavLink href={agentHref} current={active === "agent"}>
            Agent
          </NavLink>
        </nav>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-4 md:px-8">
          <p className="min-w-0 break-all text-sm text-muted">
            {ownerId ? (
              <>
                Hi, <span className="font-medium text-foreground">{ownerId}</span>
              </>
            ) : null}
          </p>
          {actions}
        </header>
        <main className="mx-auto max-w-5xl space-y-6 p-4 md:p-8">{children}</main>
      </div>
    </div>
  );
}
