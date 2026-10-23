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

// break-all splits ordinary words ("demo" / "-bot"); wrapping uses overflow-wrap:anywhere instead.
describe("no break-all in dashboard source", () => {
  it("app/ and components/ never use break-all", async () => {
    const { readdirSync, statSync } = await import("node:fs");
    const walk = (dir: string): string[] =>
      readdirSync(dir).flatMap((f) => {
        const p = resolve(dir, f);
        return statSync(p).isDirectory() ? walk(p) : /\.tsx?$/.test(f) && !/\.test\./.test(f) ? [p] : [];
      });
    const root = resolve(__dirname, "..");
    const hits = [...walk(resolve(root, "app")), ...walk(resolve(root, "components"))].filter((p) =>
      readFileSync(p, "utf-8").includes("break-all")
    );
    expect(hits).toEqual([]);
  });
});
