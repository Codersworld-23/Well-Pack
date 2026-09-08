import Link from "next/link";

const PIPELINE = [
  {
    step: "1",
    title: "Scan the label",
    body: "The capture is checked on the edge for blur and glare before anything is uploaded.",
  },
  {
    step: "2",
    title: "Computer vision",
    body: "OCR reads every declaration; OpenCV measures character height in millimetres and text/background contrast.",
  },
  {
    step: "3",
    title: "RAG verification",
    body: "The extracted label queries a live vector index of the 2011 Rules and is checked clause by clause.",
  },
  {
    step: "4",
    title: "Compliance verdict",
    body: "A structured pass/fail result with cited clauses, cached for future scans and logged for regulators.",
  },
];

const DIFFERENTIATORS = [
  {
    title: "Dynamic rule corpus",
    body: "Policies are not hardcoded. An admin uploads an amendment and the very next scan is verified against it — no redeploy, no code change.",
  },
  {
    title: "Semantic caching",
    body: "A product already scanned returns its verdict from a cosine-similarity cache, so common items cost almost nothing to re-verify.",
  },
  {
    title: "Multi-modal verification",
    body: "Pixel-level measurement (font height, WCAG contrast) and statutory text comprehension run in one pipeline, not two disconnected tools.",
  },
];

export default function Home() {
  return (
    <div className="space-y-14">
      <section className="grid items-center gap-10 lg:grid-cols-[1.15fr_1fr]">
        <div>
          <span className="chip chip-neutral">Problem Statement SIH26034</span>
          <h1 className="mt-4 text-4xl font-bold leading-[1.12] tracking-tight sm:text-5xl">
            Every packaged commodity,
            <br />
            checked against the law.
          </h1>
          <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-[var(--muted)]">
            WellPack scans a product label and verifies it against the Legal Metrology
            (Packaged Commodities) Rules, 2011 — mandatory declarations, net quantity,
            MRP, manufacture date, consumer care, character height and colour contrast —
            returning a cited verdict in seconds.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link href="/scan" className="btn btn-primary">
              Scan a label
            </Link>
            <Link href="/admin" className="btn btn-ghost">
              Open admin portal
            </Link>
          </div>
        </div>

        <div className="card p-6">
          <p className="text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">
            What gets checked
          </p>
          <ul className="mt-4 space-y-2.5 text-sm">
            {[
              ["Rule 6(1)(a)", "Manufacturer / packer / importer with complete address"],
              ["Rule 6(1)(b)", "Common or generic name of the commodity"],
              ["Rule 6(1)(c)", "Net quantity in standard metric units"],
              ["Rule 6(1)(d)", "Month and year of manufacture or packing"],
              ["Rule 6(1)(e)", "MRP inclusive of all taxes"],
              ["Rule 6(1)(f)", "Consumer care contact details"],
              ["Rule 9(1)", "Conspicuous contrast against the background"],
              ["Rule 9(3)", "Minimum character height, Second Schedule"],
            ].map(([rule, text]) => (
              <li key={rule} className="flex gap-3">
                <span className="w-24 shrink-0 font-mono text-xs text-[var(--accent)]">
                  {rule}
                </span>
                <span className="text-[var(--muted)]">{text}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section>
        <h2 className="text-sm font-bold uppercase tracking-wider text-[var(--muted)]">
          How a scan becomes a verdict
        </h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {PIPELINE.map((item) => (
            <div key={item.step} className="card p-5">
              <span className="grid h-7 w-7 place-items-center rounded-full bg-[var(--brand)] text-xs font-bold text-[var(--brand-fg)]">
                {item.step}
              </span>
              <h3 className="mt-3 text-sm font-bold">{item.title}</h3>
              <p className="mt-1.5 text-[13px] leading-relaxed text-[var(--muted)]">
                {item.body}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-sm font-bold uppercase tracking-wider text-[var(--muted)]">
          What makes it different
        </h2>
        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          {DIFFERENTIATORS.map((item) => (
            <div key={item.title} className="card p-5">
              <h3 className="text-sm font-bold">{item.title}</h3>
              <p className="mt-1.5 text-[13px] leading-relaxed text-[var(--muted)]">
                {item.body}
              </p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
