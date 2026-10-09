import { describe, it, expect } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";

// Amplify monorepo spec lives at the repo root, not inside dashboard/.
const amplifyPath = resolve(__dirname, "..", "..", "amplify.yml");

describe("amplify build config", () => {
  it("exists at the repo root", () => {
    expect(existsSync(amplifyPath)).toBe(true);
  });

  it("is a monorepo spec rooted at dashboard that builds the static export", () => {
    const yml = readFileSync(amplifyPath, "utf-8");
    expect(yml).toMatch(/^applications:/m);
    expect(yml).toMatch(/appRoot:\s*dashboard\b/);
    expect(yml).toMatch(/baseDirectory:\s*out\b/);
    expect(yml).toContain("npm ci");
    expect(yml).toContain("npm run build");
  });
});
