"use client";

import { useCallback, useRef, useState } from "react";

interface Props {
  onSelect: (file: File) => void;
  maxBytes?: number;
}

const ACCEPTED = ["image/jpeg", "image/png"];

async function hasEnoughDetail(file: File): Promise<boolean> {
  // Cheap blur heuristic: render to a 64x64 canvas and check stddev of luminance.
  // Very low stddev = mostly flat / low-detail / probably blurry.
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const i = new Image();
      i.onload = () => resolve(i);
      i.onerror = reject;
      i.src = url;
    });
    const canvas = document.createElement("canvas");
    canvas.width = 64;
    canvas.height = 64;
    const ctx = canvas.getContext("2d");
    if (!ctx) return true;
    ctx.drawImage(img, 0, 0, 64, 64);
    const { data } = ctx.getImageData(0, 0, 64, 64);
    let sum = 0;
    let sumSq = 0;
    const n = data.length / 4;
    for (let i = 0; i < data.length; i += 4) {
      const lum = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
      sum += lum;
      sumSq += lum * lum;
    }
    const mean = sum / n;
    const variance = sumSq / n - mean * mean;
    return Math.sqrt(variance) > 8;
  } finally {
    URL.revokeObjectURL(url);
  }
}

export default function ImageUploader({ onSelect, maxBytes = 10 * 1024 * 1024 }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      if (!ACCEPTED.includes(file.type)) {
        setError("Only JPEG or PNG images are accepted.");
        return;
      }
      if (file.size > maxBytes) {
        setError(`Image is too large (max ${(maxBytes / 1024 / 1024).toFixed(0)} MB).`);
        return;
      }
      const sharp = await hasEnoughDetail(file);
      if (!sharp) {
        setError("Image looks blurry or low-contrast. Please retake in good lighting.");
        return;
      }
      onSelect(file);
    },
    [maxBytes, onSelect],
  );

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragActive(false);
          const f = e.dataTransfer.files?.[0];
          if (f) handleFile(f);
        }}
        onClick={() => inputRef.current?.click()}
        className={`flex h-56 cursor-pointer items-center justify-center rounded-2xl border-2 border-dashed p-6 text-center transition ${
          dragActive ? "border-blue-500 bg-blue-50" : "border-slate-300 bg-white hover:border-slate-400"
        }`}
      >
        <div>
          <p className="text-base font-medium text-slate-800">Drop a photo here, or click to choose</p>
          <p className="mt-1 text-sm text-slate-500">JPEG or PNG, up to {(maxBytes / 1024 / 1024).toFixed(0)} MB</p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
            e.currentTarget.value = "";
          }}
        />
      </div>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
    </div>
  );
}
