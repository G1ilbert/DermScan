"use client";

import type { ScanResult } from "@/lib/api";
import { api } from "@/lib/api";
import HeatmapOverlay from "./HeatmapOverlay";

interface Props {
  scan: ScanResult;
  dimmed?: boolean;
}

const LABEL_DESCRIPTIONS: Record<string, string> = {
  melanoma: "Melanoma — high-risk skin cancer",
  melanocytic_nevus: "Melanocytic nevus (mole) — typically benign",
  basal_cell_carcinoma: "Basal cell carcinoma — common skin cancer, slow-growing",
  actinic_keratosis: "Actinic keratosis — pre-cancerous lesion",
  benign_keratosis: "Benign keratosis — non-cancerous",
  dermatofibroma: "Dermatofibroma — benign skin nodule",
  vascular_lesion: "Vascular lesion — typically benign",
};

export default function ResultCard({ scan, dimmed = false }: Props) {
  const label = scan.prediction?.label ?? "—";
  const desc = LABEL_DESCRIPTIONS[label] ?? label;
  const isMalignant = label === "melanoma" || label === "basal_cell_carcinoma";

  return (
    <div className={`rounded-2xl border bg-white p-6 ${dimmed ? "opacity-80" : ""}`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-500">Predicted class</p>
          <p className="mt-1 text-xl font-semibold text-slate-900">{desc}</p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-medium ${
            isMalignant ? "bg-red-100 text-red-800" : "bg-emerald-100 text-emerald-800"
          }`}
        >
          {isMalignant ? "Higher risk" : "Lower risk"}
        </span>
      </div>

      {scan.confidence !== null && (
        <div className="mt-4">
          <div className="flex justify-between text-xs text-slate-500">
            <span>Confidence</span>
            <span>{(scan.confidence * 100).toFixed(1)}%</span>
          </div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-200">
            <div className="h-full bg-blue-500" style={{ width: `${scan.confidence * 100}%` }} />
          </div>
        </div>
      )}

      <HeatmapOverlay imageUrl={scan.image_url} heatmapUrl={scan.heatmap_url} />

      <div className="mt-6 flex flex-wrap gap-3">
        <a
          href={api.reportUrl(scan.scan_id)}
          className="inline-flex rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
          download
        >
          Download PDF report
        </a>
        <a
          href={api.fhirUrl(scan.scan_id)}
          className="inline-flex rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
          target="_blank"
          rel="noreferrer"
        >
          FHIR JSON
        </a>
      </div>
    </div>
  );
}
