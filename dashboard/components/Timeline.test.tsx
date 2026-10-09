import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { TimelineItem } from "@/lib/types";

const getTimeline = vi.fn();
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, getTimeline: (...args: unknown[]) => getTimeline(...args) };
});

import { Timeline } from "./Timeline";
import type { Credentials } from "@/lib/credentials";

const creds: Credentials = { ownerId: "alice", keyHash: "a".repeat(64) };

function ev(partial: Partial<TimelineItem>): TimelineItem {
  return {
    ts: "2026-10-08T12:00:00.000Z",
    eventId: Math.random().toString(16).slice(2),
    type: "llm_call",
    model: null,
    tool: null,
    target: null,
    inputTokens: null,
    outputTokens: null,
    costUsd: null,
    violationType: null,
    attemptedCostUsd: null,
    attemptedPath: null,
    meta: null,
    ...partial,
  };
}

// Capture the IntersectionObserver callback so tests can fire it.
let ioCallback: IntersectionObserverCallback | null = null;
class FakeIO {
  constructor(cb: IntersectionObserverCallback) {
    ioCallback = cb;
  }
  observe() {}
  disconnect() {}
  unobserve() {}
}

beforeEach(() => {
  getTimeline.mockReset();
  ioCallback = null;
  vi.stubGlobal("IntersectionObserver", FakeIO as unknown as typeof IntersectionObserver);
});

describe("Timeline", () => {
  it("renders mixed events in the returned order", async () => {
    getTimeline.mockResolvedValue({
      events: [
        ev({ type: "blocked", attemptedPath: ".env" }),
        ev({ type: "tool_call", tool: "read_file" }),
        ev({ type: "llm_call", model: "claude" }),
      ],
      nextCursor: null,
    });
    render(<Timeline creds={creds} agentId="bot1" />);
    await waitFor(() => expect(getTimeline).toHaveBeenCalled());
    expect(await screen.findByText(/\.env/)).toBeInTheDocument();
    expect(screen.getByText(/read_file/)).toBeInTheDocument();
    expect(screen.getByText(/claude/)).toBeInTheDocument();
    // desc order by default
    expect(getTimeline.mock.calls[0][2]).toMatchObject({ order: "desc" });
  });

  it("resets the list and passes the type when the filter changes", async () => {
    getTimeline.mockResolvedValue({ events: [ev({})], nextCursor: null });
    const user = userEvent.setup();
    render(<Timeline creds={creds} agentId="bot1" />);
    await waitFor(() => expect(getTimeline).toHaveBeenCalledTimes(1));

    getTimeline.mockResolvedValue({
      events: [ev({ type: "blocked", attemptedPath: ".env" })],
      nextCursor: null,
    });
    await user.selectOptions(screen.getByLabelText(/filter/i), "blocked");
    await waitFor(() => {
      const last = getTimeline.mock.calls.at(-1)!;
      expect(last[2]).toMatchObject({ type: "blocked" });
    });
  });

  it("loads and appends the next page when the sentinel intersects", async () => {
    getTimeline.mockResolvedValueOnce({
      events: [ev({ model: "page1" })],
      nextCursor: "cursor1",
    });
    render(<Timeline creds={creds} agentId="bot1" />);
    await screen.findByText(/page1/);

    getTimeline.mockResolvedValueOnce({
      events: [ev({ model: "page2" })],
      nextCursor: null,
    });
    ioCallback!(
      [{ isIntersecting: true } as IntersectionObserverEntry],
      {} as IntersectionObserver
    );
    expect(await screen.findByText(/page2/)).toBeInTheDocument();
    expect(screen.getByText(/page1/)).toBeInTheDocument();
  });

  it("does not load more when nextCursor is null", async () => {
    getTimeline.mockResolvedValue({ events: [ev({})], nextCursor: null });
    render(<Timeline creds={creds} agentId="bot1" />);
    await waitFor(() => expect(getTimeline).toHaveBeenCalledTimes(1));
    ioCallback!(
      [{ isIntersecting: true } as IntersectionObserverEntry],
      {} as IntersectionObserver
    );
    // No extra call.
    await new Promise((r) => setTimeout(r, 20));
    expect(getTimeline).toHaveBeenCalledTimes(1);
  });
});
