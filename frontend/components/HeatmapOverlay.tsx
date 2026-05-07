"use client";

import { useState } from "react";

interface Props {
  imageUrl: string | null;
  heatmapUrl: string | null;
}

export default function HeatmapOverlay({ imageUrl, heatmapUrl }: Props) {
  const [showHeatmap, setShowHeatmap] = useState(true);

  if (!imageUrl) return null;

  return (
    <div className="mt-5">
      <div className="relative overflow-hidden rounded-xl border bg-slate-100">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={imageUrl} alt="Lesion" className="block w-full" />
        {heatmapUrl && showHeatmap && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={heatmapUrl}
            alt="GradCAM heatmap"
            className="absolute inset-0 h-full w-full mix-blend-multiply opacity-80"
          />
        )}
      </div>
      {heatmapUrl && (
        <label className="mt-2 flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={showHeatmap} onChange={(e) => setShowHeatmap(e.target.checked)} />
          Show attention heatmap
        </label>
      )}
    </div>
  );
}
