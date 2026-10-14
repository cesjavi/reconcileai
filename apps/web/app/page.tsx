"use client";

import Link from "next/link";
import { InfMetrics, STATUSES, Summary, useApi } from "@/lib/api";
import { Banner, Card, Empty, ErrorBox, Loading, PageHeader, StatusBadge } from "./_components/ui";

const BAR: Record<string, string> = { MATCHED: "bg-emerald-600", SUGGESTED: "bg-sky-600", AMBIGUOUS: "bg-amber-500", UNMATCHED: "bg-slate-400", REJECTED: "bg-rose-600" };

export default function Dashboard() {
  const sum = useApi<Summary>("/summary");
  const inf = useApi<InfMetrics>("/inference/metrics");
  const chain = useApi<{ valid: boolean; checked: number }>("/audit/verify");

  if (sum.loading && !sum.data) return <Loading />;
  if (sum.error) return <ErrorBox error={sum.error} onRetry={sum.reload} />;
  const s = sum.data!;

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Estado de la conciliación. Los porcentajes se calculan sobre los movimientos bancarios importados." />
      {s.bank_total === 0 ? (
        <Empty title="Aún no hay datos" hint="Importa un CSV bancario y uno de depósitos del sistema, o carga el dataset sintético de demo.">
          <Link href="/import" className="rounded-lg bg-teal-700 px-3 py-2 text-sm font-medium text-white hover:bg-teal-800">Ir a importar</Link>
        </Empty>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Kpi label="Tasa conciliada" value={`${(s.match_rate * 100).toFixed(1)}%`} hint="MATCHED / movimientos bancarios" testId="kpi-rate" />
            <Kpi label="En cola de revisión" value={String(s.review_queue)} hint="candidatos pendientes de decisión humana" testId="kpi-queue" />
            <Kpi label="Movimientos bancarios" value={String(s.bank_total)} testId="kpi-bank" />
            <Kpi label="Depósitos del sistema" value={String(s.deposits_total)} testId="kpi-deposits" />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {([["Movimientos bancarios", s.bank, s.bank_total], ["Depósitos del sistema", s.deposits, s.deposits_total]] as const).map(([title, counts, total]) => (
              <Card key={title} title={title}>
                <div className="flex h-3 overflow-hidden rounded-full bg-slate-100" role="img"
                  aria-label={STATUSES.map((k) => `${k}: ${counts[k]}`).join(", ")}>
                  {STATUSES.map((k) => counts[k] > 0 && <div key={k} className={BAR[k]} style={{ width: `${(counts[k] / total) * 100}%` }} />)}
                </div>
                <ul className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
                  {STATUSES.map((k) => (
                    <li key={k} className="flex items-center justify-between gap-2">
                      <StatusBadge status={k} /><span className="font-semibold tabular-nums" data-testid={`count-${title.startsWith("Mov") ? "bank" : "dep"}-${k}`}>{counts[k]}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Inferencia">
              {inf.data ? (
                inf.data.has_real_inference
                  ? <p className="text-sm">{inf.data.real_calls} llamadas reales registradas · latencia media {inf.data.real_latency_ms.avg ?? "—"} ms. <Link href="/inference" className="font-medium text-teal-700 underline">Ver monitor</Link></p>
                  : <Banner tone="warn">Sin inferencia real registrada{inf.data.mock_calls > 0 ? ` (${inf.data.mock_calls} llamadas fueron MOCK)` : ""}. <Link href="/inference" className="font-medium underline">Ver monitor</Link></Banner>
              ) : <Loading />}
            </Card>
            <Card title="Auditoría">
              {chain.data ? (chain.data.valid
                ? <Banner tone="ok">Cadena de auditoría íntegra · {chain.data.checked} eventos verificados.</Banner>
                : <Banner tone="warn">La cadena de auditoría está rota. Revisa la pantalla de auditoría.</Banner>) : <Loading />}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}

function Kpi({ label, value, hint, testId }: { label: string; value: string; hint?: string; testId: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-3xl font-bold tabular-nums text-slate-900" data-testid={testId}>{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}
