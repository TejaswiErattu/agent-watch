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
