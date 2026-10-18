import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AgentSummary, capPercent } from "./AgentSummary";
import type { SpendResponse, StatusResponse } from "@/lib/types";

const NOW = Date.parse("2026-10-17T15:00:00.000Z");
const spend = (usd: number): SpendResponse => ({
  agentId: "bot1",
  rollingSpendUsd: usd,
  windowStart: "2026-10-16T15:00:00.000Z",
  windowEnd: "2026-10-17T15:00:00.000Z",
});
const active: StatusResponse = { agentId: "bot1", paused: false, pausedAt: null };

describe("AgentSummary", () => {
  it("shows spend with 4 decimals and 'no cap' with no progress bar", () => {
    render(<AgentSummary spend={spend(0.0006)} capUsd={null} status={active} lastSeen={null} now={NOW} />);
    expect(screen.getByTestId("summary-spend")).toHaveTextContent("$0.0006");
    expect(screen.getByTestId("summary-cap")).toHaveTextContent("no cap");
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("shows the cap and a progressbar with aria-valuenow = spend/cap", () => {
    render(<AgentSummary spend={spend(0.0025)} capUsd={0.01} status={active} lastSeen={null} now={NOW} />);
    expect(screen.getByTestId("summary-cap")).toHaveTextContent("of $0.0100 cap");
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "25");
    expect(screen.getByTestId("cap-bar").className).not.toMatch(/red/);
  });

  it("clamps at 100 and turns red at or over the cap", () => {
    render(<AgentSummary spend={spend(0.02)} capUsd={0.01} status={active} lastSeen={null} now={NOW} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
    expect(screen.getByTestId("cap-bar").className).toMatch(/bg-red/);
  });

  it("capPercent handles exact cap and a zero cap", () => {
    expect(capPercent(0.01, 0.01)).toBe(100);
    expect(capPercent(0, 0)).toBe(100);
    expect(capPercent(0.005, 0.01)).toBe(50);
  });

  it("shows the pause state and relative last activity with the exact ts as title", () => {
    const ts = new Date(NOW - 5 * 60_000).toISOString();
    render(
      <AgentSummary
        spend={spend(0)}
        capUsd={null}
        status={{ agentId: "bot1", paused: true, pausedAt: ts }}
        lastSeen={ts}
        now={NOW}
      />
    );
    expect(screen.getByTestId("summary-status")).toHaveTextContent("Paused");
    const last = screen.getByTestId("summary-last");
    expect(last).toHaveTextContent("5 min ago");
    expect(last).toHaveAttribute("title", ts);
  });
});
