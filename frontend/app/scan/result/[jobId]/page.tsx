"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import ConfidenceGate from "@/components/ConfidenceGate";
import { POLL_INTERVAL_MS, ScanResult, api, getAccessToken } from "@/lib/api";

export default function ResultPage() {
  const router = useRouter();
  const params = useParams<{ jobId: string }>();
  const jobId = params?.jobId;

  const [scan, setScan] = useState<ScanResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    if (!getAccessToken()) {
      router.push(`/login?next=/scan/result/${jobId}`);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      try {
        const res = await api.getScanResult(jobId);
        if (cancelled) return;
        if (res.data) {
          setScan(res.data);
          if (res.data.status === "done" || res.data.status === "failed") {
            return;
          }
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Unknown error");
        return;
      }
      timer = setTimeout(tick, POLL_INTERVAL_MS);
    };
    tick();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId, router]);

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="text-3xl font-bold text-slate-900">Scan result</h1>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      {!scan && !error && <p className="mt-6 text-slate-600">Loading…</p>}

      {scan && scan.status === "pending" && (
        <p className="mt-6 text-slate-600">Queued — waiting for a worker…</p>
      )}
      {scan && scan.status === "processing" && (
        <p className="mt-6 text-slate-600">Processing — running inference…</p>
      )}
      {scan && scan.status === "failed" && (
        <p className="mt-6 text-red-600">Inference failed: {scan.error_message ?? "unknown error"}</p>
      )}

      {scan && scan.status === "done" && (
        <div className="mt-6">
          <ConfidenceGate scan={scan} />
          <div className="mt-6 flex">
            <Link
              href="/"
              className="inline-flex rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
            >
              Back to home
            </Link>
          </div>
        </div>
      )}
    </main>
  );
}
