import * as React from "react";
import type { SpendBucket } from "@/lib/types";
import { formatSpend } from "@/lib/format";

export interface SpendChartProps {
  buckets: SpendBucket[];
  capUsd: number | null;
}

// Fallback scale when there's no spend and no cap, so bars have a sane height of 0.
const MIN_Y = 0.0001;

// y-axis max: the tallest bar, or cap/24 (the even hourly pace) if that's taller.
export function yMax(buckets: SpendBucket[], capUsd: number | null): number {
  const top = Math.max(0, ...buckets.map((b) => b.costUsd));
  const pace = capUsd !== null && capUsd > 0 ? capUsd / 24 : 0;
  return Math.max(top, pace, MIN_Y);
}

const W = 480;
const H = 160;
const PAD_L = 4;
const PAD_T = 18; // room for block markers above the tallest bar
const PAD_B = 18; // room for hour labels

function hourLabel(start: string): string {
  // A bucket covers (start, start + 1h]; label it by the hour it ends in, in local time.
  const end = new Date(Date.parse(start) + 3_600_000);
  return `${String(end.getHours()).padStart(2, "0")}:00`;
}

export type Anchor = "start" | "middle" | "end";

// Edge labels anchor inward so they never run past the chart's left or right edge.
export function labelAnchor(i: number, n: number): Anchor {
  if (i === 0) return "start";
  if (i === n - 1) return "end";
  return "middle";
}

export function SpendChart({ buckets, capUsd }: SpendChartProps) {
  const max = yMax(buckets, capUsd);
  const plotH = H - PAD_T - PAD_B;
  const slot = (W - PAD_L) / Math.max(1, buckets.length);
  const barW = slot * 0.7;
  const empty = buckets.every((b) => b.costUsd === 0 && b.blocked === 0);
  const baseY = PAD_T + plotH;

  return (
    <figure className="space-y-1">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="h-40 w-full"
        role="img"
        aria-label="LLM spend per hour, last 24 hours"
      >
        <line data-axis x1={PAD_L} y1={baseY} x2={W} y2={baseY} stroke="#9ca3af" strokeWidth={1} />
        {buckets.map((b, i) => {
          const h = (b.costUsd / max) * plotH;
          const x = PAD_L + i * slot + (slot - barW) / 2;
          const label = hourLabel(b.start);
          const anchor = labelAnchor(i, buckets.length);
          // Anchor point: slot's left edge, bar center, or slot's right edge.
          const labelX =
            anchor === "start" ? PAD_L + i * slot : anchor === "end" ? PAD_L + (i + 1) * slot : x + barW / 2;
          return (
            <g key={b.start}>
              <rect data-bar x={x} y={baseY - h} width={barW} height={h} fill="#2563eb">
                <title>{`${label}: ${formatSpend(b.costUsd)}, ${b.blocked} blocked`}</title>
              </rect>
              {b.blocked > 0 ? (
                <text
                  data-blocked-marker
                  x={x + barW / 2}
                  y={baseY - h - 4}
                  textAnchor="middle"
                  fontSize={10}
                  fill="#dc2626"
                  fontWeight={600}
                >
                  {b.blocked}
                </text>
              ) : null}
              {i % 6 === 5 ? (
                <text
                  data-hour-label
                  data-anchor={anchor}
                  x={labelX}
                  y={H - 4}
                  textAnchor={anchor}
                  fontSize={9}
                  fill="#6b7280"
                >
                  {label}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      {empty ? (
        <figcaption className="text-sm text-gray-500">No LLM calls in the last 24 hours</figcaption>
      ) : (
        <figcaption className="text-xs text-gray-500">
          Bars: LLM spend per hour. Red numbers: blocked actions in that hour.
        </figcaption>
      )}
    </figure>
  );
}
