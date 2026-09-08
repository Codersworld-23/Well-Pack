"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, type ScanResult } from "@/lib/api";
import { VerdictBadge } from "@/components/ui";

const CATEGORIES = [
  ["labelling", "Missing or incorrect declaration"],
  ["mrp", "MRP overcharging or altered price"],
  ["quantity", "Short weight / short measure"],
  ["legibility", "Declaration too small or illegible"],
  ["other", "Other"],
];

function ReportForm() {
  const params = useSearchParams();
  const scanId = params.get("scan");

  const [scan, setScan] = useState<ScanResult | null>(null);
  const [form, setForm] = useState({
    product_name: "",
    reporter_name: "",
    reporter_contact: "",
    retailer: "",
    location: "",
    category: "labelling",
    description: "",
  });
  const [state, setState] = useState<
    { kind: "idle" } | { kind: "saving" } | { kind: "sent"; id: string } | { kind: "error"; message: string }
  >({ kind: "idle" });

  useEffect(() => {
    if (!scanId) return;
    api
      .getScan(scanId)
      .then((result) => {
        setScan(result);
        setForm((prev) => ({
          ...prev,
          product_name: result.product_name ?? "",
          description: result.violations.length
            ? `Scan evidence: ${result.violations
                .map((v) => `Rule ${v.rule_number} — ${v.message}`)
                .join(" ")}`
            : prev.description,
        }));
      })
      .catch(() => setScan(null));
  }, [scanId]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setState({ kind: "saving" });
    try {
      const report = await api.createReport({ ...form, scan_id: scanId ?? undefined });
      setState({ kind: "sent", id: report.id });
    } catch (error) {
      setState({
        kind: "error",
        message: error instanceof Error ? error.message : "Could not file the report",
      });
    }
  }

  if (state.kind === "sent") {
    return (
      <div className="card mx-auto max-w-xl p-8 text-center">
        <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-[var(--pass-bg)] text-xl tone-pass">
          ✓
        </div>
        <h1 className="mt-4 text-xl font-bold">Report filed</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Reference <span className="font-mono">{state.id}</span>. It is now in the Legal
          Metrology inspection queue{scanId && ", with your scan attached as evidence"}.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <Link href="/scan" className="btn btn-primary">
            Scan another product
          </Link>
          <Link href="/admin/reports" className="btn btn-ghost">
            View the queue
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-xl">
      <h1 className="text-2xl font-bold tracking-tight">Report a non-compliant product</h1>
      <p className="mt-1.5 text-sm text-[var(--muted)]">
        Reports reach Legal Metrology officers directly. Attaching a scan raises the
        priority automatically when critical contraventions were found.
      </p>

      {scan && (
        <div className="card mt-5 flex items-center gap-3 p-4">
          <VerdictBadge verdict={scan.verdict} />
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">
              {scan.product_name ?? "Unidentified product"}
            </p>
            <p className="text-xs text-[var(--muted)]">
              Scan {scan.id} attached · {scan.violations.length} violation(s)
            </p>
          </div>
        </div>
      )}

      <form onSubmit={submit} className="card mt-5 space-y-4 p-5">
        <Field label="Product name">
          <input
            className="input"
            required
            value={form.product_name}
            onChange={(e) => setForm({ ...form, product_name: e.target.value })}
          />
        </Field>

        <Field label="What is wrong?">
          <select
            className="input"
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
          >
            {CATEGORIES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Details">
          <textarea
            className="input min-h-28"
            required
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Describe what you observed on the package."
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Retailer / seller">
            <input
              className="input"
              value={form.retailer}
              onChange={(e) => setForm({ ...form, retailer: e.target.value })}
            />
          </Field>
          <Field label="Location">
            <input
              className="input"
              placeholder="City, State"
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
            />
          </Field>
          <Field label="Your name">
            <input
              className="input"
              value={form.reporter_name}
              onChange={(e) => setForm({ ...form, reporter_name: e.target.value })}
            />
          </Field>
          <Field label="Contact (phone or e-mail)">
            <input
              className="input"
              value={form.reporter_contact}
              onChange={(e) => setForm({ ...form, reporter_contact: e.target.value })}
            />
          </Field>
        </div>

        {state.kind === "error" && (
          <p className="rounded-lg bg-[var(--fail-bg)] px-3 py-2 text-sm tone-fail">
            {state.message}
          </p>
        )}

        <button
          className="btn btn-primary w-full"
          type="submit"
          disabled={state.kind === "saving"}
        >
          {state.kind === "saving" ? "Filing…" : "File report"}
        </button>
      </form>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <span className="label">{label}</span>
      {children}
    </div>
  );
}

export default function ReportPage() {
  return (
    <Suspense fallback={<p className="text-sm text-[var(--muted)]">Loading…</p>}>
      <ReportForm />
    </Suspense>
  );
}
