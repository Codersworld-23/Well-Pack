import Link from "next/link";
import { notFound } from "next/navigation";
import { API_BASE, type ScanResult } from "@/lib/api";
import ScanResultView from "@/components/ScanResultView";

export const dynamic = "force-dynamic";

export default async function ScanDetailPage(props: PageProps<"/scan/[id]">) {
  const { id } = await props.params;

  const response = await fetch(`${API_BASE}/api/scans/${id}`, { cache: "no-store" });
  if (response.status === 404) notFound();
  if (!response.ok) {
    return (
      <div className="card p-6">
        <p className="text-sm font-bold tone-fail">Could not load this scan</p>
        <p className="mt-1 text-sm text-[var(--muted)]">
          The API returned {response.status}. Confirm the backend is running.
        </p>
      </div>
    );
  }

  const scan: ScanResult = await response.json();

  return (
    <div className="space-y-5">
      <Link href="/admin/scans" className="btn btn-ghost">
        ← Back to scan log
      </Link>
      <ScanResultView scan={scan} />
    </div>
  );
}
