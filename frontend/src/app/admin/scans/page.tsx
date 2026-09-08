"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, type ScanSummary, type Verdict, fmtDate } from "@/lib/api";
import { EmptyState, Section, VerdictBadge } from "@/components/ui";

const FILTERS: { value: string; label: string }[] = [
  { value: "", label: "All" },
  { value: "compliant", label: "Compliant" },
  { value: "partial", label: "Minor defects" },
  { value: "non_compliant", label: "Non-compliant" },
  { value: "needs_review", label: "Needs review" },
];

export default function ScanLogPage() {
  const [scans, setScans] = useState<ScanSummary[]>([]);
  const [verdict, setVerdict] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    api
      .listScans(verdict ? { limit: 200, verdict } : { limit: 200 })
      .then(setScans)
      .catch(() => setScans([]))
      .finally(() => setLoading(false));
  }, [verdict]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <Section
      title="Inspection log"
      description="Every scan, with its verdict and evidence."
      action={
        <div className="flex flex-wrap gap-1">
          {FILTERS.map((filter) => (
            <button
              key={filter.value}
              onClick={() => setVerdict(filter.value)}
              className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition-colors ${
                verdict === filter.value
                  ? "bg-[var(--brand)] text-[var(--brand-fg)]"
                  : "text-[var(--muted)] hover:bg-[var(--surface-2)]"
              }`}
            >
              {filter.label}
            </button>
          ))}
        </div>
      }
    >
      {loading ? (
        <p className="pulsing px-5 py-8 text-sm text-[var(--muted)]">Loading…</p>
      ) : scans.length === 0 ? (
        <EmptyState title="No scans match this filter" />
      ) : (
        <div className="scroll-x">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="border-b text-left text-xs uppercase tracking-wider text-[var(--muted)]">
                <th className="px-5 py-2.5 font-semibold">Product</th>
                <th className="px-3 py-2.5 font-semibold">Verdict</th>
                <th className="px-3 py-2.5 text-right font-semibold">Score</th>
                <th className="px-3 py-2.5 text-right font-semibold">Violations</th>
                <th className="px-3 py-2.5 font-semibold">Source</th>
                <th className="px-3 py-2.5 text-right font-semibold">Latency</th>
                <th className="px-5 py-2.5 text-right font-semibold">Scanned</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {scans.map((scan) => (
                <tr key={scan.id} className="transition-colors hover:bg-[var(--surface-2)]">
                  <td className="px-5 py-2.5">
                    <Link href={`/scan/${scan.id}`} className="font-medium hover:underline">
                      {scan.product_name ?? "Unidentified product"}
                    </Link>
                    <span className="ml-2 font-mono text-[10px] text-[var(--muted)]">
                      {scan.id}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    <VerdictBadge verdict={scan.verdict as Verdict} size="sm" />
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {scan.compliance_score}
                  </td>
                  <td className="px-3 py-2.5 text-right tabular-nums">
                    {scan.violation_count}
                  </td>
                  <td className="px-3 py-2.5 text-[var(--muted)]">{scan.source}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-[var(--muted)]">
                    {scan.latency_ms} ms{scan.cache_hit && " ·cached"}
                  </td>
                  <td className="px-5 py-2.5 text-right text-xs tabular-nums text-[var(--muted)]">
                    {fmtDate(scan.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}
