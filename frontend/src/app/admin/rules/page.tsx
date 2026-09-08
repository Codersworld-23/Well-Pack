"use client";

import { useEffect, useRef, useState } from "react";
import { api, type RuleClause, type Severity } from "@/lib/api";
import { EmptyState, Section, SeverityChip } from "@/components/ui";

const FIELDS = [
  "manufacturer",
  "commodity_name",
  "net_quantity",
  "mrp",
  "manufacture_date",
  "consumer_care",
  "country_of_origin",
  "font_height",
  "contrast",
  "layout",
  "general",
];

const BLANK = {
  rule_number: "",
  title: "",
  text: "",
  field: "general",
  severity: "major" as Severity,
  active: true,
};

export default function RulesPage() {
  const [rules, setRules] = useState<RuleClause[]>([]);
  const [draft, setDraft] = useState({ ...BLANK });
  const [editing, setEditing] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState<{ clause_id: string; title: string; score: number }[] | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => api.listRules().then(setRules).catch(() => setRules([]));
  useEffect(() => {
    void load();
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      if (editing) {
        await api.updateRule(editing, draft);
        setNotice(`Clause ${editing} updated — corpus re-embedded, cache cleared.`);
      } else {
        const created = await api.createRule(draft);
        setNotice(`Clause ${created.clause_id} added — it applies to the next scan.`);
      }
      setDraft({ ...BLANK });
      setEditing(null);
      await load();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function upload(file: File) {
    setBusy(true);
    try {
      const result = await api.uploadPolicy(file);
      setNotice(result.message);
      await load();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      {notice && (
        <div className="card border-[color-mix(in_srgb,var(--brand)_35%,transparent)] bg-[var(--surface-2)] px-4 py-3 text-sm">
          {notice}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_1.15fr]">
        <div className="space-y-6">
          <Section
            title={editing ? `Edit ${editing}` : "Add a clause"}
            description="Saved clauses are embedded immediately; no redeploy is needed."
          >
            <form onSubmit={save} className="space-y-3 px-5 py-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <span className="label">Rule number</span>
                  <input
                    className="input"
                    required
                    placeholder="6(1)(h)"
                    value={draft.rule_number}
                    onChange={(e) => setDraft({ ...draft, rule_number: e.target.value })}
                  />
                </div>
                <div>
                  <span className="label">Severity</span>
                  <select
                    className="input"
                    value={draft.severity}
                    onChange={(e) =>
                      setDraft({ ...draft, severity: e.target.value as Severity })
                    }
                  >
                    {["critical", "major", "minor", "info"].map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <span className="label">Title</span>
                <input
                  className="input"
                  required
                  value={draft.title}
                  onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                />
              </div>

              <div>
                <span className="label">Clause text</span>
                <textarea
                  className="input min-h-32"
                  required
                  placeholder="Verbatim statutory text — this is what the retriever indexes and the verifier cites."
                  value={draft.text}
                  onChange={(e) => setDraft({ ...draft, text: e.target.value })}
                />
              </div>

              <div>
                <span className="label">Declaration field</span>
                <select
                  className="input"
                  value={draft.field}
                  onChange={(e) => setDraft({ ...draft, field: e.target.value })}
                >
                  {FIELDS.map((f) => (
                    <option key={f} value={f}>
                      {f}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex gap-3">
                <button className="btn btn-primary flex-1" disabled={busy}>
                  {busy ? "Saving…" : editing ? "Update clause" : "Add clause"}
                </button>
                {editing && (
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => {
                      setEditing(null);
                      setDraft({ ...BLANK });
                    }}
                  >
                    Cancel
                  </button>
                )}
              </div>
            </form>
          </Section>

          <Section
            title="Upload a policy document"
            description="A .txt or .md circular is split into clauses and indexed on the spot."
          >
            <div className="px-5 py-4">
              <button
                className="btn btn-ghost w-full"
                disabled={busy}
                onClick={() => fileRef.current?.click()}
              >
                Choose policy file
              </button>
              <input
                ref={fileRef}
                type="file"
                accept=".txt,.md"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void upload(file);
                  e.target.value = "";
                }}
              />
              <p className="mt-2 text-xs text-[var(--muted)]">
                Uploading clears the semantic cache, so verdicts cached under the previous
                corpus are never served after a rule change.
              </p>
            </div>
          </Section>

          <Section
            title="Retrieval preview"
            description="See exactly which clauses a label would retrieve."
          >
            <div className="space-y-3 px-5 py-4">
              <div className="flex gap-2">
                <input
                  className="input"
                  placeholder="e.g. missing mrp declaration"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                <button
                  className="btn btn-ghost"
                  onClick={() =>
                    api
                      .previewRetrieval(query)
                      .then((r) => setPreview(r.results))
                      .catch(() => setPreview([]))
                  }
                >
                  Query
                </button>
              </div>
              {preview && (
                <ul className="space-y-1.5">
                  {preview.length === 0 && (
                    <li className="text-xs text-[var(--muted)]">No clauses matched.</li>
                  )}
                  {preview.map((hit) => (
                    <li key={hit.clause_id} className="flex items-center gap-2 text-xs">
                      <span className="font-mono text-[var(--accent)]">{hit.clause_id}</span>
                      <span className="truncate text-[var(--muted)]">{hit.title}</span>
                      <span className="ml-auto tabular-nums">{hit.score.toFixed(3)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Section>
        </div>

        <Section
          title={`Rule corpus (${rules.length})`}
          description="Deactivating a clause removes it from retrieval immediately."
        >
          {rules.length === 0 ? (
            <EmptyState title="No clauses indexed" />
          ) : (
            <ul className="divide-y">
              {rules.map((rule) => (
                <li key={rule.clause_id} className="px-5 py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-[var(--accent)]">
                      Rule {rule.rule_number}
                    </span>
                    <SeverityChip severity={rule.severity} />
                    <span className="chip chip-neutral">{rule.field}</span>
                    {!rule.active && <span className="chip chip-fail">inactive</span>}
                    {rule.source === "admin" && (
                      <span className="chip chip-neutral">admin v{rule.version}</span>
                    )}
                  </div>
                  <p className="mt-1.5 text-sm font-semibold">{rule.title}</p>
                  <p className="mt-1 line-clamp-3 text-[13px] leading-relaxed text-[var(--muted)]">
                    {rule.text}
                  </p>
                  <div className="mt-2.5 flex gap-2">
                    <button
                      className="btn btn-ghost !px-2.5 !py-1 !text-xs"
                      onClick={() => {
                        setEditing(rule.clause_id);
                        setDraft({
                          rule_number: rule.rule_number,
                          title: rule.title,
                          text: rule.text,
                          field: rule.field,
                          severity: rule.severity,
                          active: rule.active,
                        });
                        window.scrollTo({ top: 0, behavior: "smooth" });
                      }}
                    >
                      Edit
                    </button>
                    <button
                      className="btn btn-ghost !px-2.5 !py-1 !text-xs"
                      onClick={() => api.toggleRule(rule.clause_id).then(load)}
                    >
                      {rule.active ? "Deactivate" : "Activate"}
                    </button>
                    <button
                      className="btn btn-danger !px-2.5 !py-1 !text-xs"
                      onClick={() => api.deleteRule(rule.clause_id).then(load)}
                    >
                      Delete
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>
    </div>
  );
}
