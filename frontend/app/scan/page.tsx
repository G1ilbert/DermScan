"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import ConsentModal from "@/components/ConsentModal";
import ImageUploader from "@/components/ImageUploader";
import { api, getAccessToken } from "@/lib/api";

export default function ScanPage() {
  const router = useRouter();
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!pendingFile) return;
    if (!getAccessToken()) {
      router.push("/login?next=/scan");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.submitScan(pendingFile);
      const jobId = res.data?.job_id;
      if (!jobId) throw new Error("Server did not return a job id");
      router.push(`/scan/result/${jobId}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="mx-auto max-w-2xl px-6 py-12">
      <h1 className="text-3xl font-bold text-slate-900">New scan</h1>
      <p className="mt-2 text-sm text-slate-600">Upload a clear photo of the skin area you want screened.</p>

      <div className="mt-6">
        <ImageUploader onSelect={(f) => setPendingFile(f)} />
      </div>

      {pendingFile && (
        <div className="mt-4 rounded-md border bg-slate-50 p-3 text-sm text-slate-700">
          Selected: <strong>{pendingFile.name}</strong> ({(pendingFile.size / 1024).toFixed(1)} KB)
        </div>
      )}

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <ConsentModal
        open={!!pendingFile && !submitting}
        onAccept={submit}
        onCancel={() => setPendingFile(null)}
      />

      {submitting && <p className="mt-4 text-sm text-slate-600">Uploading and queuing for analysis…</p>}
    </main>
  );
}
