"use client";

import Link from "next/link";
import { API_BASE, type ScanResult, verdictOf } from "@/lib/api";
import { ScoreRing, SeverityChip, Section, VerdictBadge } from "@/components/ui";

const FIELD_LABELS: Record<string, string> = {
  commodity_name: "Commodity name",
  net_quantity: "Net quantity",
  mrp: "Retail sale price",
  manufacture_date: "Manufactured / packed",
  expiry_date: "Best before / expiry",
  manufacturer: "Manufacturer / packer",
  consumer_care: "Consumer care",
  country_of_origin: "Country of origin",
  fssai_licence: "FSSAI licence",
  batch_number: "Batch number",
};

const DISPLAY_ORDER = Object.keys(FIELD_LABELS);

export default function ScanResultView({ scan }: { scan: ScanResult }) {
  const meta = verdictOf(scan.verdict);
  const physical = scan.physical_analysis ?? {};
  const fields = scan.extracted_fields ?? {};

  return (
    <div className="space-y-6">
      {/* --- verdict header --- */}
      <div className="card p-6">
        <div className="flex flex-wrap items-center gap-6">
          <ScoreRing score={scan.compliance_score} />

          <div className="min-w-[16rem] flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <VerdictBadge verdict={scan.verdict} size="lg" />
              {scan.cache_hit && <span className="chip chip-neutral">cached</span>}
            </div>
            <h1 className="mt-2.5 text-2xl font-bold tracking-tight">
              {scan.product_name ?? "Unidentified product"}
            </h1>
            <p className="mt-1 text-sm text-[var(--muted)]">{meta.description}</p>
            {scan.reasoning && (
              <p className="mt-3 max-w-3xl text-sm leading-relaxed">{scan.reasoning}</p>
            )}
          </div>

          {scan.image_url && (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img
              src={`${API_BASE}${scan.image_url}`}
              alt="Scanned label"
              className="h-40 w-32 rounded-lg border object-cover"
            />
          )}
        </div>

        <dl className="mt-6 grid gap-4 border-t pt-4 text-sm sm:grid-cols-4">
          <Meta label="Violations" value={String(scan.violations.length)} />
          <Meta label="Confidence" value={`${Math.round(scan.confidence * 100)}%`} />
          <Meta
            label="Hallucination coefficient"
            value={scan.hallucination_coefficient.toFixed(3)}
            hint="0 = the narrative matches the verified findings exactly"
          />
          <Meta label="Latency" value={`${scan.latency_ms} ms`} hint={scan.engine ?? ""} />
        </dl>
      </div>

      {/* --- violations --- */}
      <Section
        title={`Violations (${scan.violations.length})`}
        description="Each finding is anchored to the clause it contravenes."
      >
        {scan.violations.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-[var(--muted)]">
            No contraventions detected. Every mandatory declaration is present and
            legible.
          </p>
        ) : (
          <ul className="divide-y">
            {scan.violations.map((violation, index) => (
              <li key={`${violation.clause_id}-${index}`} className="px-5 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <SeverityChip severity={violation.severity} />
                  <span className="font-mono text-xs text-[var(--accent)]">
                    Rule {violation.rule_number}
                  </span>
                  <span className="text-sm font-semibold">{violation.title}</span>
                </div>
                <p className="mt-1.5 text-sm text-[var(--muted)]">{violation.message}</p>
                {(violation.observed || violation.expected) && (
                  <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-xs">
                    {violation.observed && (
                      <span>
                        <span className="text-[var(--muted)]">Observed: </span>
                        <span className="font-medium tone-fail">{violation.observed}</span>
                      </span>
                    )}
                    {violation.expected && (
                      <span>
                        <span className="text-[var(--muted)]">Required: </span>
                        <span className="font-medium tone-pass">{violation.expected}</span>
                      </span>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* --- extracted declarations --- */}
        <Section
          title="Extracted declarations"
          description="Read from the label by OCR."
        >
          <dl className="divide-y">
            {DISPLAY_ORDER.filter((key) => fields[key]).map((key) => (
              <div key={key} className="flex gap-4 px-5 py-2.5 text-sm">
                <dt className="w-40 shrink-0 text-[var(--muted)]">{FIELD_LABELS[key]}</dt>
                <dd className="font-medium break-words">{String(fields[key])}</dd>
              </div>
            ))}
            {DISPLAY_ORDER.filter((key) => !fields[key]).map((key) => (
              <div key={key} className="flex gap-4 px-5 py-2.5 text-sm">
                <dt className="w-40 shrink-0 text-[var(--muted)]">{FIELD_LABELS[key]}</dt>
                <dd className="text-[var(--muted)] italic">not found</dd>
              </div>
            ))}
          </dl>
        </Section>

        {/* --- physical analysis --- */}
        <Section
          title="Physical analysis"
          description="OpenCV measurements against Rules 9(1) and 9(3)."
        >
          <dl className="divide-y">
            <Measure
              label="Principal display panel"
              value={`${physical.estimated_pdp_area_cm2 ?? 0} cm²`}
            />
            <Measure
              label="Minimum height required"
              value={`${physical.min_required_height_mm ?? 0} mm`}
            />
            <Measure
              label="Smallest declaration"
              value={`${physical.smallest_declaration_height_mm ?? 0} mm`}
              failing={
                (physical.smallest_declaration_height_mm ?? 0) > 0 &&
                (physical.smallest_declaration_height_mm ?? 0) <
                  (physical.min_required_height_mm ?? 0)
              }
            />
            <Measure
              label="Lowest contrast ratio"
              value={`${physical.min_contrast_ratio ?? 0} : 1`}
              failing={(physical.min_contrast_ratio ?? 99) < 3}
            />
            <Measure
              label="Focus (Laplacian variance)"
              value={String(physical.blur_score ?? 0)}
              failing={physical.is_blurry}
            />
            <Measure
              label="Glare coverage"
              value={`${((physical.glare_ratio ?? 0) * 100).toFixed(2)}%`}
              failing={physical.has_glare}
            />
            <Measure label="Text regions read" value={String(physical.text_regions ?? 0)} />
          </dl>

          {physical.quality_message && (
            <p className="border-t bg-[var(--warn-bg)] px-5 py-3 text-xs tone-warn">
              {physical.quality_message}
            </p>
          )}
        </Section>
      </div>

      {/* --- citations --- */}
      <Section
        title="Retrieved clauses"
        description="The statutory text this verdict was checked against, ranked by relevance."
      >
        <ul className="divide-y">
          {scan.citations.map((citation) => (
            <li key={citation.clause_id} className="px-5 py-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs text-[var(--accent)]">
                  {citation.clause_id}
                </span>
                <span className="text-sm font-semibold">{citation.title}</span>
                <span className="chip chip-neutral">
                  relevance {citation.score.toFixed(3)}
                </span>
              </div>
              <p className="mt-1.5 text-[13px] leading-relaxed text-[var(--muted)]">
                {citation.excerpt}
              </p>
            </li>
          ))}
        </ul>
      </Section>

      {/* --- raw OCR --- */}
      {scan.ocr_text && (
        <details className="card px-5 py-4">
          <summary className="cursor-pointer text-sm font-semibold">
            Raw OCR text
          </summary>
          <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-[var(--surface-2)] p-4 text-xs leading-relaxed">
            {scan.ocr_text}
          </pre>
        </details>
      )}

      <div className="flex flex-wrap gap-3">
        <Link href={`/report?scan=${scan.id}`} className="btn btn-primary">
          Report this product
        </Link>
        <Link href="/scan" className="btn btn-ghost">
          Scan another label
        </Link>
      </div>
    </div>
  );
}

function Meta({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">
        {label}
      </dt>
      <dd className="mt-0.5 text-lg font-bold tabular-nums">{value}</dd>
      {hint && <p className="text-[11px] text-[var(--muted)]">{hint}</p>}
    </div>
  );
}

function Measure({
  label,
  value,
  failing,
}: {
  label: string;
  value: string;
  failing?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4 px-5 py-2.5 text-sm">
      <span className="text-[var(--muted)]">{label}</span>
      <span className={`font-semibold tabular-nums ${failing ? "tone-fail" : ""}`}>
        {value}
      </span>
    </div>
  );
}
