import { describe, it, expect, vi, afterEach } from "vitest";
import { bucketSpend, fetchWindow, HOUR_MS } from "./spend";
import type { TimelineItem } from "./types";
import type { Credentials } from "./credentials";

const creds: Credentials = { ownerId: "alice", keyHash: "a".repeat(64) };
const END = Date.parse("2026-10-17T15:00:00.000Z");
const iso = (ms: number) => new Date(ms).toISOString();

function ev(ts: string | null, partial: Partial<TimelineItem> = {}): TimelineItem {
  return {
    ts,
    eventId: Math.random().toString(16).slice(2),
    type: "llm_call",
    model: "m",
    tool: null,
    target: null,
    inputTokens: 1,
    outputTokens: 1,
    costUsd: 0.001,
    violationType: null,
    attemptedCostUsd: null,
    attemptedPath: null,
    attemptedCommand: null,
    meta: null,
    ...partial,
  };
}

// Small seeded PRNG (mulberry32) so the randomized test is reproducible.
function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

describe("bucketSpend", () => {
  it("returns 24 hourly buckets ending at windowEnd", () => {
    const b = bucketSpend([], [], END);
    expect(b).toHaveLength(24);
    expect(b[0].start).toBe(iso(END - 24 * HOUR_MS));
    expect(b[23].start).toBe(iso(END - HOUR_MS));
    expect(b.every((x) => x.costUsd === 0 && x.llmCalls === 0 && x.blocked === 0)).toBe(true);
  });

  it("excludes events exactly at the window start and includes the window end", () => {
    const b = bucketSpend(
      [ev(iso(END - 24 * HOUR_MS), { costUsd: 5 }), ev(iso(END), { costUsd: 0.25 })],
      [],
      END
    );
    expect(b.reduce((s, x) => s + x.costUsd, 0)).toBeCloseTo(0.25, 9);
    expect(b[23].costUsd).toBeCloseTo(0.25, 9);
    expect(b[23].llmCalls).toBe(1);
  });

  it("puts an event on a bucket boundary in the earlier bucket (start exclusive)", () => {
    const b = bucketSpend([ev(iso(END - HOUR_MS))], [], END);
    expect(b[22].llmCalls).toBe(1);
    expect(b[23].llmCalls).toBe(0);
  });

  it("counts blocked events per bucket and ignores null ts and null cost", () => {
    const b = bucketSpend(
      [ev(null), ev(iso(END - 10), { costUsd: null })],
      [ev(iso(END - 30 * 60_000), { type: "blocked" }), ev(iso(END - 2.5 * HOUR_MS), { type: "blocked" })],
      END
    );
    expect(b[23].blocked).toBe(1);
    expect(b[21].blocked).toBe(1);
    expect(b[23].llmCalls).toBe(1);
    expect(b[23].costUsd).toBe(0);
  });

  it("sum of buckets equals the in-window event sum and each event lands once (200 seeded runs)", () => {
    const rand = rng(42);
    for (let run = 0; run < 200; run++) {
      const n = Math.floor(rand() * 60);
      const events: TimelineItem[] = [];
      for (let i = 0; i < n; i++) {
        // Spread across 26 h so some events fall outside the window.
        const offset = Math.floor(rand() * 26 * HOUR_MS) - HOUR_MS;
        events.push(ev(iso(END - offset), { costUsd: Math.round(rand() * 1e6) / 1e6 }));
      }
      const inWindow = events.filter((e) => {
        const t = Date.parse(e.ts!);
        return t > END - 24 * HOUR_MS && t <= END;
      });
      const b = bucketSpend(events, [], END);
      const bucketSum = b.reduce((s, x) => s + x.costUsd, 0);
      const eventSum = inWindow.reduce((s, e) => s + (e.costUsd ?? 0), 0);
      expect(Math.abs(bucketSum - eventSum)).toBeLessThan(1e-6);
      expect(b.reduce((s, x) => s + x.llmCalls, 0)).toBe(inWindow.length);
    }
  });
});

describe("fetchWindow", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function stubPages(pages: { events: TimelineItem[]; nextCursor: string | null }[]) {
    const fn = vi.fn();
    for (const p of pages) {
      fn.mockResolvedValueOnce({ ok: true, status: 200, json: async () => p } as Response);
    }
    // Any extra call returns another non-empty page with a cursor (to catch over-fetching).
    fn.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ events: [ev(iso(END - 60_000))], nextCursor: "more" }),
    } as Response);
    vi.stubGlobal("fetch", fn);
    return fn;
  }

  const since = iso(END - 24 * HOUR_MS);

  it("follows nextCursor and requests desc pages of the given type", async () => {
    const fn = stubPages([
      { events: [ev(iso(END - 1000))], nextCursor: "c1" },
      { events: [ev(iso(END - 2000))], nextCursor: null },
    ]);
    const out = await fetchWindow(creds, "bot1", "llm_call", since);
    expect(out).toHaveLength(2);
    expect(fn).toHaveBeenCalledTimes(2);
    const first = fn.mock.calls[0][0] as string;
    expect(first).toContain("order=desc");
    expect(first).toContain("type=llm_call");
    expect(fn.mock.calls[1][0] as string).toContain("cursor=c1");
  });

  it("tolerates an empty page that still has a cursor", async () => {
    const fn = stubPages([
      { events: [], nextCursor: "c1" },
      { events: [ev(iso(END - 1000))], nextCursor: null },
    ]);
    const out = await fetchWindow(creds, "bot1", "blocked", since);
    expect(out).toHaveLength(1);
    expect(fn).toHaveBeenCalledTimes(2);
  });

  it("stops when a page's oldest ts is older than since and drops out-of-window events", async () => {
    const fn = stubPages([
      { events: [ev(iso(END - 1000)), ev(iso(END - 25 * HOUR_MS))], nextCursor: "c1" },
    ]);
    const out = await fetchWindow(creds, "bot1", "llm_call", since);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(out.map((e) => e.ts)).toEqual([iso(END - 1000)]);
  });

  it("stops after maxPages (default 20)", async () => {
    const fn = stubPages([]);
    const out = await fetchWindow(creds, "bot1", "llm_call", since);
    expect(fn).toHaveBeenCalledTimes(20);
    expect(out).toHaveLength(20);
  });
});
