import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const getConfig = vi.fn();
const putConfig = vi.fn();
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getConfig: (...args: unknown[]) => getConfig(...args),
    putConfig: (...args: unknown[]) => putConfig(...args),
  };
});

import { RulesEditor } from "./RulesEditor";
import { COMMAND_PRESETS } from "@/lib/commandPresets";
import type { Credentials } from "@/lib/credentials";

const creds: Credentials = { ownerId: "alice", keyHash: "a".repeat(64) };

beforeEach(() => {
  getConfig.mockReset();
  putConfig.mockReset();
});

describe("RulesEditor", () => {
  it("loads and shows the config", async () => {
    getConfig.mockResolvedValue({
      guardrails: { dailySpendCapUsd: 2.5, blockedPaths: [".env"] },
    });
    render(<RulesEditor creds={creds} agentId="bot1" />);
    expect(await screen.findByDisplayValue("2.5")).toBeInTheDocument();
    expect(screen.getByText(".env")).toBeInTheDocument();
  });

  it("saving a cap sends the full config", async () => {
    getConfig.mockResolvedValue({
      guardrails: { dailySpendCapUsd: null, blockedPaths: [] },
    });
    putConfig.mockResolvedValue({
      guardrails: { dailySpendCapUsd: 5, blockedPaths: [] },
    });
    const user = userEvent.setup();
    render(<RulesEditor creds={creds} agentId="bot1" />);
    await screen.findByLabelText(/daily spend cap/i);
    await user.type(screen.getByLabelText(/daily spend cap/i), "5");
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(putConfig).toHaveBeenCalledWith(creds, "bot1", {
        dailySpendCapUsd: 5,
        blockedPaths: [],
        blockedCommands: [],
      })
    );
  });

  it("adding a path sends it in the config", async () => {
    getConfig.mockResolvedValue({
      guardrails: { dailySpendCapUsd: null, blockedPaths: [] },
    });
    putConfig.mockResolvedValue({
      guardrails: { dailySpendCapUsd: null, blockedPaths: ["secrets/"] },
    });
    const user = userEvent.setup();
    render(<RulesEditor creds={creds} agentId="bot1" />);
    await screen.findByLabelText(/add path/i);
    await user.type(screen.getByLabelText(/add path/i), "secrets/");
    await user.click(screen.getByRole("button", { name: /add path/i }));
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(putConfig).toHaveBeenCalledWith(creds, "bot1", {
        dailySpendCapUsd: null,
        blockedPaths: ["secrets/"],
        blockedCommands: [],
      })
    );
  });

  it("removing a path sends the config without it", async () => {
    getConfig.mockResolvedValue({
      guardrails: { dailySpendCapUsd: null, blockedPaths: [".env", "secrets/"] },
    });
    putConfig.mockResolvedValue({
      guardrails: { dailySpendCapUsd: null, blockedPaths: ["secrets/"] },
    });
    const user = userEvent.setup();
    render(<RulesEditor creds={creds} agentId="bot1" />);
    await screen.findByText(".env");
    await user.click(screen.getByRole("button", { name: /remove \.env/i }));
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(putConfig).toHaveBeenCalledWith(creds, "bot1", {
        dailySpendCapUsd: null,
        blockedPaths: ["secrets/"],
        blockedCommands: [],
      })
    );
  });

  it("an empty cap input sends null", async () => {
    getConfig.mockResolvedValue({
      guardrails: { dailySpendCapUsd: 3, blockedPaths: [] },
    });
    putConfig.mockResolvedValue({
      guardrails: { dailySpendCapUsd: null, blockedPaths: [] },
    });
    const user = userEvent.setup();
    render(<RulesEditor creds={creds} agentId="bot1" />);
    const cap = (await screen.findByLabelText(/daily spend cap/i)) as HTMLInputElement;
    await user.clear(cap);
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(putConfig).toHaveBeenCalledWith(creds, "bot1", {
        dailySpendCapUsd: null,
        blockedPaths: [],
        blockedCommands: [],
      })
    );
  });

  it("loads and shows blockedCommands", async () => {
    getConfig.mockResolvedValue({
      guardrails: { dailySpendCapUsd: null, blockedPaths: [], blockedCommands: ["\\bsudo\\b"] },
    });
    render(<RulesEditor creds={creds} agentId="bot1" />);
    expect(await screen.findByText("\\bsudo\\b")).toBeInTheDocument();
  });

  it("a GET without blockedCommands (older backend) renders an empty list and saves []", async () => {
    getConfig.mockResolvedValue({
      guardrails: { dailySpendCapUsd: null, blockedPaths: [] },
    });
    putConfig.mockResolvedValue({
      guardrails: { dailySpendCapUsd: null, blockedPaths: [], blockedCommands: [] },
    });
    const user = userEvent.setup();
    render(<RulesEditor creds={creds} agentId="bot1" />);
    await screen.findByLabelText(/add pattern/i);
    expect(screen.queryAllByRole("button", { name: /^remove pattern/i })).toHaveLength(0);
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(putConfig).toHaveBeenCalledWith(creds, "bot1", {
        dailySpendCapUsd: null,
        blockedPaths: [],
        blockedCommands: [],
      })
    );
  });

  it("adds and removes a pattern and saves the full config", async () => {
    getConfig.mockResolvedValue({
      guardrails: { dailySpendCapUsd: null, blockedPaths: [".env"], blockedCommands: ["\\bsudo\\b"] },
    });
    putConfig.mockResolvedValue({
      guardrails: { dailySpendCapUsd: null, blockedPaths: [".env"], blockedCommands: ["\\bmkfs\\b"] },
    });
    const user = userEvent.setup();
    render(<RulesEditor creds={creds} agentId="bot1" />);
    await screen.findByText("\\bsudo\\b");
    await user.type(screen.getByLabelText(/add pattern/i), "\\bmkfs\\b");
    await user.click(screen.getByRole("button", { name: /^add pattern$/i }));
    expect(screen.getByText("\\bmkfs\\b")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove pattern \\bsudo\\b" }));
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(putConfig).toHaveBeenCalledWith(creds, "bot1", {
        dailySpendCapUsd: null,
        blockedPaths: [".env"],
        blockedCommands: ["\\bmkfs\\b"],
      })
    );
  });

  it("Add presets appends every missing preset once and never duplicates", async () => {
    const sudo = COMMAND_PRESETS.find((p) => p.id === "sudo")!.pattern;
    getConfig.mockResolvedValue({
      guardrails: { dailySpendCapUsd: null, blockedPaths: [], blockedCommands: ["custom", sudo] },
    });
    putConfig.mockResolvedValue({
      guardrails: { dailySpendCapUsd: null, blockedPaths: [], blockedCommands: [] },
    });
    const user = userEvent.setup();
    render(<RulesEditor creds={creds} agentId="bot1" />);
    await screen.findByText("custom");
    await user.click(screen.getByRole("button", { name: /add presets/i }));
    await user.click(screen.getByRole("button", { name: /add presets/i }));
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(putConfig).toHaveBeenCalled());
    const sent = putConfig.mock.calls[0][2].blockedCommands as string[];
    const expected = ["custom", sudo, ...COMMAND_PRESETS.map((p) => p.pattern).filter((p) => p !== sudo)];
    expect(sent).toEqual(expected);
    expect(new Set(sent).size).toBe(sent.length);
  });

  it("shows an error and keeps the draft on failure", async () => {
    getConfig.mockResolvedValue({
      guardrails: { dailySpendCapUsd: null, blockedPaths: [] },
    });
    putConfig.mockRejectedValue(new Error("server said no"));
    const user = userEvent.setup();
    render(<RulesEditor creds={creds} agentId="bot1" />);
    await screen.findByLabelText(/daily spend cap/i);
    await user.type(screen.getByLabelText(/daily spend cap/i), "9");
    await user.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("server said no");
    expect((screen.getByLabelText(/daily spend cap/i) as HTMLInputElement).value).toBe("9");
  });
});
