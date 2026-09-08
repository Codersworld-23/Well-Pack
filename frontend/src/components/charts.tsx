"use client";

import { useState } from "react";

/** Vertical bars for a single magnitude series over time.
 *  One series, one hue - identity is carried by the axis, not by colour. */
export function TimeBars({
  data,
  height = 150,
}: {
  data: { date: string; scans: number; compliant: number; non_compliant: number }[];
  height?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...data.map((d) => d.scans));
  const barGap = 2;
  const width = 100;
  const slot = width / Math.max(data.length, 1);

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="w-full"
        style={{ height }}
        role="img"
        aria-label="Daily scan volume"
      >
        {[0.25, 0.5, 0.75, 1].map((tick) => (
          <line
            key={tick}
            x1={0}
            x2={width}
            y1={height - tick * height * 0.92}
            y2={height - tick * height * 0.92}
            stroke="var(--chart-grid)"
            strokeWidth={0.5}
          />
        ))}

        {data.map((point, index) => {
          const barHeight = (point.scans / max) * height * 0.92;
          const w = Math.max(slot - barGap, 0.6);
          return (
            <rect
              key={point.date}
              x={index * slot + barGap / 2}
              y={height - barHeight}
              width={w}
              height={Math.max(barHeight, point.scans > 0 ? 1.5 : 0)}
              rx={Math.min(1.2, w / 2)}
              fill="var(--chart-1)"
              opacity={hover === null || hover === index ? 1 : 0.42}
              onMouseEnter={() => setHover(index)}
              onMouseLeave={() => setHover(null)}
            />
          );
        })}
      </svg>

      <div className="mt-1.5 flex justify-between text-[10px] text-[var(--chart-ink)]">
        <span>{data[0]?.date.slice(5)}</span>
        <span>{data.at(-1)?.date.slice(5)}</span>
      </div>

      {hover !== null && data[hover] && (
        <div className="pointer-events-none absolute left-1/2 top-0 -translate-x-1/2 rounded-lg border bg-[var(--surface)] px-3 py-2 text-xs shadow-lg">
          <p className="font-semibold">{data[hover].date}</p>
          <p className="text-[var(--muted)]">
            {data[hover].scans} scan(s) · {data[hover].compliant} compliant ·{" "}
            {data[hover].non_compliant} non-compliant
          </p>
        </div>
      )}
    </div>
  );
}

/** Horizontal bars for ranked magnitude, with the value direct-labelled. */
export function RankedBars({
  data,
}: {
  data: { label: string; sublabel?: string; value: number }[];
}) {
  const max = Math.max(1, ...data.map((d) => d.value));

  return (
    <ul className="space-y-3">
      {data.map((item) => (
        <li key={item.label + item.sublabel}>
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="truncate font-medium">{item.label}</span>
            <span className="shrink-0 font-semibold tabular-nums">{item.value}</span>
          </div>
          <div className="mt-1 flex items-center gap-2">
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--surface-2)]">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${(item.value / max) * 100}%`,
                  background: "var(--chart-1)",
                }}
              />
            </div>
            {item.sublabel && (
              <span className="shrink-0 font-mono text-[10px] text-[var(--chart-ink)]">
                {item.sublabel}
              </span>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Composition bar for the verdict split.
 *  Status colours are used here, but every segment is direct-labelled and
 *  separated by a surface gap, so the reading never depends on hue alone. */
export function CompositionBar({
  segments,
}: {
  segments: { label: string; value: number; tone: "pass" | "warn" | "fail" | "review" }[];
}) {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0);

  return (
    <div>
      <div className="flex h-3 gap-[2px] overflow-hidden rounded-full bg-[var(--surface-2)]">
        {total > 0 &&
          segments
            .filter((segment) => segment.value > 0)
            .map((segment) => (
              <div
                key={segment.label}
                title={`${segment.label}: ${segment.value}`}
                style={{
                  width: `${(segment.value / total) * 100}%`,
                  background: `var(--${segment.tone})`,
                }}
              />
            ))}
      </div>

      <ul className="mt-3 grid gap-1.5 sm:grid-cols-2">
        {segments.map((segment) => (
          <li key={segment.label} className="flex items-center gap-2 text-xs">
            <span
              aria-hidden
              className="h-2.5 w-2.5 shrink-0 rounded-sm"
              style={{ background: `var(--${segment.tone})` }}
            />
            <span className="text-[var(--muted)]">{segment.label}</span>
            <span className="ml-auto font-semibold tabular-nums">{segment.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
