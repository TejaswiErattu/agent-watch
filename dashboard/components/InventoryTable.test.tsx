import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { InventoryTable } from "./InventoryTable";
import type { InventoryItem } from "@/lib/types";

const reported: InventoryItem = {
  agentId: "bot1",
  ownerId: "alice",
  model: "anthropic.claude-3-sonnet",
  firstSeen: "2026-10-01T00:00:00.000Z",
  lastSeen: "2026-10-08T12:00:00.000Z",
  totalSpendUsd: 1.2345,
};

const unreported: InventoryItem = {
  agentId: "bot2",
  ownerId: "alice",
  model: null,
  firstSeen: null,
  lastSeen: null,
  totalSpendUsd: 0.0,
};

describe("InventoryTable", () => {
  it("shows agentId, model, last activity, and total spend", () => {
    render(<InventoryTable agents={[reported]} />);
    const row = screen.getByText("bot1").closest("tr")!;
    const cells = within(row);
    expect(cells.getByText("anthropic.claude-3-sonnet")).toBeInTheDocument();
    expect(cells.getByText(/1\.23/)).toBeInTheDocument();
  });

  it.each([
    [0.0006, "$0.0006"],
    [0.00004, "<$0.0001"],
    [0, "$0.0000"],
    [0.01, "$0.0100"],
    [1.23456, "$1.2346"],
  ])("formats total spend %s as %s", (usd, expected) => {
    render(<InventoryTable agents={[{ ...reported, totalSpendUsd: usd }]} />);
    const row = screen.getByText("bot1").closest("tr")!;
    const spendCell = within(row).getAllByRole("cell")[3];
    expect(spendCell).toHaveTextContent(expected);
    expect(spendCell.textContent).toBe(expected);
  });

  it("links each row to the agent detail page", () => {
    render(<InventoryTable agents={[reported]} />);
    const link = screen.getByRole("link", { name: /bot1/ });
    expect(link).toHaveAttribute("href", "/agent?id=bot1");
  });

  it("marks unreported agents and leaves the model cell empty", () => {
    render(<InventoryTable agents={[unreported]} />);
    const row = screen.getByText("bot2").closest("tr")!;
    expect(within(row).getByText(/not yet reported/i)).toBeInTheDocument();
  });
});

describe("InventoryTable Status column", () => {
  it.each([
    [true, "Paused"],
    [false, "Active"],
    [undefined, "Active"],
  ])("paused=%s shows %s", (paused, expected) => {
    render(<InventoryTable agents={[{ ...reported, paused }]} />);
    expect(screen.getByRole("columnheader", { name: "Status" })).toBeInTheDocument();
    const row = screen.getByText("bot1").closest("tr")!;
    const statusCell = within(row).getAllByRole("cell")[4];
    expect(statusCell.textContent).toBe(expected);
  });
});

describe("InventoryTable stale marker", () => {
  const NOW = Date.parse("2026-10-17T15:00:00.000Z");
  const lastCell = () => within(screen.getByText("bot1").closest("tr")!).getAllByRole("cell")[2];

  it("shows 'stale' when last activity is older than 24 h", () => {
    render(<InventoryTable agents={[{ ...reported, lastSeen: "2026-10-16T14:59:59.000Z" }]} now={NOW} />);
    expect(lastCell()).toHaveTextContent("stale");
  });

  it("does not show 'stale' for recent activity", () => {
    render(<InventoryTable agents={[{ ...reported, lastSeen: "2026-10-17T14:00:00.000Z" }]} now={NOW} />);
    expect(lastCell()).not.toHaveTextContent("stale");
  });

  it("leaves 'not yet reported' unchanged", () => {
    render(<InventoryTable agents={[unreported]} now={NOW} />);
    const cell = within(screen.getByText("bot2").closest("tr")!).getAllByRole("cell")[2];
    expect(cell.textContent).toBe("not yet reported");
  });
});


describe("InventoryTable empty state (audit fix)", () => {
  it("explains an empty list instead of showing a bare header", () => {
    render(<InventoryTable agents={[]} />);
    expect(
      screen.getByText("No agents for these credentials. Check the key, or run an agent once.")
    ).toBeInTheDocument();
  });

  it("does not show the empty message when there are agents", () => {
    render(<InventoryTable agents={[reported]} />);
    expect(screen.queryByText(/no agents for these credentials/i)).not.toBeInTheDocument();
  });
});

describe("InventoryTable wrapping", () => {
  it("keeps short agent ids and model ids on one line", () => {
    render(<InventoryTable agents={[{ ...reported, agentId: "demo-bot", model: "claude-haiku-4-5" }]} />);
    expect(screen.getByRole("link", { name: "demo-bot" }).className).toMatch(/\bwhitespace-nowrap\b/);
    expect(screen.getByText("claude-haiku-4-5").className).toMatch(/\bwhitespace-nowrap\b/);
  });

  it("a 128-char agent id can wrap, so it can't push the page wider than 375px", () => {
    const long = "a".repeat(128);
    render(<InventoryTable agents={[{ ...reported, agentId: long }]} />);
    const link = screen.getByRole("link", { name: long });
    expect(link.className).toContain("[overflow-wrap:anywhere]");
    expect(link.className).not.toMatch(/\bwhitespace-nowrap\b|\bbreak-all\b/);
    // Anything still too wide scrolls inside the table wrapper, never the page.
    expect(link.closest("table")!.parentElement!.className).toMatch(/\boverflow-auto\b/);
  });
});
