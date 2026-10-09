// Browser-side credential handling. The plaintext API key never leaves this
// module: it is hashed with SHA-256 and only {ownerId, keyHash} is stored.

export const STORAGE_KEY = "agentwatch.credentials";

export interface Credentials {
  ownerId: string;
  keyHash: string;
}

/** Lowercase hex SHA-256 of the API key, matching the backend's key hashing. */
export async function hashKey(apiKey: string): Promise<string> {
  const bytes = new TextEncoder().encode(apiKey);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function saveCredentials(creds: Credentials): void {
  const safe = { ownerId: creds.ownerId, keyHash: creds.keyHash };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(safe));
}

export function loadCredentials(): Credentials | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw === null) return null;
  try {
    const parsed = JSON.parse(raw);
    if (
      parsed &&
      typeof parsed.ownerId === "string" &&
      typeof parsed.keyHash === "string"
    ) {
      return { ownerId: parsed.ownerId, keyHash: parsed.keyHash };
    }
    return null;
  } catch {
    return null;
  }
}

export function clearCredentials(): void {
  localStorage.removeItem(STORAGE_KEY);
}
