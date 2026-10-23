import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";

let searchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useSearchParams: () => searchParams,
  useRouter: () => ({ push: vi.fn() }),
}));

// Child components that fetch on their own are stubbed; RulesEditor exposes onSaved.
vi.mock("@/components/Timeline", () => ({
  Timeline: ({ agentId }: { agentId: string }) => (
    <div data-testid="timeline">timeline {agentId}</div>
  ),
}));
vi.mock("@/components/RulesEditor", () => ({
  RulesEditor: ({ agentId, onSaved }: { agentId: string; onSaved?: () => void }) => (
    <div data-testid="rules">
      rules {agentId}
      <button type="button" onClick={() => onSaved?.()}>
        fake save
      </button>
    </div>
  ),
}));

const getStatus = vi.fn();
const putStatus = vi.fn();
const getSpend = vi.fn();
const getConfig = vi.fn();
const getTimeline = vi.fn();
vi.mock("@/lib/api", async () => ({
  AuthError: (await vi.importActual<typeof import("@/lib/api")>("@/lib/api")).AuthError,
  getStatus: (...a: unknown[]) => getStatus(...a),
  putStatus: (...a: unknown[]) => putStatus(...a),
  getSpend: (...a: unknown[]) => getSpend(...a),
  getConfig: (...a: unknown[]) => getConfig(...a),
  getTimeline: (...a: unknown[]) => getTimeline(...a),
}));

import userEvent from "@testing-library/user-event";
import AgentPage from "./page";
import { saveCredentials } from "@/lib/credentials";

const CREDS = { ownerId: "alice", keyHash: "a".repeat(64) };

beforeEach(() => {
  localStorage.clear();
  searchParams = new URLSearchParams();
  for (const f of [getStatus, putStatus, getSpend, getConfig, getTimeline]) f.mockReset();
  getStatus.mockResolvedValue({ agentId: "bot1", paused: false, pausedAt: null });
  getSpend.mockResolvedValue({
    agentId: "bot1",
    rollingSpendUsd: 0.0025,
    windowStart: "x",
    windowEnd: "y",
  });
  getConfig.mockResolvedValue({
    guardrails: { dailySpendCapUsd: 0.01, blockedPaths: [], blockedCommands: [] },
  });
  getTimeline.mockResolvedValue({ events: [], nextCursor: null });
});

afterEach(() => {
  vi.useRealTimers();
});

function open() {
  saveCredentials(CREDS);
  searchParams = new URLSearchParams("id=bot1");
  return render(<AgentPage />);
}

describe("agent detail page", () => {
  it("renders Timeline and RulesEditor for the id", async () => {
    open();
    expect(await screen.findByTestId("timeline")).toHaveTextContent("bot1");
    expect(screen.getByTestId("rules")).toHaveTextContent("bot1");
  });

  it("loads status, spend, config, and window events and renders the tile and chart above the rules", async () => {
    const { container } = open();
    expect(await screen.findByRole("progressbar")).toHaveAttribute("aria-valuenow", "25");
    expect(getStatus).toHaveBeenCalledWith(CREDS, "bot1");
    expect(getSpend).toHaveBeenCalledWith(CREDS, "bot1");
    expect(getConfig).toHaveBeenCalledWith(CREDS, "bot1");
    const types = getTimeline.mock.calls.map((c) => c[2]?.type);
    expect(types).toContain("llm_call");
    expect(types).toContain("blocked");
    expect(container.querySelectorAll("rect[data-bar]")).toHaveLength(24);
    const summary = screen.getByTestId("agent-summary");
    const rules = screen.getByTestId("rules");
    expect(summary.compareDocumentPosition(rules) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("renders the pause state from getStatus", async () => {
    getStatus.mockResolvedValue({ agentId: "bot1", paused: true, pausedAt: "2026-10-14T12:00:00.000Z" });
    open();
    expect(await screen.findByRole("button", { name: "Resume agent" })).toBeInTheDocument();
    expect(screen.getByTestId("pause-state")).toHaveTextContent("Paused");
    expect(screen.getByTestId("summary-status")).toHaveTextContent("Paused");
  });

  it("refetches after a pause", async () => {
    const user = userEvent.setup();
    const pausedRes = { agentId: "bot1", paused: true, pausedAt: "2026-10-14T12:00:00.000Z" };
    putStatus.mockResolvedValue(pausedRes);
    open();
    expect(await screen.findByTestId("pause-state")).toHaveTextContent("Active");

    getStatus.mockResolvedValue(pausedRes);
    await user.click(screen.getByRole("button", { name: "Pause agent" }));
    await user.click(screen.getByRole("button", { name: "Confirm pause" }));

    expect(await screen.findByRole("button", { name: "Resume agent" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("pause-state")).toHaveTextContent("Paused"));
    expect(getStatus).toHaveBeenCalledTimes(2);
  });

  it("refetches after a rules save", async () => {
    const user = userEvent.setup();
    open();
    await screen.findByRole("progressbar");
    expect(getSpend).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "fake save" }));
    await waitFor(() => expect(getSpend).toHaveBeenCalledTimes(2));
    expect(getConfig).toHaveBeenCalledTimes(2);
  });

  it("refreshes every 30 s and stops after unmount", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { unmount } = open();
    await waitFor(() => expect(getSpend).toHaveBeenCalledTimes(1));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    await waitFor(() => expect(getSpend).toHaveBeenCalledTimes(2));
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(getSpend).toHaveBeenCalledTimes(2);
  });

  it("shows a message and a link back when id is missing", async () => {
    saveCredentials(CREDS);
    render(<AgentPage />);
    expect(await screen.findByText(/no agent selected/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back/i })).toHaveAttribute("href", "/");
  });

  it("shows the credentials form when there are no credentials", async () => {
    searchParams = new URLSearchParams("id=bot1");
    render(<AgentPage />);
    expect(await screen.findByLabelText(/api key/i)).toBeInTheDocument();
  });
});


describe("agent page audit fixes", () => {
  it("on AuthError shows Clear credentials, which returns to the credentials form", async () => {
    const { AuthError } = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
    getStatus.mockRejectedValue(new AuthError());
    const user = userEvent.setup();
    open();
    const clear = await screen.findByRole("button", { name: "Clear credentials" });
    expect(screen.getByRole("alert")).toHaveTextContent("Credentials not accepted");
    await user.click(clear);
    expect(localStorage.getItem("agentwatch.credentials")).toBeNull();
    expect(await screen.findByLabelText(/api key/i)).toBeInTheDocument();
  });

  it("does not show Clear credentials for a non-auth error", async () => {
    getStatus.mockRejectedValue(new Error("network down"));
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("network down");
    expect(screen.queryByRole("button", { name: "Clear credentials" })).not.toBeInTheDocument();
  });

  it("a long agent id wraps in the heading and the header row wraps", async () => {
    const long = "a".repeat(128);
    saveCredentials(CREDS);
    searchParams = new URLSearchParams(`id=${long}`);
    render(<AgentPage />);
    const h1 = await screen.findByRole("heading", { level: 1, name: long });
    expect(h1.className).toContain("[overflow-wrap:anywhere]");
    expect(h1.className).not.toMatch(/\bbreak-all\b/);
    expect(h1.className).toMatch(/\bmin-w-0\b/);
    expect(h1.parentElement!.className).toMatch(/\bflex-wrap\b/);
  });
});
