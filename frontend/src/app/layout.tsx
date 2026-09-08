import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "WellPack — Auto-Compliance Check System",
  description:
    "Scan packaged commodity labels and verify them against the Legal Metrology (Packaged Commodities) Rules, 2011. SIH26034.",
};

const NAV = [
  { href: "/scan", label: "Scan" },
  { href: "/report", label: "Report a product" },
  { href: "/admin", label: "Admin portal" },
];

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <header className="sticky top-0 z-40 border-b bg-[var(--surface)]/90 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center gap-6 px-5 py-3">
            <Link href="/" className="flex items-center gap-2.5">
              <span
                aria-hidden
                className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--brand)] text-sm font-black text-[var(--brand-fg)]"
              >
                W
              </span>
              <span className="leading-tight">
                <span className="block text-[15px] font-bold tracking-tight">
                  WellPack
                </span>
                <span className="block text-[10px] font-medium uppercase tracking-[0.13em] text-[var(--muted)]">
                  Auto-Compliance Check
                </span>
              </span>
            </Link>

            <nav className="ml-auto flex items-center gap-1">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="rounded-lg px-3 py-2 text-sm font-medium text-[var(--muted)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>

        <main className="mx-auto min-h-[calc(100vh-8.5rem)] max-w-7xl px-5 py-8">
          {children}
        </main>

        <footer className="border-t bg-[var(--surface)]">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-5 py-4 text-xs text-[var(--muted)]">
            <p>
              Smart India Hackathon 2026 · Problem Statement SIH26034 · Ministry of
              Consumer Affairs, Food &amp; Public Distribution
            </p>
            <p>Team Double_Triple_Stack</p>
          </div>
        </footer>
      </body>
    </html>
  );
}
