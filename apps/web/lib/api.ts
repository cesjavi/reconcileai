"use client";

import { useCallback, useEffect, useState } from "react";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : (detail as { message?: string })?.message ?? `HTTP ${status}`);
  }
}

export function getActor(): string {
  try { return localStorage.getItem("reconcileai.actor") ?? ""; } catch { return ""; }
}
export function setActor(v: string) {
  try { localStorage.setItem("reconcileai.actor", v); } catch { /* storage unavailable */ }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "X-Actor": getActor() };
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, { ...init, headers: { ...headers, ...(init.headers as object) } });
  } catch {
    throw new ApiError(0, `No se pudo conectar con la API (${API}). ¿Está en ejecución?`);
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, body?.detail ?? res.statusText);
  return body as T;
}

export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const reload = useCallback(async () => {
    if (path === null) return;
    setLoading(true);
    try { setData(await api<T>(path)); setError(null); }
    catch (e) { setError(e as ApiError); }
    finally { setLoading(false); }
  }, [path]);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, loading, reload };
}

export type Status = "MATCHED" | "SUGGESTED" | "AMBIGUOUS" | "UNMATCHED" | "REJECTED";
export const STATUSES: Status[] = ["MATCHED", "SUGGESTED", "AMBIGUOUS", "UNMATCHED", "REJECTED"];

export type Tx = { id: number; external_id: string; date: string; amount: string; description: string; document: string; voucher: string; status: Status };
export type Candidate = { id: number; rule: string; status: Status; evidence: Record<string, unknown>; run_id: number; bank: Tx; deposit: Tx };
export type Summary = { bank: Record<Status, number>; deposits: Record<Status, number>; bank_total: number; deposits_total: number; match_rate: number; review_queue: number };
export type Batch = { id: number; kind: string; filename: string | null; stats: Record<string, number>; created_by: string; created_at: string };
export type Inference = { request_id: string; source: "mock" | "vllm"; is_mock: boolean; model: string; hardware_label: string; status: string; error: string | null; latency_ms: number; attempts: number; original_text: string; extraction: { documents: { value: string; evidence: string; kind: string }[]; vouchers: { value: string; evidence: string }[]; references: { value: string; evidence: string }[]; names: { value: string; evidence: string }[] }; dropped: string[]; accepted: boolean; created_at: string; bank_id: number | null };
export type InfHealth = { status: string; source: string; is_mock: boolean; model: string; model_listed: boolean | null; latency_ms: number | null; hardware_label: string; detail: string };
export type InfMetrics = { has_real_inference: boolean; mock_calls: number; real_calls: number; real_ok: number; real_invalid_output: number; real_errors: number; real_retried: number; real_latency_ms: { avg: number | null; p50: number | null; p95: number | null; samples: number }; accepted_by_engine: number; items_dropped_by_validation: number; models: string[] };
export type AuditRow = { seq: number; ts: string; actor: string; action: string; entity: string; entity_id: number | null; payload: Record<string, unknown>; hash: string };
export type EvolusStatus = { mode: string; enabled: boolean; simulated: boolean; configured: Record<string, boolean>; agent_api_enabled: boolean };
export type EvolusExec = { id: number; mode: string; simulated: boolean; remote_execution_id: string | null; trace_id: string | null; status: string; error: string | null; advisory_text: string | null };

export const RULES: Record<string, string> = {
  R1: "Mismo comprobante e importe exacto",
  R2: "Mismo CUIT/DNI, importe exacto y fecha dentro de la ventana",
  R3: "Importe único dentro de la ventana de fechas",
  R4: "Referencia propuesta por IA y verificada de forma determinista",
};

export const money = (s: string) => Number(s).toLocaleString("es-AR", { style: "currency", currency: "ARS" });
