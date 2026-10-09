import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import {
  apiFetch,
  AuthError,
  ApiError,
  getInventory,
  getTimeline,
  getConfig,
  putConfig,
} from "./api";
import type { Credentials } from "./credentials";

const creds: Credentials = { ownerId: "alice", keyHash: "a".repeat(64) };

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response);
  vi.stubGlobal("fetch", fn);
  return fn;
}

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("apiFetch", () => {
  it("adds the credential headers", async () => {
    const fn = mockFetch(200, { ok: true });
    await apiFetch("/agents", creds);
    const [, init] = fn.mock.calls[0];
    const headers = init.headers as Record<string, string>;
    expect(headers["x-agentwatch-owner"]).toBe("alice");
    expect(headers["x-agentwatch-key-hash"]).toBe("a".repeat(64));
  });

  it("throws AuthError on 401", async () => {
    mockFetch(401, { error: "unauthorized" });
    await expect(apiFetch("/agents", creds)).rejects.toBeInstanceOf(AuthError);
  });

  it("throws AuthError on 403", async () => {
    mockFetch(403, { error: "forbidden" });
    await expect(apiFetch("/agents", creds)).rejects.toBeInstanceOf(AuthError);
  });

  it("throws ApiError with the server message on other non-2xx", async () => {
    mockFetch(400, { error: "bad limit" });
    await expect(apiFetch("/agents", creds)).rejects.toThrowError("bad limit");
    try {
      mockFetch(400, { error: "bad limit" });
      await apiFetch("/agents", creds);
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError);
    }
  });
});

describe("endpoint builders", () => {
  it("getInventory hits /agents", async () => {
    const fn = mockFetch(200, { agents: [] });
    await getInventory(creds);
    expect(fn.mock.calls[0][0]).toBe("https://api.example.com/agents");
  });

  it("getTimeline builds the query string", async () => {
    const fn = mockFetch(200, { events: [], nextCursor: null });
    await getTimeline(creds, "bot1", {
      order: "desc",
      type: "blocked",
      cursor: "abc",
      limit: 25,
    });
    const url = fn.mock.calls[0][0] as string;
    expect(url).toContain("/agents/bot1/events?");
    expect(url).toContain("order=desc");
    expect(url).toContain("type=blocked");
    expect(url).toContain("cursor=abc");
    expect(url).toContain("limit=25");
  });

  it("getConfig hits the config route", async () => {
    const fn = mockFetch(200, { guardrails: { dailySpendCapUsd: null, blockedPaths: [] } });
    await getConfig(creds, "bot1");
    expect(fn.mock.calls[0][0]).toBe("https://api.example.com/agents/bot1/config");
  });

  it("putConfig sends the config as the JSON body with PUT", async () => {
    const fn = mockFetch(200, { guardrails: { dailySpendCapUsd: 1, blockedPaths: [".env"] } });
    await putConfig(creds, "bot1", { dailySpendCapUsd: 1, blockedPaths: [".env"] });
    const [url, init] = fn.mock.calls[0];
    expect(url).toBe("https://api.example.com/agents/bot1/config");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({
      dailySpendCapUsd: 1,
      blockedPaths: [".env"],
    });
  });
});
