import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatTiles } from "./StatTiles";
import type { InventoryItem } from "@/lib/types";

const NOW = Date.parse("2026-10-12T12:00:00.000Z");

const items: InventoryItem[] = [
  {
    agentId: "bot1",
    ownerId: "alice",
    model: "claude",
    firstSeen: "2026-10-12T10:00:00.000Z",
    lastSeen: "2026-10-12T11:00:00.000Z",
    totalSpendUsd: 0.0006,
  },
  {
    agentId: "bot2",
    ownerId: "alice",
    model: null,
    firstSeen: null,
    lastSeen: null,
    totalSpendUsd: 0,
  },
];

function tile(name: string) {
  return screen.getByRole("group", { name });
}

describe("StatTiles", () => {
  it("renders the four tiles computed from the inventory", () => {
    render(<StatTiles agents={items} now={NOW} />);
    expect(tile("Agents")).toHaveTextContent("2");
    expect(tile("Total spend")).toHaveTextContent("$0.0006");
    expect(tile("Active in last 24h")).toHaveTextContent("1");
    expect(tile("Not yet reported")).toHaveTextContent("1");
  });

  it("renders zeros for an empty inventory", () => {
    render(<StatTiles agents={[]} now={NOW} />);
    expect(tile("Agents")).toHaveTextContent("0");
    expect(tile("Total spend")).toHaveTextContent("$0.0000");
    expect(tile("Active in last 24h")).toHaveTextContent("0");
    expect(tile("Not yet reported")).toHaveTextContent("0");
  });
});
