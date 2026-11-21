// Client for the Lode API (src/lode/api/app.py). Types mirror its response models.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Size = "micro" | "small" | "other" | "not_informed";

export type Meta = {
  receita_month: string;
  contracts_from: string;
  contracts_to: string;
  scored_at: string;
  score_cutoff: string;
  companies: number;
  model: string;
  model_version: string;
  holdout: {
    pr_auc: number;
    pr_auc_interval: [number, number];
    precision_at_100: number;
    lift_at_10pct: number;
    base_rate: number;
  };
};

export type Company = {
  rank: number;
  score: number;
  cnpj_basico: string;
  legal_name: string;
  trade_name: string | null;
  municipality_code: string;
  municipality: string | null;
  size: Size;
};

export type CompanyPage = { total: number; limit: number; offset: number; items: Company[] };

export type CompanyDetail = Company & {
  opened_on: string | null;
  capital: number;
  legal_nature: string;
  simples: boolean;
  partners: number;
  establishments: number;
  main_activity: string;
  main_activity_name: string | null;
  secondary_activities: number;
  public_contracts: { count: number; total_value: number | null; last_published: string | null };
  reasons: { feature: string; contribution: number }[] | null;
  website: {
    url: string | null;
    domain: string;
    verified: boolean;
    what_it_does: string | null;
    public_sector_evidence: string | null;
  } | null;
};

export type Municipality = {
  municipality_code: string;
  ibge_code: string | null;
  municipality: string | null;
  companies: number;
  mean_score: number;
  expected_winners: number;
  best_cnpj_basico: string;
  best_legal_name: string;
  best_score: number;
};

export type CompanyFilters = {
  municipality?: string;
  size?: Size;
  q?: string;
  limit?: number;
  offset?: number;
};

async function get<T>(path: string, params: Record<string, string | number | undefined> = {}) {
  const url = new URL(path, API_URL);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
  }
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${url.pathname}`);
  return (await response.json()) as T;
}

export const api = {
  meta: () => get<Meta>("/meta"),
  municipalities: () => get<Municipality[]>("/municipalities"),
  companies: (filters: CompanyFilters) => get<CompanyPage>("/companies", filters),
  company: (cnpj: string) => get<CompanyDetail>(`/companies/${cnpj}`),
};
