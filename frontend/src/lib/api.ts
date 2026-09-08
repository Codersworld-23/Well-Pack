export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type Verdict = "compliant" | "partial" | "non_compliant" | "needs_review";
export type Severity = "critical" | "major" | "minor" | "info";

export interface Violation {
  field: string;
  clause_id: string;
  rule_number: string;
  title: string;
  severity: Severity;
  message: string;
  observed?: string | null;
  expected?: string | null;
}

export interface Citation {
  clause_id: string;
  rule_number: string;
  title: string;
  excerpt: string;
  score: number;
}

export interface PhysicalAnalysis {
  blur_score?: number;
  is_blurry?: boolean;
  glare_ratio?: number;
  has_glare?: boolean;
  image_width?: number;
  image_height?: number;
  estimated_pdp_area_cm2?: number;
  min_required_height_mm?: number;
  smallest_declaration_height_mm?: number;
  undersized_declarations?: { text: string; height_mm: number; required_mm: number }[];
  min_contrast_ratio?: number;
  low_contrast_declarations?: {
    text: string;
    contrast_ratio: number;
    required_ratio: number;
    text_color?: number[];
    background_color?: number[];
  }[];
  text_regions?: number;
  quality_ok?: boolean;
  quality_message?: string | null;
}

export interface ScanResult {
  id: string;
  created_at: string;
  status: string;
  verdict: Verdict | null;
  compliance_score: number;
  confidence: number;
  hallucination_coefficient: number;
  product_name: string | null;
  extracted_fields: Record<string, unknown>;
  physical_analysis: PhysicalAnalysis;
  violations: Violation[];
  citations: Citation[];
  ocr_text: string | null;
  reasoning: string | null;
  cache_hit: boolean;
  engine: string | null;
  latency_ms: number;
  image_url: string | null;
  source: string;
}

export interface ScanSummary {
  id: string;
  created_at: string;
  product_name: string | null;
  verdict: Verdict | null;
  status: string;
  compliance_score: number;
  source: string;
  cache_hit: boolean;
  latency_ms: number;
  violation_count: number;
  image_url: string | null;
}

export interface RuleClause {
  id: string;
  clause_id: string;
  rule_number: string;
  title: string;
  text: string;
  field: string;
  severity: Severity;
  source: string;
  active: boolean;
  version: number;
  updated_at: string;
}

export interface Report {
  id: string;
  created_at: string;
  scan_id: string | null;
  product_name: string | null;
  reporter_name: string | null;
  reporter_contact: string | null;
  retailer: string | null;
  location: string | null;
  category: string;
  description: string;
  status: string;
  priority: string;
  resolution_note: string | null;
  updated_at: string;
}

export interface Analytics {
  total_scans: number;
  compliant: number;
  non_compliant: number;
  needs_review: number;
  compliance_rate: number;
  avg_latency_ms: number;
  cache_hit_rate: number;
  open_reports: number;
  total_reports: number;
  active_clauses: number;
  top_violations: { clause_id: string; rule_number: string; title: string; count: number }[];
  scans_by_day: { date: string; scans: number; compliant: number; non_compliant: number }[];
  verdict_split: { verdict: string; count: number }[];
  severity_split: { severity: string; count: number }[];
}

export interface SystemStatus {
  vector_store: {
    clauses_indexed: number;
    corpus_version: number;
    embedding_dim: number;
    backend: string;
  };
  semantic_cache: {
    entries: number;
    hits: number;
    misses: number;
    hit_rate: number;
    threshold: number;
    backend: string;
  };
  ocr_engine: string;
  llm: { model: string; configured: boolean; mode: string };
  database: string;
  totals: { scans: number; reports: number; clauses: number };
}

export interface Quality {
  blur_score: number;
  is_blurry: boolean;
  glare_ratio: number;
  has_glare: boolean;
  quality_ok: boolean;
  quality_message: string | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }

  return response.status === 204 ? (undefined as T) : response.json();
}

export const api = {
  scan: (file: File, source = "consumer") => {
    const body = new FormData();
    body.append("file", file);
    body.append("source", source);
    return request<ScanResult>("/api/scans", { method: "POST", body });
  },

  precheck: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<Quality>("/api/scans/precheck", { method: "POST", body });
  },

  getScan: (id: string) => request<ScanResult>(`/api/scans/${id}`),

  listScans: (params: Record<string, string | number> = {}) => {
    const query = new URLSearchParams(
      Object.entries(params).map(([k, v]) => [k, String(v)]),
    );
    return request<ScanSummary[]>(`/api/scans?${query}`);
  },

  rescan: (id: string) => request<ScanResult>(`/api/scans/${id}/rescan`, { method: "POST" }),

  deleteScan: (id: string) => request<void>(`/api/scans/${id}`, { method: "DELETE" }),

  listRules: () => request<RuleClause[]>("/api/rules"),

  createRule: (payload: Partial<RuleClause>) =>
    request<RuleClause>("/api/rules", { method: "POST", body: JSON.stringify(payload) }),

  updateRule: (clauseId: string, payload: Partial<RuleClause>) =>
    request<RuleClause>(`/api/rules/${clauseId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  toggleRule: (clauseId: string) =>
    request<RuleClause>(`/api/rules/${clauseId}/toggle`, { method: "PATCH" }),

  deleteRule: (clauseId: string) =>
    request<void>(`/api/rules/${clauseId}`, { method: "DELETE" }),

  uploadPolicy: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<{
      filename: string;
      clauses_created: number;
      clauses_indexed: number;
      corpus_version: number;
      message: string;
    }>("/api/rules/upload", { method: "POST", body });
  },

  previewRetrieval: (q: string) =>
    request<{ query: string; results: (Citation & { text: string })[] }>(
      `/api/rules/retrieve/preview?q=${encodeURIComponent(q)}`,
    ),

  listReports: (params: Record<string, string> = {}) => {
    const query = new URLSearchParams(params);
    return request<Report[]>(`/api/reports?${query}`);
  },

  createReport: (payload: Record<string, unknown>) =>
    request<Report>("/api/reports", { method: "POST", body: JSON.stringify(payload) }),

  updateReport: (id: string, payload: Record<string, unknown>) =>
    request<Report>(`/api/reports/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),

  analytics: (days = 30) => request<Analytics>(`/api/analytics?days=${days}`),

  systemStatus: () => request<SystemStatus>("/api/analytics/system"),

  login: (email: string, password: string) =>
    request<{ access_token: string; name: string; role: string; email: string }>(
      "/api/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
    ),
};

export const VERDICT_META: Record<
  Verdict,
  { label: string; tone: string; description: string }
> = {
  compliant: {
    label: "Compliant",
    tone: "pass",
    description: "All mandatory declarations satisfy the 2011 Rules.",
  },
  partial: {
    label: "Minor defects",
    tone: "warn",
    description: "Technical defects only — no mandatory declaration is defeated.",
  },
  non_compliant: {
    label: "Non-compliant",
    tone: "fail",
    description: "Contravention of a mandatory declaration requirement.",
  },
  needs_review: {
    label: "Needs review",
    tone: "review",
    description: "Capture quality is too low for a confident verdict.",
  },
};

export function verdictOf(verdict: Verdict | null) {
  return VERDICT_META[verdict ?? "needs_review"];
}

export function fmtDate(iso: string) {
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}
