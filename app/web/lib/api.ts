// app/web/lib/api.ts
// Phase 9 typed local-only API client.
//
// Local-only by design — Project Atlas binds the FastAPI service to
// http://127.0.0.1:8000 (`make demo-api`). There is intentionally NO
// non-local fallback, NO env-based override, and NO production base
// URL. Phase 9 invariant (a)(1).
//
// Server-side only — every fetcher runs from a Next.js server
// component (`app/web/app/page.tsx`). The browser never talks directly
// to the FastAPI service. The orchestrators in `replay.ts` call these
// fetchers and surface a structured ``ReplayLoadResult`` the page
// renders directly (no fixture fallback).

import type {
  ReplayPayload,
  RoundDetail,
  RunDetail,
  RunSummary,
} from "./replay";
import type { JudgeReport, ModelVulnerabilityCard } from "./types";

export const ATLAS_API_BASE_URL = "http://127.0.0.1:8000";

export class AtlasApiError extends Error {
  readonly status: number;
  readonly remediation: string | null;

  constructor(message: string, status: number, remediation: string | null) {
    super(message);
    this.name = "AtlasApiError";
    this.status = status;
    this.remediation = remediation;
  }
}

// Typed thin wrapper around `fetch`. Throws `AtlasApiError` on non-2xx.
// Component 6 calls this from server components only.
export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${ATLAS_API_BASE_URL}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail: string | null = null;
    try {
      const body = (await res.json()) as { detail?: string };
      detail = typeof body.detail === "string" ? body.detail : null;
    } catch {
      detail = null;
    }
    throw new AtlasApiError(
      `ATLAS API ${path} failed (${res.status})`,
      res.status,
      detail,
    );
  }
  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// Placeholder fetcher signatures (bodies in component 6)
// ---------------------------------------------------------------------------

export async function getRuns(): Promise<{ runs: RunSummary[] }> {
  return apiFetch<{ runs: RunSummary[] }>("/runs");
}

export interface DemoCaseSearchReport {
  selected?: { run_id?: unknown } | null;
  available?: boolean;
  [key: string]: unknown;
}

export async function getDemoCaseSearchReport(): Promise<DemoCaseSearchReport> {
  return apiFetch<DemoCaseSearchReport>("/demo-case-search-report");
}

export async function getRun(run_id: string): Promise<RunDetail> {
  return apiFetch<RunDetail>(`/runs/${encodeURIComponent(run_id)}`);
}

export async function getRunRoundDetail(
  run_id: string,
  round_id: number,
): Promise<RoundDetail> {
  return apiFetch<RoundDetail>(
    `/runs/${encodeURIComponent(run_id)}/rounds/${round_id}`,
  );
}

export async function getReplay(run_id: string): Promise<ReplayPayload> {
  return apiFetch<ReplayPayload>(`/replay/${encodeURIComponent(run_id)}`);
}

export async function getRunModelVulnerabilities(
  run_id: string,
): Promise<{ model_vulnerabilities: ModelVulnerabilityCard[] }> {
  return apiFetch<{ model_vulnerabilities: ModelVulnerabilityCard[] }>(
    `/runs/${encodeURIComponent(run_id)}/model-vulnerabilities`,
  );
}

export async function getJudgeReport(
  run_id: string,
  judge_report_id: string,
): Promise<JudgeReport> {
  return apiFetch<JudgeReport>(
    `/runs/${encodeURIComponent(run_id)}/judge-reports/${encodeURIComponent(
      judge_report_id,
    )}`,
  );
}
