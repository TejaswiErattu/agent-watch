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

import AgentPage from "./page";
import { saveCredentials } from "@/lib/credentials";

beforeEach(() => {
  localStorage.clear();
  searchParams = new URLSearchParams();
});

describe("agent detail page", () => {
  it("renders Timeline and RulesEditor for the id", async () => {
    saveCredentials({ ownerId: "alice", keyHash: "a".repeat(64) });
    searchParams = new URLSearchParams("id=bot1");
    render(<AgentPage />);
    expect(await screen.findByTestId("timeline")).toHaveTextContent("bot1");
    expect(screen.getByTestId("rules")).toHaveTextContent("bot1");
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
