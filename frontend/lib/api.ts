const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

const ACCESS_TOKEN_KEY = "dermscan_access_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setAccessToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) {
    window.localStorage.setItem(ACCESS_TOKEN_KEY, token);
  } else {
    window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (!(init.body instanceof FormData) && init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });

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

export const api = {
  register(email: string, password: string) {
    return request<Envelope<{ id: string; email: string }>>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },
  login(email: string, password: string) {
    return request<Envelope<TokenPair>>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },
  refresh() {
    return request<Envelope<TokenPair>>("/auth/refresh", { method: "POST" });
  },
  logout() {
    setAccessToken(null);
    return request<Envelope<unknown>>("/auth/logout", { method: "POST" });
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
