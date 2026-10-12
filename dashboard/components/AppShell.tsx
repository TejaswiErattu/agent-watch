import * as React from "react";
import Link from "next/link";

export interface AppShellProps {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  /** Extra header content on the right (e.g. a back link). */
  actions?: React.ReactNode;
  /** Rendered at the bottom of the sidebar (e.g. the Clear credentials button). */
  sidebarFooter?: React.ReactNode;
  children: React.ReactNode;
}

function Logo() {
  // Shield with an eye: inline SVG, no icon dependency.
  return (
    <svg viewBox="0 0 24 24" className="h-7 w-7" aria-hidden="true">
      <path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3Z" fill="#1F4D3A" />
      <path d="M6.5 12s2-3.5 5.5-3.5 5.5 3.5 5.5 3.5-2 3.5-5.5 3.5S6.5 12 6.5 12Z" fill="#D8EFE3" />
      <circle cx="12" cy="12" r="1.8" fill="#1F4D3A" />
    </svg>
  );
}

export function AppShell({ title, subtitle, actions, sidebarFooter, children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-brand-page text-gray-900 md:flex">
      <aside className="flex flex-wrap items-center justify-between gap-3 md:flex-nowrap border-b border-gray-200 bg-white px-4 py-3 md:sticky md:top-0 md:h-screen md:w-60 md:shrink-0 md:flex-col md:items-stretch md:border-b-0 md:border-r md:px-5 md:py-6">
        <div className="flex flex-wrap items-center gap-3 md:flex-col md:flex-nowrap md:items-stretch md:gap-8">
          <Link href="/" className="flex items-center gap-2 text-lg font-bold text-brand">
            <Logo />
            Agent Watch
          </Link>
          <nav aria-label="Main">
            <Link
              href="/"
              className="block rounded-full bg-brand-mint px-4 py-2 text-sm font-semibold text-brand"
            >
              Dashboard
            </Link>
          </nav>
        </div>
        {sidebarFooter ? <div className="md:mt-auto">{sidebarFooter}</div> : null}
      </aside>
      <main className="min-w-0 flex-1 px-4 py-6 sm:px-8 sm:py-8">
        <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <h1 className="break-words text-2xl font-bold text-gray-900 sm:text-3xl">{title}</h1>
            {subtitle ? <p className="mt-1 text-sm text-gray-600">{subtitle}</p> : null}
          </div>
          {actions}
        </header>
        <div className="space-y-6">{children}</div>
      </main>
    </div>
  );
}
