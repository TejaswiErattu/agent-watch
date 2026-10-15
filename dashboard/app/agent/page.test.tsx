import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

let searchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useSearchParams: () => searchParams,
  useRouter: () => ({ push: vi.fn() }),
}));

// Child components talk to the API; stub them to isolate the page.
vi.mock("@/components/Timeline", () => ({
  Timeline: ({ agentId }: { agentId: string }) => (
    <div data-testid="timeline">timeline {agentId}</div>
  ),
}));
vi.mock("@/components/RulesEditor", () => ({
  RulesEditor: ({ agentId }: { agentId: string }) => (
    <div data-testid="rules">rules {agentId}</div>
  ),
}));

const getStatus = vi.fn();
const putStatus = vi.fn();
vi.mock("@/lib/api", () => ({
  getStatus: (...args: unknown[]) => getStatus(...args),
  putStatus: (...args: unknown[]) => putStatus(...args),
}));

import userEvent from "@testing-library/user-event";
import AgentPage from "./page";
import { saveCredentials } from "@/lib/credentials";

beforeEach(() => {
  localStorage.clear();
  searchParams = new URLSearchParams();
  getStatus.mockReset();
  putStatus.mockReset();
  getStatus.mockResolvedValue({ agentId: "bot1", paused: false, pausedAt: null });
});

describe("agent detail page", () => {
  it("renders Timeline and RulesEditor for the id", async () => {
    saveCredentials({ ownerId: "alice", keyHash: "a".repeat(64) });
    searchParams = new URLSearchParams("id=bot1");
    render(<AgentPage />);
    expect(await screen.findByTestId("timeline")).toHaveTextContent("bot1");
    expect(screen.getByTestId("rules")).toHaveTextContent("bot1");
  });

  it("renders the pause state from getStatus", async () => {
    saveCredentials({ ownerId: "alice", keyHash: "a".repeat(64) });
    searchParams = new URLSearchParams("id=bot1");
    getStatus.mockResolvedValue({
      agentId: "bot1",
      paused: true,
      pausedAt: "2026-10-14T12:00:00.000Z",
    });
    render(<AgentPage />);
    expect(await screen.findByRole("button", { name: "Resume agent" })).toBeInTheDocument();
    expect(screen.getByTestId("pause-state")).toHaveTextContent("Paused");
    expect(getStatus).toHaveBeenCalledWith(
      { ownerId: "alice", keyHash: "a".repeat(64) },
      "bot1"
    );
  });

  it("shows Active and refetches status after a pause", async () => {
    const user = userEvent.setup();
    saveCredentials({ ownerId: "alice", keyHash: "a".repeat(64) });
    searchParams = new URLSearchParams("id=bot1");
    const pausedRes = { agentId: "bot1", paused: true, pausedAt: "2026-10-14T12:00:00.000Z" };
    putStatus.mockResolvedValue(pausedRes);
    render(<AgentPage />);
    expect(await screen.findByTestId("pause-state")).toHaveTextContent("Active");

    getStatus.mockResolvedValue(pausedRes);
    await user.click(screen.getByRole("button", { name: "Pause agent" }));
    await user.click(screen.getByRole("button", { name: "Confirm pause" }));

    expect(await screen.findByRole("button", { name: "Resume agent" })).toBeInTheDocument();
    expect(screen.getByTestId("pause-state")).toHaveTextContent("Paused");
    expect(getStatus).toHaveBeenCalledTimes(2);
  });

  it("shows a message and a link back when id is missing", async () => {
    saveCredentials({ ownerId: "alice", keyHash: "a".repeat(64) });
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
