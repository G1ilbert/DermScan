"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ScanHistoryPage as Page, api, getAccessToken } from "@/lib/api";

const PAGE_SIZE = 20;

function bandStyle(band: string | null | undefined): string {
  if (band === "result") return "bg-red-100 text-red-800";
  if (band === "uncertain") return "bg-yellow-100 text-yellow-800";
  if (band === "low_quality") return "bg-slate-100 text-slate-700";
  return "bg-slate-100 text-slate-600";
}

export default function HistoryPage() {
  const router = useRouter();
  const [page, setPage] = useState<Page | null>(null);
  const [pageNum, setPageNum] = useState(1);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getAccessToken()) {
      router.push("/login?next=/history");
      return;
    }
    let cancelled = false;
    api
      .getHistory(pageNum, PAGE_SIZE)
      .then((res) => {
        if (!cancelled) setPage(res.data);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load history");
      });
    return () => {
      cancelled = true;
    };
  }, [pageNum, router]);

  const totalPages = page ? Math.max(Math.ceil(page.total / page.page_size), 1) : 1;

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-3xl font-bold">My scans</h1>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      {!page && !error && <p className="mt-6 text-slate-600">Loading…</p>}

      {page && page.items.length === 0 && (
        <p className="mt-6 text-slate-600">
          No scans yet.{" "}
          <Link href="/scan" className="text-blue-600 hover:underline">
            Run your first scan
          </Link>
          .
        </p>
      )}

      <ul className="mt-6 divide-y rounded-2xl border bg-white">
        {page?.items.map((s) => (
          <li key={s.scan_id} className="flex items-center justify-between p-4">
            <div>
              <p className="text-sm font-medium text-slate-900">
                {new Date(s.created_at).toLocaleString()}
              </p>
              <p className="text-xs text-slate-500">scan {s.scan_id.slice(0, 8)}…</p>
            </div>
            <div className="flex items-center gap-3">
              <span className={`rounded-full px-2 py-0.5 text-xs ${bandStyle(s.confidence_band)}`}>
                {s.confidence_band ?? s.status}
              </span>
              {s.confidence !== null && (
                <span className="text-sm text-slate-700">{(s.confidence * 100).toFixed(0)}%</span>
              )}
              <Link
                href={`/scan/result/${encodeURIComponent(s.job_id)}`}
                className="text-sm text-blue-600 hover:underline"
              >
                View
              </Link>
            </div>
          </li>
        ))}
      </ul>

      {page && page.total > page.page_size && (
        <div className="mt-6 flex items-center justify-between">
          <button
            onClick={() => setPageNum((p) => Math.max(p - 1, 1))}
            disabled={pageNum === 1}
            className="rounded-md border px-3 py-1.5 text-sm disabled:opacity-50"
          >
            Previous
          </button>
          <span className="text-sm text-slate-600">
            Page {pageNum} / {totalPages}
          </span>
          <button
            onClick={() => setPageNum((p) => Math.min(p + 1, totalPages))}
            disabled={pageNum >= totalPages}
            className="rounded-md border px-3 py-1.5 text-sm disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}
    </main>
  );
}
