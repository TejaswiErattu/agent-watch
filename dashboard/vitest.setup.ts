import "@testing-library/jest-dom/vitest";

// jsdom in this setup does not always expose a Storage implementation.
// Provide a minimal in-memory localStorage so credential tests can run.
if (typeof globalThis.localStorage === "undefined") {
  class MemoryStorage {
    private store = new Map<string, string>();
    get length() {
      return this.store.size;
    }
    clear() {
      this.store.clear();
    }
    getItem(key: string) {
      return this.store.has(key) ? this.store.get(key)! : null;
    }
    key(index: number) {
      return Array.from(this.store.keys())[index] ?? null;
    }
    removeItem(key: string) {
      this.store.delete(key);
    }
    setItem(key: string, value: string) {
      this.store.set(key, String(value));
    }
  }
  Object.defineProperty(globalThis, "localStorage", {
    value: new MemoryStorage(),
    writable: false,
    configurable: true,
  });
}
