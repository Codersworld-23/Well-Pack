"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type Analytics, type ScanSummary, type SystemStatus, fmtDate } from "@/lib/api";
import { EmptyState, Section, Stat, VerdictBadge } from "@/components/ui";
import { CompositionBar, RankedBars, TimeBars } from "@/components/charts";

export default function AdminDashboard() {
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [recent, setRecent] = useState<ScanSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.analytics(30), api.systemStatus(), api.listScans({ limit: 6 })])
      .then(([a, s, r]) => {
        setAnalytics(a);
        setSystem(s);
        setRecent(r);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, []);

  if (error) {
    return (
      <div className="card p-6">
        <p className="text-sm font-bold tone-fail">Cannot reach the API</p>
        <p className="mt-1 text-sm text-[var(--muted)]">{error}</p>
      </div>
    );
  }

  if (!analytics || !system) {
    return <p className="pulsing text-sm text-[var(--muted)]">Loading dashboard…</p>;
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Scans (30 days)"
          value={analytics.total_scans}
          hint={`${analytics.avg_latency_ms} ms average`}
        />
        <Stat
          label="Compliance rate"
          value={`${analytics.compliance_rate}%`}
          tone={analytics.compliance_rate >= 70 ? "pass" : "fail"}
          hint={`${analytics.compliant} of ${analytics.total_scans} passed`}
        />
        <Stat
          label="Open reports"
          value={analytics.open_reports}
          tone={analytics.open_reports > 0 ? "warn" : undefined}
          hint={`${analytics.total_reports} filed in total`}
        />
        <Stat
          label="Cache hit rate"
          value={`${analytics.cache_hit_rate}%`}
          hint={`${system.semantic_cache.entries} products remembered`}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Section
          title="Daily scan volume"
          description="Last 30 days. Hover a bar for the compliance split."
        >
          <div className="px-5 py-5">
            <TimeBars data={analytics.scans_by_day} />
          </div>
        </Section>

        <Section title="Verdict split" description="Across the same period.">
          <div className="px-5 py-5">
            <CompositionBar
              segments={[
                { label: "Compliant", value: analytics.compliant, tone: "pass" },
                {
                  label: "Minor defects",
                  value:
                    analytics.verdict_split.find((v) => v.verdict === "partial")?.count ?? 0,
                  tone: "warn",
                },
                { label: "Non-compliant", value: analytics.non_compliant, tone: "fail" },
                {
                  label: "Needs review",
                  value:
                    analytics.verdict_split.find((v) => v.verdict === "needs_review")
                      ?.count ?? 0,
                  tone: "review",
                },
              ]}
            />
          </div>
        </Section>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section
          title="Most contravened clauses"
          description="What field inspection should target first."
        >
          <div className="px-5 py-5">
            {analytics.top_violations.length === 0 ? (
              <p className="text-sm text-[var(--muted)]">No violations recorded yet.</p>
            ) : (
              <RankedBars
                data={analytics.top_violations.map((v) => ({
                  label: v.title,
                  sublabel: `Rule ${v.rule_number}`,
                  value: v.count,
                }))}
              />
            )}
          </div>
        </Section>

        <Section
          title="System status"
          description="Live state of the RAG corpus, cache and inference tier."
        >
          <dl className="divide-y text-sm">
            <Row
              label="Vector store"
              value={`${system.vector_store.clauses_indexed} clauses · v${system.vector_store.corpus_version}`}
              hint={`${system.vector_store.backend}, ${system.vector_store.embedding_dim}-dim`}
            />
            <Row
              label="Semantic cache"
              value={`${system.semantic_cache.entries} entries · ${system.semantic_cache.hits} hits`}
              hint={`${system.semantic_cache.backend}, threshold ${system.semantic_cache.threshold}`}
            />
            <Row label="OCR engine" value={system.ocr_engine} />
            <Row
              label="Verification"
              value={system.llm.mode}
              hint={
                system.llm.configured
                  ? `${system.llm.model} narrates; the rule engine decides`
                  : `Set ANTHROPIC_API_KEY to enable ${system.llm.model} narration`
              }
            />
            <Row label="Database" value={system.database} />
          </dl>
        </Section>
      </div>

      <Section
        title="Recent scans"
        action={
          <Link href="/admin/scans" className="btn btn-ghost">
            View all
          </Link>
        }
      >
        {recent.length === 0 ? (
          <EmptyState
            title="No scans yet"
            hint="Scan a label to populate the inspection log."
          />
        ) : (
          <ul className="divide-y">
            {recent.map((scan) => (
              <li key={scan.id}>
                <Link
                  href={`/scan/${scan.id}`}
                  className="flex items-center gap-4 px-5 py-3 transition-colors hover:bg-[var(--surface-2)]"
                >
                  <VerdictBadge verdict={scan.verdict} size="sm" />
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">
                    {scan.product_name ?? "Unidentified product"}
                  </span>
                  <span className="hidden text-xs text-[var(--muted)] sm:block">
                    {scan.violation_count} violation(s)
                  </span>
                  <span className="text-xs tabular-nums text-[var(--muted)]">
                    {fmtDate(scan.created_at)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}

function Row({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex items-start justify-between gap-4 px-5 py-3">
      <dt className="text-[var(--muted)]">{label}</dt>
      <dd className="text-right">
        <span className="font-semibold">{value}</span>
        {hint && <p className="text-[11px] text-[var(--muted)]">{hint}</p>}
      </dd>
    </div>
  );
}
