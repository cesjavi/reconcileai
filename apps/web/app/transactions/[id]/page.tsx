"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Candidate, EvolusExec, Inference, RULES, Tx, money, useApi } from "@/lib/api";
import { Banner, Card, Empty, ErrorBox, Loading, PageHeader, StatusBadge } from "../../_components/ui";

type Detail = { bank: Tx; candidates: Candidate[]; decisions: { candidate_id: number; action: string; actor: string; note: string | null; created_at: string }[]; inference: Inference[] };
type Insights = { recommendations: { id: number; recommendation: string; rationale: string; source: string }[]; evolus_executions: EvolusExec[] };

function Fields({ title, t }: { title: string; t: Tx }) {
  return (
    <div className="rounded-lg bg-slate-50 p-3 text-sm">
      <div className="mb-1 text-xs font-semibold uppercase text-slate-500">{title}</div>
      <dl className="grid grid-cols-[7rem_1fr] gap-y-0.5">
        <dt className="text-slate-500">ID</dt><dd>{t.external_id}</dd>
        <dt className="text-slate-500">Fecha</dt><dd>{t.date}</dd>
        <dt className="text-slate-500">Importe</dt><dd className="font-semibold tabular-nums">{money(t.amount)}</dd>
        <dt className="text-slate-500">CUIT/DNI</dt><dd>{t.document || "—"}</dd>
        <dt className="text-slate-500">Comprobante</dt><dd>{t.voucher || "—"}</dd>
        <dt className="text-slate-500">Texto</dt><dd>{t.description || "—"}</dd>
      </dl>
    </div>
  );
}

function CandidateCard({ c, decisions }: { c: Candidate; decisions: Detail["decisions"] }) {
  const ins = useApi<Insights>(`/candidates/${c.id}/insights`);
  return (
    <Card title={`Candidato #${c.id} · ${c.rule}`} action={<StatusBadge status={c.status} />}>
      <p className="mb-3 text-sm text-slate-700"><b>Regla {c.rule}:</b> {RULES[c.rule]}</p>
      <div className="grid gap-3 md:grid-cols-2"><Fields title="Banco" t={c.bank} /><Fields title="Depósito del sistema" t={c.deposit} /></div>
      <div className="mt-3 text-sm">
        <span className="font-medium">Evidencia del motor:</span>{" "}
        <code className="rounded bg-slate-100 px-1 text-xs">{JSON.stringify(c.evidence)}</code>
      </div>
      {c.status === "AMBIGUOUS" && <div className="mt-3"><Banner tone="warn">Ambiguo: hay más de una combinación posible con la misma evidencia. Solo una persona puede resolverlo.</Banner></div>}
      {decisions.filter((d) => d.candidate_id === c.id).map((d, i) => (
        <p key={i} className="mt-2 text-sm text-slate-700">Decisión <b>{d.action}</b> por {d.actor}{d.note ? ` — “${d.note}”` : ""}</p>
      ))}
      {ins.data && (ins.data.recommendations.length > 0 || ins.data.evolus_executions.length > 0) && (
        <div className="mt-3 rounded-lg border border-slate-200 p-3 text-sm">
          <div className="mb-1 text-xs font-semibold uppercase text-slate-500">Evolus · informativo, no decide</div>
          {ins.data.evolus_executions.map((e) => (
            <p key={e.id}>{e.simulated && <span className="mr-1 rounded bg-amber-100 px-1 text-xs font-bold text-amber-900">SIMULADO</span>}
              Ejecución {e.remote_execution_id ?? "—"} · {e.status}{e.error ? ` · ${e.error}` : ""}{e.advisory_text ? ` — ${e.advisory_text}` : ""}</p>
          ))}
          {ins.data.recommendations.map((r) => <p key={r.id}>Agente ({r.source}): <b>{r.recommendation}</b> {r.rationale && `— ${r.rationale}`}</p>)}
        </div>
      )}
    </Card>
  );
}

export default function TransactionDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, error, loading, reload } = useApi<Detail>(`/bank-transactions/${id}`);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  const d = data!;

  return (
    <>
      <PageHeader title={`Movimiento ${d.bank.external_id}`} subtitle="Evidencia, candidatos evaluados por las reglas y lo que extrajo la IA del texto original.">
        <StatusBadge status={d.bank.status} />
      </PageHeader>
      <div className="space-y-4">
        <Card title="Movimiento bancario"><Fields title="Banco" t={d.bank} /></Card>
        {d.candidates.length === 0
          ? <Empty title="Sin candidatos" hint="Ninguna regla determinista produjo un candidato con importe exacto y evidencia suficiente. Queda para conciliación manual." />
          : d.candidates.map((c) => <CandidateCard key={c.id} c={c} decisions={d.decisions} />)}

        <Card title="Interpretación por IA (texto original conservado como evidencia)">
          {d.inference.length === 0 ? <p className="text-sm text-slate-600">No se consultó a la IA para este movimiento (lo resolvieron las reglas R1–R3 o no había candidatos que verificar).</p> :
            d.inference.map((i) => (
              <div key={i.request_id} className="mb-3 rounded-lg border border-slate-200 p-3 text-sm last:mb-0">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  {i.is_mock
                    ? <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-bold text-amber-900">MOCK — no es inferencia AMD</span>
                    : <span className="rounded bg-teal-100 px-2 py-0.5 text-xs font-bold text-teal-900">vLLM · {i.model}</span>}
                  <span className="text-xs text-slate-500">{i.status} · {i.latency_ms.toFixed(0)} ms · {i.attempts} intento(s) · id {i.request_id.slice(0, 8)}</span>
                  <span className={`text-xs font-semibold ${i.accepted ? "text-emerald-700" : "text-slate-500"}`}>{i.accepted ? "El motor aceptó una referencia verificada" : "El motor no aceptó ninguna propuesta"}</span>
                </div>
                <blockquote className="border-l-4 border-slate-300 pl-3 italic">{i.original_text}</blockquote>
                <ul className="mt-2 grid gap-x-6 sm:grid-cols-2">
                  {(["documents", "vouchers", "references", "names"] as const).map((k) => (
                    <li key={k}><span className="text-slate-500">{k}:</span> {i.extraction[k].length ? i.extraction[k].map((x) => x.value).join(", ") : "—"}</li>
                  ))}
                </ul>
                {i.dropped.length > 0 && <p className="mt-2 text-xs text-amber-800">Descartado por validación: {i.dropped.join(" · ")}</p>}
                {i.error && <p className="mt-2 text-xs text-rose-800">Error: {i.error}</p>}
              </div>
            ))}
        </Card>
        <Link href="/transactions" className="text-sm font-medium text-teal-800 underline">← Volver a movimientos</Link>
      </div>
    </>
  );
}
