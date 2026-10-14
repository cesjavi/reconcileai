"use client";

import { ReactNode } from "react";
import { ApiError, Status } from "@/lib/api";

const STATUS_STYLE: Record<Status, string> = {
  MATCHED: "bg-emerald-100 text-emerald-900 ring-emerald-600/30",
  SUGGESTED: "bg-sky-100 text-sky-900 ring-sky-600/30",
  AMBIGUOUS: "bg-amber-100 text-amber-900 ring-amber-600/40",
  UNMATCHED: "bg-slate-100 text-slate-800 ring-slate-500/30",
  REJECTED: "bg-rose-100 text-rose-900 ring-rose-600/30",
};
const STATUS_ICON: Record<Status, string> = { MATCHED: "✓", SUGGESTED: "◔", AMBIGUOUS: "?", UNMATCHED: "—", REJECTED: "✕" };

export function StatusBadge({ status }: { status: Status }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${STATUS_STYLE[status]}`}>
      <span aria-hidden="true">{STATUS_ICON[status]}</span>{status}
    </span>
  );
}

export function Card({ title, children, action }: { title?: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      {(title || action) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-base font-semibold text-slate-900">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-slate-600">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

export function Loading({ label = "Cargando…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-2 p-6 text-sm text-slate-600">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-teal-600" aria-hidden="true" />
      {label}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: ApiError | Error | string; onRetry?: () => void }) {
  const msg = typeof error === "string" ? error : error.message;
  return (
    <div role="alert" className="flex items-start justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
      <span>{msg}</span>
      {onRetry && <button onClick={onRetry} className="shrink-0 rounded border border-rose-300 bg-white px-2 py-1 font-medium hover:bg-rose-100">Reintentar</button>}
    </div>
  );
}

export function Empty({ title, hint, children }: { title: string; hint?: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center">
      <p className="font-medium text-slate-800">{title}</p>
      {hint && <p className="mt-1 text-sm text-slate-600">{hint}</p>}
      {children && <div className="mt-3">{children}</div>}
    </div>
  );
}

export function Btn({ variant = "primary", ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" | "success" }) {
  const v = {
    primary: "bg-teal-700 text-white hover:bg-teal-800",
    ghost: "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50",
    danger: "bg-rose-700 text-white hover:bg-rose-800",
    success: "bg-emerald-700 text-white hover:bg-emerald-800",
  }[variant];
  return <button {...p} className={`rounded-lg px-3 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600 disabled:cursor-not-allowed disabled:opacity-50 ${v} ${p.className ?? ""}`} />;
}

export function Banner({ tone, children }: { tone: "warn" | "ok" | "info"; children: ReactNode }) {
  const t = { warn: "border-amber-300 bg-amber-50 text-amber-950", ok: "border-emerald-300 bg-emerald-50 text-emerald-950", info: "border-sky-300 bg-sky-50 text-sky-950" }[tone];
  return <div role="note" className={`rounded-lg border p-3 text-sm ${t}`}>{children}</div>;
}
