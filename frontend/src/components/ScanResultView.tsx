"use client";

import Link from "next/link";
import { useState } from "react";
import { API_BASE, api, type ReportFormat, type ScanResult, verdictOf } from "@/lib/api";
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

const HALLUCINATION_FACTORS: { key: string; label: string; description: string }[] = [
  {
    key: "citation_drift",
    label: "Citation drift",
    description: "Clause IDs cited by LLM that were never retrieved (fabricated references)",
  },
  {
    key: "finding_drift",
    label: "Finding drift",
    description: "Disagreement between LLM-claimed violations and rule engine findings",
  },
  {
    key: "entity_drift",
    label: "Entity drift",
    description: "Numbers/prices in LLM summary not present in OCR text or extracted fields",
  },
  {
    key: "penalty_drift",
    label: "Penalty drift",
    description: "Fabricated statutes, IPC sections, or non-existent legal penalties",
  },
  {
    key: "confidence_drift",
    label: "Confidence drift",
    description: "LLM over-asserting certainty beyond what the OCR quality supports",
  },
  {
    key: "ocr_grounding_score",
    label: "OCR grounding",
    description: "Fraction of LLM reasoning words anchored in the actual OCR text (higher = better)",
  },
  {
    key: "clause_alignment_score",
    label: "Clause alignment",
    description: "Fraction of engine violations explained in the LLM narrative (higher = better)",
  },
];

export default function ScanResultView({ scan }: { scan: ScanResult }) {
  const meta = verdictOf(scan.verdict);
  const physical = scan.physical_analysis ?? {};
  const fields = scan.extracted_fields ?? {};
  const breakdown = scan.hallucination_breakdown ?? {};
  const skipped = (scan as any).skipped_checks ?? [];

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
              {(physical as any).ocr_preprocessed && (
                <span className="chip chip-neutral" title="CLAHE + denoising + deskew applied">
                  preprocessed
                </span>
              )}
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
            label="Hallucination coeff."
            value={scan.hallucination_coefficient.toFixed(3)}
            hint="0 = narrative matches findings exactly · > 0.35 = rejected"
            tone={
              scan.hallucination_coefficient > 0.35
                ? "fail"
                : scan.hallucination_coefficient > 0.20
                  ? "warn"
                  : undefined
            }
          />
          <Meta label="Latency" value={`${scan.latency_ms} ms`} hint={scan.engine ?? ""} />
        </dl>

        <ReportDownload scanId={scan.id} />
      </div>

      {/* --- analyst note --- */}
      {scan.analyst_note && (
        <div className="card border-[color-mix(in_srgb,var(--warn)_35%,transparent)] bg-[var(--warn-bg)] px-5 py-4">
          <p className="text-xs font-bold uppercase tracking-wider tone-warn">Analyst note</p>
          <p className="mt-1 text-sm">{scan.analyst_note}</p>
        </div>
      )}

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
            <Measure
              label="ORB keypoints"
              value={`${physical.orb_keypoints ?? 0} (${(physical as any).feature_richness ?? "—"})`}
              hint={orbHint((physical as any).feature_richness)}
            />
          </dl>

          {physical.quality_message && (
            <p className="border-t bg-[var(--warn-bg)] px-5 py-3 text-xs tone-warn">
              {physical.quality_message}
            </p>
          )}

          {/* Uncertain OCR regions */}
          {(physical as any).uncertain_region_count > 0 && (
            <div className="border-t px-5 py-3">
              <p className="text-xs font-semibold text-[var(--muted)]">
                Low-confidence OCR regions ({(physical as any).uncertain_region_count})
              </p>
              <p className="mt-1 text-xs text-[var(--muted)]">
                These text regions had OCR confidence &lt; 50% and may be misread:
              </p>
              <ul className="mt-1.5 flex flex-wrap gap-1.5">
                {((physical as any).uncertain_regions ?? []).slice(0, 8).map(
                  (t: string, i: number) => (
                    <li key={i} className="chip chip-warn text-[11px]">
                      {t}
                    </li>
                  ),
                )}
              </ul>
            </div>
          )}
        </Section>
      </div>

      {/* --- hallucination breakdown --- */}
      {Object.keys(breakdown).length > 0 && (
        <Section
          title="Hallucination breakdown"
          description={`Overall coefficient: ${scan.hallucination_coefficient.toFixed(3)} — how closely the LLM narrative matches the machine-verified findings.`}
        >
          <div className="divide-y">
            {HALLUCINATION_FACTORS.map(({ key, label, description }) => {
              const raw = (breakdown as Record<string, number>)[key];
              if (raw === undefined) return null;
              // For grounding/alignment, higher is better; invert for display.
              const isInverse = key === "ocr_grounding_score" || key === "clause_alignment_score";
              const displayVal = isInverse ? raw : raw;
              const barPct = isInverse
                ? Math.round(raw * 100)
                : Math.round((1 - Math.min(1, raw)) * 100);
              const barTone =
                barPct >= 80
                  ? "var(--pass)"
                  : barPct >= 50
                    ? "var(--warn)"
                    : "var(--fail)";

              return (
                <div key={key} className="px-5 py-3">
                  <div className="flex items-center justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-semibold">{label}</p>
                      <p className="text-[11px] text-[var(--muted)]">{description}</p>
                    </div>
                    <span className="shrink-0 font-mono text-sm font-bold tabular-nums">
                      {displayVal.toFixed(3)}
                    </span>
                  </div>
                  <div className="mt-2 h-1.5 w-full rounded-full bg-[var(--surface-2)]">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${barPct}%`, backgroundColor: barTone }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {/* --- rule checks --- */}
      <Section
        title={`Rule checks (${scan.checks?.length ?? 0} run${skipped.length > 0 ? `, ${skipped.length} skipped` : ""})`}
        description="Every check that ran against this label."
      >
        {(!scan.checks || scan.checks.length === 0) ? (
          <p className="px-5 py-6 text-center text-sm text-[var(--muted)]">No checks recorded.</p>
        ) : (
          <ul className="divide-y">
            {scan.checks.map((check: any, i: number) => (
              <li key={i} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                <span className={`h-2 w-2 shrink-0 rounded-full ${check.passed ? "bg-[var(--pass)]" : "bg-[var(--fail)]"}`} />
                <span className="flex-1">{check.name.replaceAll("_", " ")}</span>
                <span className="font-mono text-xs text-[var(--muted)]">
                  Rule {check.rule_number}
                </span>
                {check.detail && (
                  <span className="text-xs text-[var(--muted)] truncate max-w-[140px]">
                    {check.detail}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}

        {skipped.length > 0 && (
          <div className="border-t px-5 py-3">
            <p className="text-xs font-semibold text-[var(--muted)]">
              Skipped checks — clause inactive or removed from corpus
            </p>
            <ul className="mt-1.5 space-y-1">
              {skipped.map((s: any, i: number) => (
                <li key={i} className="text-xs text-[var(--muted)]">
                  <span className="font-mono">{s.clause_id}</span> — {s.name.replaceAll("_", " ")}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Section>

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
            <span className="ml-2 font-normal text-[var(--muted)] text-xs">
              (confidence: {Math.round((scan as any).ocr_confidence * 100)}%)
            </span>
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

function orbHint(richness: string | undefined): string {
  switch (richness) {
    case "high":
      return "Rich features — excellent for tamper/counterfeit detection";
    case "medium":
      return "Adequate features for comparison";
    case "low":
      return "Sparse features — comparison may be unreliable";
    case "very_low":
      return "Too few features for reliable comparison";
    default:
      return "";
  }
}

function Meta({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "pass" | "warn" | "fail";
}) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">
        {label}
      </dt>
      <dd className={`mt-0.5 text-lg font-bold tabular-nums ${tone ? `tone-${tone}` : ""}`}>
        {value}
      </dd>
      {hint && <p className="text-[11px] text-[var(--muted)]">{hint}</p>}
    </div>
  );
}

/**
 * Download the scan as a compliance report.
 *
 * Two formats, because they serve different moments: the PDF is what gets
 * filed or served, while the DOCX is for the officer who needs to correct a
 * misread declaration or add observations before issuing it.
 */
function ReportDownload({ scanId }: { scanId: string }) {
  const [busy, setBusy] = useState<ReportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function download(format: ReportFormat) {
    setBusy(format);
    setError(null);
    try {
      await api.downloadReport(scanId, format);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Report download failed.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mt-4 border-t pt-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">
          Compliance report
        </span>
        <button
          type="button"
          onClick={() => download("pdf")}
          disabled={busy !== null}
          className="rounded-lg border px-3 py-1.5 text-sm font-semibold transition hover:bg-[var(--surface-2)] disabled:opacity-50"
        >
          {busy === "pdf" ? "Preparing…" : "Download PDF"}
        </button>
        <button
          type="button"
          onClick={() => download("docx")}
          disabled={busy !== null}
          className="rounded-lg border px-3 py-1.5 text-sm font-semibold transition hover:bg-[var(--surface-2)] disabled:opacity-50"
        >
          {busy === "docx" ? "Preparing…" : "Download editable (.docx)"}
        </button>
      </div>
      <p className="mt-1.5 text-[11px] text-[var(--muted)]">
        The PDF is the filing copy. The .docx opens in Word so an officer can correct a
        misread declaration and add observations before issuing it.
      </p>
      {error && <p className="mt-1.5 text-xs tone-fail">{error}</p>}
    </div>
  );
}

function Measure({
  label,
  value,
  failing,
  hint,
}: {
  label: string;
  value: string;
  failing?: boolean;
  hint?: string;
}) {
  return (
    <div className="px-5 py-2.5 text-sm">
      <div className="flex items-center justify-between gap-4">
        <span className="text-[var(--muted)]">{label}</span>
        <span className={`font-semibold tabular-nums ${failing ? "tone-fail" : ""}`}>
          {value}
        </span>
      </div>
      {hint && <p className="mt-0.5 text-[11px] text-[var(--muted)]">{hint}</p>}
    </div>
  );
}
