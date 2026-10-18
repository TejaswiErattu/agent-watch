import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SpendChart, yMax } from "./SpendChart";
import type { SpendBucket } from "@/lib/types";

const START = Date.parse("2026-10-16T15:00:00.000Z");

function buckets(over: Partial<Record<number, Partial<SpendBucket>>> = {}): SpendBucket[] {
  return Array.from({ length: 24 }, (_, i) => ({
    start: new Date(START + i * 3_600_000).toISOString(),
    costUsd: 0,
    llmCalls: 0,
    blocked: 0,
    ...(over[i] ?? {}),
  }));
}

describe("SpendChart", () => {
  it("renders 24 bars, each with an accessible title", () => {
    const { container } = render(
      <SpendChart buckets={buckets({ 23: { costUsd: 0.0012, llmCalls: 2, blocked: 1 } })} capUsd={null} />
    );
    const bars = container.querySelectorAll("rect[data-bar]");
    expect(bars).toHaveLength(24);
    const titles = Array.from(bars).map((b) => b.querySelector("title")?.textContent);
    expect(titles.every((t) => /^\d{2}:00: (\$\d+\.\d{4}|<\$0\.0001), \d+ blocked$/.test(t ?? ""))).toBe(true);
    expect(titles[23]).toMatch(/: \$0\.0012, 1 blocked$/);
    expect(titles[0]).toMatch(/: \$0\.0000, 0 blocked$/);
  });

  it("marks buckets with blocks with the count", () => {
    const { container } = render(
      <SpendChart buckets={buckets({ 5: { blocked: 3 }, 20: { blocked: 1, costUsd: 0.001 } })} capUsd={null} />
    );
    const markers = container.querySelectorAll("[data-blocked-marker]");
    expect(markers).toHaveLength(2);
    expect(Array.from(markers).map((m) => m.textContent)).toEqual(["3", "1"]);
  });

  it("shows the axis and an empty message when there is nothing to show", () => {
    const { container } = render(<SpendChart buckets={buckets()} capUsd={0.5} />);
    expect(screen.getByText("No LLM calls in the last 24 hours")).toBeInTheDocument();
    expect(container.querySelector("[data-axis]")).not.toBeNull();
  });

  it("does not show the empty message when a bucket has only blocks", () => {
    render(<SpendChart buckets={buckets({ 3: { blocked: 1 } })} capUsd={null} />);
    expect(screen.queryByText("No LLM calls in the last 24 hours")).toBeNull();
  });

  it("uses at least cap/24 as the y-axis max", () => {
    expect(yMax(buckets({ 1: { costUsd: 0.001 } }), 2.4)).toBeCloseTo(0.1, 9);
    expect(yMax(buckets({ 1: { costUsd: 0.5 } }), 2.4)).toBeCloseTo(0.5, 9);
    expect(yMax(buckets({ 1: { costUsd: 0.5 } }), null)).toBeCloseTo(0.5, 9);
    expect(yMax(buckets(), null)).toBeGreaterThan(0);
  });
});
