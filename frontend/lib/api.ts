import { Session, SupabaseClient, createClient } from "@supabase/supabase-js";

// Trim any trailing slash so callers can append paths like `/scan` without
// producing `//scan` — which is a different URL to FastAPI and was producing
// 400-status CORS preflights in audit_logs against the live deploy.
const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

// Singleton Supabase JS client. Browser-only — the App Router runs lib code
// during SSR for "use client" components, so we lazily construct on first
// use and skip on the server.
let _supabase: SupabaseClient | null = null;
let _cachedToken: string | null = null;

function supabase(): SupabaseClient {
  if (typeof window === "undefined") {
    throw new Error("Supabase client used outside the browser");
  }
  if (_supabase) return _supabase;
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    throw new Error(
      "Supabase env not set: NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are required",
    );
  }
  _supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  });
  // Keep a sync-readable cache of the access token so call-sites that can't
  // await (e.g. layout-time guards) stay simple. onAuthStateChange fires
  // immediately on subscribe with the current session.
  _supabase.auth.onAuthStateChange((_event, session: Session | null) => {
    _cachedToken = session?.access_token ?? null;
  });
  return _supabase;
}

export interface Envelope<T> {
  success: boolean;
  data: T | null;
  error: string | null;
}

export interface ScanCreated {
  job_id: string;
  scan_id: string;
  status: string;
}

export interface ScanResult {
  job_id: string;
  scan_id: string;
  status: "pending" | "processing" | "done" | "failed";
  confidence: number | null;
  prediction: { label?: string; band?: string; probabilities?: number[]; label_index?: number } | null;
  image_url: string | null;
  heatmap_url: string | null;
  confidence_band: "result" | "uncertain" | "low_quality" | null;
  error_message: string | null;
  created_at: string | null;
}

export interface ScanHistoryItem {
  scan_id: string;
  job_id: string;
  status: string;
  confidence: number | null;
  confidence_band: string | null;
  created_at: string;
}

export interface ScanHistoryPage {
  items: ScanHistoryItem[];
  page: number;
  page_size: number;
  total: number;
}

export interface AuthResult {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user_id: string;
  email: string | null;
}

/**
 * Returns the current Supabase access token synchronously, or null if no
 * session is active. Updated by the onAuthStateChange subscription above.
 */
export function getAccessToken(): string | null {
  return _cachedToken;
}

/**
 * Kept for backwards-compatibility with existing call-sites. Supabase JS
 * owns session storage, so we deliberately ignore the argument — callers
 * no longer need to manually persist tokens.
 */
export function setAccessToken(_token: string | null): void {
  // no-op: Supabase JS manages persistence in localStorage
}

async function authHeader(): Promise<Record<string, string>> {
  if (typeof window === "undefined") return {};
  const { data } = await supabase().auth.getSession();
  const token = data.session?.access_token ?? _cachedToken;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  for (const [k, v] of Object.entries(await authHeader())) headers.set(k, v);
  if (!(init.body instanceof FormData) && init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });

  const text = await res.text();
  let parsed: unknown = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = null;
  }

  if (!res.ok) {
    const detail =
      parsed && typeof parsed === "object" && "detail" in parsed
        ? String((parsed as { detail: unknown }).detail)
        : `HTTP ${res.status}`;
    throw new Error(detail);
  }

  return parsed as T;
}

function sessionToEnvelope(session: Session | null): Envelope<AuthResult> {
  if (!session) {
    return { success: false, data: null, error: "No session" };
  }
  return {
    success: true,
    data: {
      access_token: session.access_token,
      refresh_token: session.refresh_token,
      token_type: "bearer",
      user_id: session.user.id,
      email: session.user.email ?? null,
    },
    error: null,
  };
}

export const api = {
  async register(email: string, password: string) {
    const { data, error } = await supabase().auth.signUp({ email, password });
    if (error) throw new Error(error.message);
    _cachedToken = data.session?.access_token ?? null;
    return sessionToEnvelope(data.session);
  },

  async login(email: string, password: string) {
    const { data, error } = await supabase().auth.signInWithPassword({ email, password });
    if (error) throw new Error(error.message);
    _cachedToken = data.session?.access_token ?? null;
    return sessionToEnvelope(data.session);
  },

  async logout() {
    const { error } = await supabase().auth.signOut();
    if (error) throw new Error(error.message);
    _cachedToken = null;
    return { success: true, data: { logged_out: true }, error: null } as Envelope<{ logged_out: boolean }>;
  },

  submitScan(file: File) {
    const fd = new FormData();
    fd.append("file", file);
    return request<Envelope<ScanCreated>>("/scan", { method: "POST", body: fd });
  },

  getScanResult(jobId: string) {
    return request<Envelope<ScanResult>>(`/scan/result/${encodeURIComponent(jobId)}`);
  },

  getHistory(page = 1, pageSize = 20) {
    return request<Envelope<ScanHistoryPage>>(`/scan/history?page=${page}&page_size=${pageSize}`);
  },

  reportUrl(scanId: string) {
    return `${API_BASE_URL}/scan/report/${encodeURIComponent(scanId)}`;
  },

  fhirUrl(scanId: string) {
    return `${API_BASE_URL}/scan/fhir/${encodeURIComponent(scanId)}`;
  },
};

export const POLL_INTERVAL_MS = Number(process.env.NEXT_PUBLIC_POLL_INTERVAL_MS ?? 2000);
