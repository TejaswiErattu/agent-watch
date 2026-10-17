import { describe, it, expect } from "vitest";
import { COMMAND_PRESETS } from "./commandPresets";

// Req 28.13: the same presets must work in JavaScript RegExp (here) and Python re
// (backend/tests/test_command_presets.py), since the dashboard edits what the SDK matches.
describe("commandPresets", () => {
  it("has nine or more presets with unique ids, including env_file", () => {
    const ids = COMMAND_PRESETS.map((p) => p.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids.length).toBeGreaterThanOrEqual(9);
    expect(ids).toContain("env_file");
    expect(ids).toContain("pipe_to_shell");
  });

  for (const p of COMMAND_PRESETS) {
    it(`${p.id}: has the five fields, compiles, matches example, misses safeExample`, () => {
      expect(Object.keys(p).sort()).toEqual(
        ["example", "id", "label", "pattern", "safeExample"]
      );
      const rx = new RegExp(p.pattern, "i");
      expect(rx.test(p.example)).toBe(true);
      expect(rx.test(p.safeExample)).toBe(false);
    });
  }

  it("env_file blocks cat .env", () => {
    const env = COMMAND_PRESETS.find((p) => p.id === "env_file")!;
    expect(new RegExp(env.pattern, "i").test("cat .env")).toBe(true);
  });
});
