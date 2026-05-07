"use client";

interface Props {
  open: boolean;
  onAccept: () => void;
  onCancel: () => void;
}

export default function ConsentModal({ open, onAccept, onCancel }: Props) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        <h2 className="text-lg font-bold text-slate-900">Before you continue</h2>
        <p className="mt-3 text-sm leading-6 text-slate-700">
          DermScan provides AI-assisted screening only. It is <strong>not</strong> a diagnosis.
          Always consult a licensed dermatologist for any concerning skin lesion. Your image will be
          uploaded to encrypted storage and processed by an AI model for the sole purpose of giving
          you a screening result.
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <button onClick={onCancel} className="rounded-md px-4 py-2 text-sm text-slate-600 hover:bg-slate-100">
            Cancel
          </button>
          <button onClick={onAccept} className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
            I understand, continue
          </button>
        </div>
      </div>
    </div>
  );
}
