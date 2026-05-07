"use client";

import type { ScanResult } from "@/lib/api";
import ResultCard from "./ResultCard";

interface Props {
  scan: ScanResult;
}

export default function ConfidenceGate({ scan }: Props) {
  if (scan.confidence_band === "low_quality") {
    return (
      <div className="rounded-2xl border border-amber-300 bg-amber-50 p-6">
        <h3 className="text-lg font-semibold text-amber-900">Image quality too low</h3>
        <p className="mt-2 text-sm text-amber-800">
          The model is not confident enough to produce a result. Please retake the photo in good
          lighting, with the lesion clearly in focus and centered in the frame.
        </p>
      </div>
    );
  }

  if (scan.confidence_band === "uncertain") {
    return (
      <div className="rounded-2xl border border-yellow-300 bg-yellow-50 p-6">
        <h3 className="text-lg font-semibold text-yellow-900">Result uncertain</h3>
        <p className="mt-2 text-sm text-yellow-800">
          The model produced a borderline prediction
          {scan.confidence !== null && ` (${(scan.confidence * 100).toFixed(1)}% confidence)`}.
          We recommend you consult a dermatologist for an in-person evaluation.
        </p>
        <ResultCard scan={scan} dimmed />
      </div>
    );
  }

  return <ResultCard scan={scan} />;
}
