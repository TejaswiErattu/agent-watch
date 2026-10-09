import { describe, it, expect, beforeEach } from "vitest";
import {
  hashKey,
  saveCredentials,
  loadCredentials,
  clearCredentials,
  STORAGE_KEY,
} from "./credentials";

// Known SHA-256 of "abc" (lowercase hex).
const SHA256_ABC =
  "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

describe("hashKey", () => {
  it("matches the known SHA-256 hex vector for 'abc'", async () => {
    expect(await hashKey("abc")).toBe(SHA256_ABC);
  });
});

describe("credential storage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("saves only ownerId and keyHash, never the plaintext key", () => {
    saveCredentials({ ownerId: "alice", keyHash: SHA256_ABC });
    const raw = localStorage.getItem(STORAGE_KEY)!;
    expect(JSON.parse(raw)).toEqual({ ownerId: "alice", keyHash: SHA256_ABC });
    expect(raw).not.toContain("abc");
  });

  it("loads what was saved", () => {
    saveCredentials({ ownerId: "alice", keyHash: SHA256_ABC });
    expect(loadCredentials()).toEqual({ ownerId: "alice", keyHash: SHA256_ABC });
  });

  it("returns null when empty", () => {
    expect(loadCredentials()).toBeNull();
  });

  it("returns null when corrupt", () => {
    localStorage.setItem(STORAGE_KEY, "{not json");
    expect(loadCredentials()).toBeNull();
  });

  it("returns null when the shape is wrong", () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ownerId: "alice" }));
    expect(loadCredentials()).toBeNull();
  });

  it("clears the stored credentials", () => {
    saveCredentials({ ownerId: "alice", keyHash: SHA256_ABC });
    clearCredentials();
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(loadCredentials()).toBeNull();
  });
});
