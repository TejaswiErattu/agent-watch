import * as React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export interface CardProps extends React.HTMLAttributes<HTMLElement> {
  // Rendered as the section's h2, so headings and their names are unchanged.
  title?: string;
  icon?: LucideIcon;
  // Optional pill button or link on the right of the header row.
  action?: React.ReactNode;
}

// Surface card: soft border, rounded-2xl, p-5, with an optional header row
// (icon circle + muted title on the left, action on the right).
export function Card({ title, icon: Icon, action, className, children, ...props }: CardProps) {
  return (
    <section className={cn("rounded-2xl border bg-surface p-5", className)} {...props}>
      {title ? (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            {Icon ? (
              <span
                aria-hidden="true"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent"
              >
                <Icon className="h-4 w-4" />
              </span>
            ) : null}
            <h2 className="text-sm font-medium text-muted">{title}</h2>
          </div>
          {action}
        </div>
      ) : null}
      {children}
    </section>
  );
}
