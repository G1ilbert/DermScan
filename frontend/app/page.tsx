import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-4xl font-bold tracking-tight text-slate-900">DermScan</h1>
      <p className="mt-4 text-lg text-slate-600">
        AI-assisted skin lesion screening, designed for pre-hospital triage. Upload a photo, get a
        risk band and a heatmap showing where the model looked. Always confirm with a dermatologist.
      </p>

      <div className="mt-8 flex flex-wrap gap-3">
        <Link
          href="/scan"
          className="rounded-md bg-blue-600 px-5 py-3 text-sm font-medium text-white shadow hover:bg-blue-700"
        >
          Start a scan
        </Link>
        <Link
          href="/history"
          className="rounded-md border border-slate-300 bg-white px-5 py-3 text-sm font-medium text-slate-800 hover:bg-slate-50"
        >
          My history
        </Link>
        <Link
          href="/login"
          className="rounded-md px-5 py-3 text-sm font-medium text-slate-600 hover:bg-slate-100"
        >
          Log in
        </Link>
      </div>

      <section className="mt-14 grid gap-6 sm:grid-cols-3">
        <div className="rounded-xl border bg-white p-5">
          <h3 className="font-semibold text-slate-900">Confidence-gated</h3>
          <p className="mt-2 text-sm text-slate-600">
            Low-confidence outputs are returned as &ldquo;uncertain&rdquo; or &ldquo;low quality&rdquo; — never
            as a diagnosis.
          </p>
        </div>
        <div className="rounded-xl border bg-white p-5">
          <h3 className="font-semibold text-slate-900">Encrypted at rest</h3>
          <p className="mt-2 text-sm text-slate-600">PII is encrypted with AES-class field-level encryption.</p>
        </div>
        <div className="rounded-xl border bg-white p-5">
          <h3 className="font-semibold text-slate-900">FHIR + PDF</h3>
          <p className="mt-2 text-sm text-slate-600">
            Export results as a PDF for the patient or a FHIR DiagnosticReport for clinicians.
          </p>
        </div>
      </section>
    </main>
  );
}
