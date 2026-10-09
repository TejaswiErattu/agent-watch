import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("dashboard scaffold", () => {
  it("configures Next.js static export", () => {
    const config = readFileSync(
      resolve(__dirname, "..", "next.config.mjs"),
      "utf-8"
    );
    expect(config).toMatch(/output:\s*["']export["']/);
  });

  it("runs vitest in a jsdom environment", () => {
    // document exists only when the jsdom environment is active.
    expect(typeof document).toBe("object");
    const el = document.createElement("div");
    el.textContent = "ok";
    expect(el.textContent).toBe("ok");
  });
});
