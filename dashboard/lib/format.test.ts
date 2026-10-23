import { describe, it, expect } from "vitest";
import { formatSpend, relativeTime, shortModel } from "./format";
import { formatSpend as reExported } from "@/components/InventoryTable";

const NOW = Date.parse("2026-10-17T15:00:00.000Z");
const ago = (ms: number) => new Date(NOW - ms).toISOString();

describe("formatSpend", () => {
  it("is re-exported from InventoryTable", () => {
    expect(reExported).toBe(formatSpend);
  });

  it.each([
    [0.0006, "$0.0006"],
    [0.00004, "<$0.0001"],
    [0, "$0.0000"],
  ])("%s -> %s", (usd, out) => {
    expect(formatSpend(usd)).toBe(out);
  });
});

describe("relativeTime", () => {
  it.each([
    [10_000, "just now"],
    [2 * 60_000, "2 min ago"],
    [59 * 60_000, "59 min ago"],
    [3 * 3_600_000, "3 h ago"],
    [2 * 86_400_000, "2 d ago"],
  ])("%s ms ago -> %s", (ms, out) => {
    expect(relativeTime(ago(ms), NOW)).toBe(out);
  });

  it("treats a future ts as just now and an unparseable ts as empty", () => {
    expect(relativeTime(new Date(NOW + 5000).toISOString(), NOW)).toBe("just now");
    expect(relativeTime("nope", NOW)).toBe("");
  });
});

describe("shortModel", () => {
  it.each([
    ["us.anthropic.claude-haiku-4-5-20251001-v1:0", "claude-haiku-4-5"],
    ["anthropic.claude-haiku-4-5-20251001-v1:0", "claude-haiku-4-5"],
    ["eu.anthropic.claude-sonnet-4-5-20250929-v1:0", "claude-sonnet-4-5"],
    ["claude-haiku-4-5-20251001", "claude-haiku-4-5"],
    ["claude-sonnet-4-5", "claude-sonnet-4-5"],
    ["gpt-4o", "gpt-4o"],
    ["", ""],
  ])("%j -> %j", (id, short) => {
    expect(shortModel(id)).toBe(short);
  });
});
