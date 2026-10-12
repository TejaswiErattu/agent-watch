import { describe, it, expect } from "vitest";
import { inventoryStats } from "./stats";
import type { InventoryItem } from "./types";

const NOW = Date.parse("2026-10-12T12:00:00.000Z");
const HOUR = 3_600_000;

function agent(id: string, lastSeenMsAgo: number | null, spend: number): InventoryItem {
  const lastSeen = lastSeenMsAgo === null ? null : new Date(NOW - lastSeenMsAgo).toISOString();
  return {
    agentId: id,
    ownerId: "alice",
    model: lastSeen ? "claude" : null,
    firstSeen: lastSeen,
    lastSeen,
    totalSpendUsd: spend,
  };
}

describe("inventoryStats", () => {
  it("returns zeros for an empty inventory", () => {
    expect(inventoryStats([], NOW)).toEqual({
      agents: 0,
      totalSpendUsd: 0,
      activeLast24h: 0,
      notYetReported: 0,
    });
  });

  it("counts every agent as not yet reported when all lastSeen are null", () => {
    const s = inventoryStats([agent("a", null, 0), agent("b", null, 0)], NOW);
    expect(s).toEqual({ agents: 2, totalSpendUsd: 0, activeLast24h: 0, notYetReported: 2 });
  });

  it("sums spend and splits active vs stale vs unreported", () => {
    const s = inventoryStats(
      [
        agent("recent", 1 * HOUR, 0.1),
        agent("edge", 24 * HOUR, 0.2), // exactly 24h ago counts as active
        agent("stale", 25 * HOUR, 0.0006),
        agent("new", null, 0),
      ],
      NOW
    );
    expect(s.agents).toBe(4);
    expect(s.totalSpendUsd).toBeCloseTo(0.3006, 10);
    expect(s.activeLast24h).toBe(2);
    expect(s.notYetReported).toBe(1);
  });

  it("does not count an unparsable lastSeen as active", () => {
    const bad = { ...agent("x", 0, 0), lastSeen: "not-a-date" };
    expect(inventoryStats([bad], NOW).activeLast24h).toBe(0);
  });
});
