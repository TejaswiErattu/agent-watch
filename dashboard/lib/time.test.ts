import { describe, it, expect } from "vitest";
import { relativeTime } from "./time";

const NOW = Date.parse("2026-10-12T12:00:00.000Z");
const ago = (ms: number) => new Date(NOW - ms).toISOString();

describe("relativeTime", () => {
  it.each([
    [10_000, "just now"],
    [3 * 60_000, "3 min ago"],
    [59 * 60_000, "59 min ago"],
    [2 * 3_600_000, "2 h ago"],
    [3 * 86_400_000, "3 d ago"],
    [-60_000, "just now"], // small clock skew into the future
  ])("formats %s ms ago as %s", (ms, expected) => {
    expect(relativeTime(ago(ms), NOW)).toBe(expected);
  });

  it("returns the input unchanged when it is not a date", () => {
    expect(relativeTime("garbage", NOW)).toBe("garbage");
  });
});
