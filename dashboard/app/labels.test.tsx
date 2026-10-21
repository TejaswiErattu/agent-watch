// Guard for the visual restyle: every visible label, heading, and button the
// DEMO_SCRIPT and users rely on must still render with the same text and roles.
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

let searchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useSearchParams: () => searchParams,
  useRouter: () => ({ push: vi.fn() }),
}));

const api = vi.hoisted(() => ({
  getInventory: vi.fn(),
  getStatus: vi.fn(),
  getSpend: vi.fn(),
  getConfig: vi.fn(),
  getTimeline: vi.fn(),
  putStatus: vi.fn(),
  putConfig: vi.fn(),
}));
vi.mock("@/lib/api", async () => ({
  ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")),
  ...api,
}));

import Home from "./page";
import AgentPage from "./agent/page";
import { saveCredentials } from "@/lib/credentials";

class IO {
  observe() {}
  disconnect() {}
}

beforeEach(() => {
  localStorage.clear();
  searchParams = new URLSearchParams();
  Object.values(api).forEach((f) => f.mockReset());
  vi.stubGlobal("IntersectionObserver", IO);
  api.getInventory.mockResolvedValue({
    agents: [
      {
        agentId: "bot1",
        ownerId: "alice",
        model: "m",
        firstSeen: "2026-10-01T00:00:00.000Z",
        lastSeen: "2026-10-01T00:00:00.000Z",
        totalSpendUsd: 0.5,
      },
    ],
  });
  api.getStatus.mockResolvedValue({ agentId: "bot1", paused: false, pausedAt: null });
  api.getSpend.mockResolvedValue({ agentId: "bot1", rollingSpendUsd: 0.02, windowStart: "x", windowEnd: "y" });
  api.getConfig.mockResolvedValue({
    guardrails: { dailySpendCapUsd: 0.01, blockedPaths: [".env"], blockedCommands: ["sudo"] },
  });
  api.getTimeline.mockResolvedValue({ events: [], nextCursor: null });
});

describe("labels survive the restyle", () => {
  it("credentials form", () => {
    render(<Home />);
    expect(screen.getByRole("heading", { level: 1, name: "Agent Watch" })).toBeInTheDocument();
    expect(screen.getByLabelText("Owner ID")).toBeInTheDocument();
    expect(screen.getByLabelText("API key")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save credentials" })).toBeInTheDocument();
  });

  it("inventory page", async () => {
    saveCredentials({ ownerId: "alice", keyHash: "a".repeat(64) });
    render(<Home />);
    expect(await screen.findByRole("link", { name: "bot1" })).toHaveAttribute("href", "/agent?id=bot1");
    expect(screen.getByRole("heading", { level: 1, name: "Agent Watch" })).toBeInTheDocument();
    for (const col of ["Agent", "Model", "Last activity", "Total spend", "Status"]) {
      expect(screen.getByRole("columnheader", { name: col })).toBeInTheDocument();
    }
    expect(screen.getByLabelText("Agent ID")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear credentials" })).toBeInTheDocument();
    expect(screen.getByText("stale")).toBeInTheDocument();
  });

  it("agent page", async () => {
    saveCredentials({ ownerId: "alice", keyHash: "a".repeat(64) });
    searchParams = new URLSearchParams("id=bot1");
    render(<AgentPage />);
    expect(await screen.findByRole("button", { name: "Save rules" })).toBeEnabled();
    expect(screen.getByRole("heading", { level: 1, name: "bot1" })).toBeInTheDocument();
    for (const h of ["Overview", "Status", "Rules", "Timeline"]) {
      expect(screen.getByRole("heading", { level: 2, name: h })).toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: "Back to inventory" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("progressbar", { name: "Spend against daily cap" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "LLM spend per hour, last 24 hours" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Pause agent" })).toBeInTheDocument();
    expect(screen.getByLabelText("Daily spend cap (USD)")).toBeInTheDocument();
    expect(screen.getByText("Blocked paths")).toBeInTheDocument();
    expect(screen.getByText("Blocked commands (regex, case-insensitive)")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Add path" })).toHaveLength(1);
    expect(screen.getByLabelText("Add path")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add pattern" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add presets" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove .env" })).toHaveTextContent("Remove");
    expect(screen.getByRole("button", { name: "Remove pattern sudo" })).toHaveTextContent("Remove");
    expect(screen.getByLabelText("Filter")).toBeInTheDocument();
  });
});
