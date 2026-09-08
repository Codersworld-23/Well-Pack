"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api, type Report, fmtDate } from "@/lib/api";
import { EmptyState, Section } from "@/components/ui";

const STATUSES = ["open", "under_review", "action_taken", "dismissed"] as const;

const STATUS_TONE: Record<string, string> = {
  open: "chip-warn",
  under_review: "chip-neutral",
  action_taken: "chip-pass",
  dismissed: "chip-neutral",
};

const PRIORITY_TONE: Record<string, string> = {
  high: "chip-fail",
  medium: "chip-warn",
  low: "chip-neutral",
};

export default function ReportsQueuePage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    api
      .listReports(filter ? { status: filter } : {})
      .then(setReports)
      .catch(() => setReports([]))
      .finally(() => setLoading(false));
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  async function setStatus(id: string, status: string) {
    await api.updateReport(id, { status });
    load();
  }

  return (
    <Section
      title={`Violation reports (${reports.length})`}
      description="Crowdsourced alerts, triaged by the evidence attached to them."
      action={
        <div className="flex flex-wrap gap-1">
          {["", ...STATUSES].map((status) => (
            <button
              key={status || "all"}
              onClick={() => setFilter(status)}
              className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition-colors ${
                filter === status
                  ? "bg-[var(--brand)] text-[var(--brand-fg)]"
                  : "text-[var(--muted)] hover:bg-[var(--surface-2)]"
              }`}
            >
              {status ? status.replace("_", " ") : "All"}
            </button>
          ))}
        </div>
      }
    >
      {loading ? (
        <p className="pulsing px-5 py-8 text-sm text-[var(--muted)]">Loading…</p>
      ) : reports.length === 0 ? (
        <EmptyState
          title="No reports in this queue"
          hint="Citizen reports filed from the scan result land here."
        />
      ) : (
        <ul className="divide-y">
          {reports.map((report) => (
            <li key={report.id} className="px-5 py-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`chip ${PRIORITY_TONE[report.priority]}`}>
                  {report.priority} priority
                </span>
                <span className={`chip ${STATUS_TONE[report.status]}`}>
                  {report.status.replace("_", " ")}
                </span>
                <span className="chip chip-neutral">{report.category}</span>
                <span className="ml-auto text-xs tabular-nums text-[var(--muted)]">
                  {fmtDate(report.created_at)}
                </span>
              </div>

              <p className="mt-2 text-sm font-semibold">
                {report.product_name ?? "Unnamed product"}
              </p>
              <p className="mt-1 text-[13px] leading-relaxed text-[var(--muted)]">
                {report.description}
              </p>

              <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-[var(--muted)]">
                {report.retailer && <span>Retailer: {report.retailer}</span>}
                {report.location && <span>Location: {report.location}</span>}
                {report.reporter_name && <span>Reported by: {report.reporter_name}</span>}
                {report.reporter_contact && <span>Contact: {report.reporter_contact}</span>}
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                {report.scan_id && (
                  <Link
                    href={`/scan/${report.scan_id}`}
                    className="btn btn-ghost !px-2.5 !py-1 !text-xs"
                  >
                    View scan evidence
                  </Link>
                )}
                {STATUSES.filter((status) => status !== report.status).map((status) => (
                  <button
                    key={status}
                    className="btn btn-ghost !px-2.5 !py-1 !text-xs"
                    onClick={() => setStatus(report.id, status)}
                  >
                    Mark {status.replace("_", " ")}
                  </button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
