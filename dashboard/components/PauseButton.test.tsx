import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { StatusResponse } from "@/lib/types";

const putStatus = vi.fn();
vi.mock("@/lib/api", () => ({
  putStatus: (...args: unknown[]) => putStatus(...args),
}));

import { PauseButton } from "./PauseButton";

const creds = { ownerId: "alice", keyHash: "a".repeat(64) };
const active: StatusResponse = { agentId: "bot1", paused: false, pausedAt: null };
const paused: StatusResponse = {
  agentId: "bot1",
  paused: true,
  pausedAt: "2026-10-14T12:00:00.000Z",
};

beforeEach(() => {
  putStatus.mockReset();
});

describe("PauseButton", () => {
  it("shows 'Pause agent' when the agent is active", () => {
    render(<PauseButton creds={creds} agentId="bot1" status={active} />);
    expect(screen.getByRole("button", { name: "Pause agent" })).toBeInTheDocument();
  });

  it("needs a confirm click before pausing, then shows 'Resume agent'", async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn();
    putStatus.mockResolvedValue(paused);
    render(<PauseButton creds={creds} agentId="bot1" status={active} onChanged={onChanged} />);

    await user.click(screen.getByRole("button", { name: "Pause agent" }));
    expect(putStatus).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Confirm pause" }));

    expect(putStatus).toHaveBeenCalledWith(creds, "bot1", true);
    expect(await screen.findByRole("button", { name: "Resume agent" })).toBeInTheDocument();
    expect(onChanged).toHaveBeenCalledWith(paused);
  });

  it("cancel backs out of the confirm step without a request", async () => {
    const user = userEvent.setup();
    render(<PauseButton creds={creds} agentId="bot1" status={active} />);
    await user.click(screen.getByRole("button", { name: "Pause agent" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Pause agent" })).toBeInTheDocument();
    expect(putStatus).not.toHaveBeenCalled();
  });

  it("resumes with a single click", async () => {
    const user = userEvent.setup();
    putStatus.mockResolvedValue(active);
    render(<PauseButton creds={creds} agentId="bot1" status={paused} />);
    await user.click(screen.getByRole("button", { name: "Resume agent" }));
    expect(putStatus).toHaveBeenCalledWith(creds, "bot1", false);
    expect(await screen.findByRole("button", { name: "Pause agent" })).toBeInTheDocument();
  });

  it("a failing PUT shows the error and keeps the old label", async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn();
    putStatus.mockRejectedValue(new Error("network down"));
    render(<PauseButton creds={creds} agentId="bot1" status={active} onChanged={onChanged} />);
    await user.click(screen.getByRole("button", { name: "Pause agent" }));
    await user.click(screen.getByRole("button", { name: "Confirm pause" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("network down");
    expect(screen.getByRole("button", { name: "Pause agent" })).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
  });
});
