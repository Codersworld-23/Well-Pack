import type { ReactNode } from "react";
import type { Severity, Verdict } from "@/lib/api";
import { verdictOf } from "@/lib/api";

export function VerdictBadge({
  verdict,
  size = "md",
}: {
  verdict: Verdict | null;
  size?: "sm" | "md" | "lg";
}) {
  const meta = verdictOf(verdict);
  const scale =
    size === "lg"
      ? "text-base px-4 py-1.5"
      : size === "sm"
        ? "text-[11px] px-2 py-0.5"
        : "";
  return <span className={`chip chip-${meta.tone} ${scale}`}>{meta.label}</span>;
}

const SEVERITY_TONE: Record<Severity, string> = {
  critical: "fail",
  major: "warn",
  minor: "neutral",
  info: "neutral",
};

export function SeverityChip({ severity }: { severity: Severity }) {
  return <span className={`chip chip-${SEVERITY_TONE[severity]}`}>{severity}</span>;
}

export function Stat({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "pass" | "warn" | "fail" | "review";
}) {
  return (
    <div className="card p-4">
      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">
        {label}
      </p>
      <p className={`mt-1.5 text-2xl font-bold tabular-nums ${tone ? `tone-${tone}` : ""}`}>
        {value}
      </p>
      {hint && <p className="mt-0.5 text-xs text-[var(--muted)]">{hint}</p>}
    </div>
  );
}

export function Section({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b px-5 py-4">
        <div>
          <h2 className="text-sm font-bold tracking-tight">{title}</h2>
          {description && (
            <p className="mt-0.5 text-xs text-[var(--muted)]">{description}</p>
          )}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function ScoreRing({ score }: { score: number }) {
  const tone = score >= 90 ? "pass" : score >= 60 ? "warn" : "fail";
  const circumference = 2 * Math.PI * 42;
  const offset = circumference * (1 - Math.max(0, Math.min(100, score)) / 100);

  return (
    <div className="relative h-28 w-28 shrink-0">
      <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
        <circle
          cx="50"
          cy="50"
          r="42"
          fill="none"
          strokeWidth="9"
          className="stroke-[var(--surface-2)]"
        />
        <circle
          cx="50"
          cy="50"
          r="42"
          fill="none"
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          stroke={`var(--${tone})`}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center">
        <span className={`text-2xl font-bold tabular-nums tone-${tone}`}>
          {Math.round(score)}
        </span>
        <span className="mt-7 absolute text-[10px] font-semibold uppercase tracking-wider text-[var(--muted)]">
          / 100
        </span>
      </div>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="px-5 py-12 text-center">
      <p className="text-sm font-semibold">{title}</p>
      {hint && <p className="mt-1 text-xs text-[var(--muted)]">{hint}</p>}
    </div>
  );
}
