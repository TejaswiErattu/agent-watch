import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";

const amplifyPath = resolve(__dirname, "..", "amplify.yml");

describe("amplify build config", () => {
  it("exists", () => {
    expect(existsSync(amplifyPath)).toBe(true);
  });

  it("publishes the static export from out/ and runs ci + build", () => {
    const yml = readFileSync(amplifyPath, "utf-8");
    expect(yml).toMatch(/baseDirectory:\s*out\b/);
    expect(yml).toContain("npm ci");
    expect(yml).toContain("npm run build");
  });
});
