// Mirrors the backend response contracts (backend/src/agentwatch_api/service.py).

export type EventType = "llm_call" | "tool_call" | "blocked";

export interface InventoryItem {
  agentId: string;
  ownerId: string;
  model: string | null;
  firstSeen: string | null;
  lastSeen: string | null;
  totalSpendUsd: number;
  // Optional so an older backend without the field still renders ("Active").
  paused?: boolean;
}

export interface StatusResponse {
  agentId: string;
  paused: boolean;
  pausedAt: string | null;
}

export interface SpendResponse {
  agentId: string;
  rollingSpendUsd: number;
  windowStart: string;
  windowEnd: string;
}

// One hour of the 24h Spend_Series; `start` is the exclusive lower bound.
export interface SpendBucket {
  start: string;
  costUsd: number;
  llmCalls: number;
  blocked: number;
}

export interface InventoryResponse {
  agents: InventoryItem[];
}

export interface TimelineItem {
  ts: string | null;
  eventId: string | null;
  type: EventType | null;
  model: string | null;
  tool: string | null;
  target: string | null;
  inputTokens: number | null;
  outputTokens: number | null;
  costUsd: number | null;
  violationType: string | null;
  attemptedCostUsd: number | null;
  attemptedPath: string | null;
  // Optional so an older backend without the field still renders.
  attemptedCommand?: string | null;
  attemptedUrl?: string | null;
  meta: Record<string, unknown> | null;
}

export interface TimelineResponse {
  events: TimelineItem[];
  nextCursor: string | null;
}

export interface GuardrailConfig {
  dailySpendCapUsd: number | null;
  blockedPaths: string[];
  // Always sent on save; a GET from an older backend may omit it (read as []).
  blockedCommands: string[];
}

// What GET/PUT /config may return: an older backend omits blockedCommands.
export type GuardrailConfigIn = Omit<GuardrailConfig, "blockedCommands"> & {
  blockedCommands?: string[];
};

export interface ModelPrice {
  inputPerMtok: number;
  outputPerMtok: number;
}

export interface PricingTable {
  models: Record<string, ModelPrice>;
}

export interface ConfigResponse {
  guardrails: GuardrailConfigIn;
  pricing?: PricingTable;
}
