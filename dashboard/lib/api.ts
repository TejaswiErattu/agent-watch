// Typed API client. Every request carries the owner/key-hash credential
// headers the backend expects. Auth failures surface as AuthError so the UI
// can prompt for credentials; other failures surface the server message.

import type { Credentials } from "./credentials";
import type {
  ConfigResponse,
  GuardrailConfig,
  InventoryResponse,
  TimelineResponse,
} from "./types";

export class AuthError extends Error {
  constructor(message = "Credentials not accepted") {
    super(message);
    this.name = "AuthError";
  }
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function baseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? "";
}

export async function apiFetch<T>(
  path: string,
  creds: Credentials,
  init: RequestInit = {}
): Promise<T> {
  const headers: Record<string, string> = {
    "content-type": "application/json",
    "x-agentwatch-owner": creds.ownerId,
    "x-agentwatch-key-hash": creds.keyHash,
    ...((init.headers as Record<string, string>) ?? {}),
  };
  const res = await fetch(`${baseUrl()}${path}`, { ...init, headers });
  if (res.status === 401 || res.status === 403) {
    throw new AuthError();
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const message =
      (body && typeof body.error === "string" && body.error) ||
      `request failed (${res.status})`;
    throw new ApiError(message, res.status);
  }
  return body as T;
}

export function getInventory(creds: Credentials): Promise<InventoryResponse> {
  return apiFetch<InventoryResponse>("/agents", creds);
}

export interface TimelineQuery {
  order?: "asc" | "desc";
  type?: "llm_call" | "tool_call" | "blocked";
  cursor?: string;
  limit?: number;
}

export function getTimeline(
  creds: Credentials,
  agentId: string,
  query: TimelineQuery = {}
): Promise<TimelineResponse> {
  const params = new URLSearchParams();
  if (query.order) params.set("order", query.order);
  if (query.type) params.set("type", query.type);
  if (query.cursor) params.set("cursor", query.cursor);
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  const qs = params.toString();
  const path = `/agents/${encodeURIComponent(agentId)}/events${qs ? `?${qs}` : ""}`;
  return apiFetch<TimelineResponse>(path, creds);
}

export function getConfig(
  creds: Credentials,
  agentId: string
): Promise<ConfigResponse> {
  return apiFetch<ConfigResponse>(
    `/agents/${encodeURIComponent(agentId)}/config`,
    creds
  );
}

export function putConfig(
  creds: Credentials,
  agentId: string,
  config: GuardrailConfig
): Promise<ConfigResponse> {
  return apiFetch<ConfigResponse>(
    `/agents/${encodeURIComponent(agentId)}/config`,
    creds,
    { method: "PUT", body: JSON.stringify(config) }
  );
}
