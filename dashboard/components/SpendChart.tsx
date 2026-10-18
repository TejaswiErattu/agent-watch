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

const SHIFT: Record<Anchor, string> = {
  start: "translateX(0%)",
  middle: "translateX(-50%)",
  end: "translateX(-100%)",
};

// A viewBox coordinate as a CSS percent of the box (3 dp keeps the edges exact, e.g. "100%").
function pct(v: number, total: number): string {
  return `${Number(((v / total) * 100).toFixed(3))}%`;
}

export function SpendChart({ buckets, capUsd }: SpendChartProps) {
  const max = yMax(buckets, capUsd);
  const plotH = H - PAD_T - PAD_B;
  const slot = (W - PAD_L) / Math.max(1, buckets.length);
  const barW = slot * 0.7;
  const empty = buckets.every((b) => b.costUsd === 0 && b.blocked === 0);
  const baseY = PAD_T + plotH;

  const geom = buckets.map((b, i) => {
    const h = (b.costUsd / max) * plotH;
    const x = PAD_L + i * slot + (slot - barW) / 2;
    const anchor = labelAnchor(i, buckets.length);
    // Anchor point: slot's left edge, bar center, or slot's right edge.
    const labelX =
      anchor === "start" ? PAD_L + i * slot : anchor === "end" ? PAD_L + (i + 1) * slot : x + barW / 2;
    return { b, i, h, x, anchor, labelX, label: hourLabel(b.start) };
  });

  return (
    <figure className="space-y-1">
      <div className="relative h-40 w-full">
        {/* Bars and axis stretch to the box; no text lives here, so nothing is distorted. */}
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          className="h-full w-full"
          role="img"
          aria-label="LLM spend per hour, last 24 hours"
        >
          <line data-axis x1={PAD_L} y1={baseY} x2={W} y2={baseY} stroke="#9ca3af" strokeWidth={1} />
          {geom.map(({ b, h, x, label }) => (
            <rect key={b.start} data-bar x={x} y={baseY - h} width={barW} height={h} fill="#2563eb">
              <title>{`${label}: ${formatSpend(b.costUsd)}, ${b.blocked} blocked`}</title>
            </rect>
          ))}
        </svg>
        {/* Text is HTML positioned in percent of the same coordinate box, so it scales uniformly. */}
        <div data-chart-labels aria-hidden="true" className="pointer-events-none absolute inset-0">
          {geom.map(({ b, i, h, x, anchor, labelX, label }) => (
            <React.Fragment key={b.start}>
              {b.blocked > 0 ? (
                <span
                  data-blocked-marker
                  className="absolute text-[10px] font-semibold leading-none text-red-600"
                  style={{
                    left: pct(x + barW / 2, W),
                    top: pct(baseY - h - 2, H),
                    transform: "translateX(-50%) translateY(-100%)",
                  }}
                >
                  {b.blocked}
                </span>
              ) : null}
              {i % 6 === 5 ? (
                <span
                  data-hour-label
                  data-anchor={anchor}
                  className="absolute whitespace-nowrap text-[9px] leading-none text-gray-500"
                  style={{
                    left: pct(labelX, W),
                    top: pct(H - 2, H),
                    transform: `${SHIFT[anchor]} translateY(-100%)`,
                  }}
                >
                  {label}
                </span>
              ) : null}
            </React.Fragment>
          ))}
        </div>
      </div>
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
