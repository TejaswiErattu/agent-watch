// Mirrors the backend response contracts (backend/src/agentwatch_api/service.py).

export type EventType = "llm_call" | "tool_call" | "blocked";

export interface InventoryItem {
  agentId: string;
  ownerId: string;
  model: string | null;
  firstSeen: string | null;
  lastSeen: string | null;
  totalSpendUsd: number;
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
  meta: Record<string, unknown> | null;
}

export interface TimelineResponse {
  events: TimelineItem[];
  nextCursor: string | null;
}

export interface GuardrailConfig {
  dailySpendCapUsd: number | null;
  blockedPaths: string[];
}

export interface ModelPrice {
  inputPerMtok: number;
  outputPerMtok: number;
}

export interface PricingTable {
  models: Record<string, ModelPrice>;
}

export interface ConfigResponse {
  guardrails: GuardrailConfig;
  pricing?: PricingTable;
}
