import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

import { AddAgentForm } from "./AddAgentForm";

beforeEach(() => {
  push.mockClear();
});

describe("AddAgentForm", () => {
  it("shows an error for an invalid agentId and does not navigate", async () => {
    const user = userEvent.setup();
    render(<AddAgentForm />);
    await user.type(screen.getByLabelText(/agent id/i), "bad id!");
    await user.click(screen.getByRole("button", { name: /open/i }));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("navigates to the agent page for a valid agentId", async () => {
    const user = userEvent.setup();
    render(<AddAgentForm />);
    await user.type(screen.getByLabelText(/agent id/i), "bot1");
    await user.click(screen.getByRole("button", { name: /open/i }));
    expect(push).toHaveBeenCalledWith("/agent?id=bot1");
  });
});
