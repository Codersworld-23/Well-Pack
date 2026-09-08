"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Quality, type ScanResult } from "@/lib/api";
import ScanResultView from "@/components/ScanResultView";

type Stage =
  | { kind: "idle" }
  | { kind: "prechecking" }
  | { kind: "blocked"; quality: Quality }
  | { kind: "scanning"; step: string }
  | { kind: "done"; scan: ScanResult }
  | { kind: "error"; message: string };

const STEPS = [
  "Uploading capture…",
  "Reading the label (OCR)…",
  "Measuring character height and contrast…",
  "Retrieving Legal Metrology clauses…",
  "Cross-referencing declarations…",
];

export default function ScanPage() {
  const [stage, setStage] = useState<Stage>({ kind: "idle" });
  const [preview, setPreview] = useState<string | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  const runScan = useCallback(async (file: File) => {
    setStage({ kind: "scanning", step: STEPS[0] });
    let index = 0;
    const ticker = setInterval(() => {
      index = Math.min(index + 1, STEPS.length - 1);
      setStage({ kind: "scanning", step: STEPS[index] });
    }, 900);

    try {
      const scan = await api.scan(file);
      setStage({ kind: "done", scan });
    } catch (error) {
      setStage({
        kind: "error",
        message: error instanceof Error ? error.message : "Scan failed",
      });
    } finally {
      clearInterval(ticker);
    }
  }, []);

  const handleFile = useCallback(
    async (file: File) => {
      if (preview) URL.revokeObjectURL(preview);
      setPreview(URL.createObjectURL(file));
      setPendingFile(file);
      setStage({ kind: "prechecking" });

      // Edge pre-processing gate: reject a blurred or glared capture before
      // spending an OCR + retrieval round-trip on it.
      try {
        const quality = await api.precheck(file);
        if (!quality.quality_ok) {
          setStage({ kind: "blocked", quality });
          return;
        }
      } catch {
        /* precheck is advisory - fall through to the scan */
      }
      await runScan(file);
    },
    [preview, runScan],
  );

  if (stage.kind === "done") {
    return (
      <div className="space-y-5">
        <button
          className="btn btn-ghost"
          onClick={() => {
            setStage({ kind: "idle" });
            setPreview(null);
            setPendingFile(null);
          }}
        >
          ← Scan another label
        </button>
        <ScanResultView scan={stage.scan} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-bold tracking-tight">Scan a product label</h1>
      <p className="mt-1.5 text-sm text-[var(--muted)]">
        Photograph the principal display panel straight on, filling the frame, in even
        light. On a phone the camera opens directly.
      </p>

      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const file = event.dataTransfer.files?.[0];
          if (file) void handleFile(file);
        }}
        className={`card mt-6 grid place-items-center px-6 py-12 text-center transition-colors ${
          dragging ? "border-[var(--brand)] bg-[var(--surface-2)]" : ""
        }`}
      >
        {preview ? (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            src={preview}
            alt="Selected label"
            className="mb-5 max-h-64 rounded-lg border object-contain"
          />
        ) : (
          <div
            aria-hidden
            className="mb-4 grid h-14 w-14 place-items-center rounded-full bg-[var(--surface-2)] text-2xl"
          >
            ⬚
          </div>
        )}

        {stage.kind === "scanning" || stage.kind === "prechecking" ? (
          <p className="pulsing text-sm font-medium">
            {stage.kind === "prechecking" ? "Checking capture quality…" : stage.step}
          </p>
        ) : (
          <>
            <p className="text-sm font-semibold">
              Drop a label photo here, or choose a file
            </p>
            <p className="mt-1 text-xs text-[var(--muted)]">
              JPEG, PNG or WebP · up to 12 MB
            </p>
            <div className="mt-5 flex flex-wrap justify-center gap-3">
              <button
                className="btn btn-primary"
                onClick={() => inputRef.current?.click()}
              >
                Choose image
              </button>
              {pendingFile && (
                <button
                  className="btn btn-ghost"
                  onClick={() => void runScan(pendingFile)}
                >
                  Scan anyway
                </button>
              )}
            </div>
          </>
        )}

        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void handleFile(file);
            event.target.value = "";
          }}
        />
      </div>

      {stage.kind === "blocked" && (
        <div className="card mt-4 border-[color-mix(in_srgb,var(--warn)_35%,transparent)] bg-[var(--warn-bg)] p-4">
          <p className="text-sm font-bold tone-warn">Retake recommended</p>
          <p className="mt-1 text-sm">{stage.quality.quality_message}</p>
          <p className="mt-2 text-xs text-[var(--muted)]">
            Focus score {stage.quality.blur_score} · glare coverage{" "}
            {(stage.quality.glare_ratio * 100).toFixed(2)}%. A degraded capture produces
            unreliable verdicts, so WellPack asks for a retake before querying the
            backend.
          </p>
        </div>
      )}

      {stage.kind === "error" && (
        <div className="card mt-4 border-[color-mix(in_srgb,var(--fail)_35%,transparent)] bg-[var(--fail-bg)] p-4">
          <p className="text-sm font-bold tone-fail">Scan failed</p>
          <p className="mt-1 text-sm">{stage.message}</p>
          <p className="mt-2 text-xs text-[var(--muted)]">
            Confirm the API is running on {" "}
            <code className="font-mono">
              {process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"}
            </code>
            .
          </p>
        </div>
      )}
    </div>
  );
}
