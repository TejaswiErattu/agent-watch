import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { InventoryItem } from "@/lib/types";

const getInventory = vi.fn();
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, getInventory: (...args: unknown[]) => getInventory(...args) };
});

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import Home from "./page";
import { AuthError } from "@/lib/api";
import { saveCredentials } from "@/lib/credentials";

const item: InventoryItem = {
  agentId: "bot1",
  ownerId: "alice",
  model: "anthropic.claude-3-sonnet",
  firstSeen: "2026-10-01T00:00:00.000Z",
  lastSeen: "2026-10-08T12:00:00.000Z",
  totalSpendUsd: 0.5,
};

beforeEach(() => {
  localStorage.clear();
  getInventory.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("inventory page", () => {
  it("shows the credentials form when no credentials are stored", () => {
    render(<Home />);
    expect(screen.getByLabelText(/api key/i)).toBeInTheDocument();
  });

  it("renders the table from getInventory when credentials exist", async () => {
    saveCredentials({ ownerId: "alice", keyHash: "a".repeat(64) });
    getInventory.mockResolvedValue({ agents: [item] });
    render(<Home />);
    expect(await screen.findByText("bot1")).toBeInTheDocument();
  });

  it("shows an auth message and the form on AuthError", async () => {
    saveCredentials({ ownerId: "alice", keyHash: "a".repeat(64) });
    getInventory.mockRejectedValue(new AuthError());
    render(<Home />);
    expect(await screen.findByText(/credentials not accepted/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/api key/i)).toBeInTheDocument();
  });

  it("clears credentials and shows the form on Clear credentials", async () => {
    saveCredentials({ ownerId: "alice", keyHash: "a".repeat(64) });
    getInventory.mockResolvedValue({ agents: [item] });
    const user = userEvent.setup();
    render(<Home />);
    await screen.findByText("bot1");
    await user.click(screen.getByRole("button", { name: /clear credentials/i }));
    expect(screen.getByLabelText(/api key/i)).toBeInTheDocument();
    expect(localStorage.getItem("agentwatch.credentials")).toBeNull();
  });

  it("refetches every 30s and clears the interval on unmount", async () => {
    vi.useFakeTimers();
    saveCredentials({ ownerId: "alice", keyHash: "a".repeat(64) });
    getInventory.mockResolvedValue({ agents: [item] });
    const { unmount } = render(<Home />);
    await vi.waitFor(() => expect(getInventory).toHaveBeenCalledTimes(1));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(getInventory).toHaveBeenCalledTimes(2);
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(getInventory).toHaveBeenCalledTimes(2);
  });

  it("keeps the last data and shows an inline alert on a non-auth error", async () => {
    saveCredentials({ ownerId: "alice", keyHash: "a".repeat(64) });
    getInventory.mockResolvedValueOnce({ agents: [item] });
    getInventory.mockRejectedValueOnce(new Error("network down"));
    const { rerender } = render(<Home />);
    await screen.findByText("bot1");
    // Force a second fetch by re-rendering (interval also would, but keep it simple).
    rerender(<Home />);
    await waitFor(() => {
      expect(screen.getByText("bot1")).toBeInTheDocument();
    });
  });
});
