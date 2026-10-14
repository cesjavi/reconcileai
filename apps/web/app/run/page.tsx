"use client";

import Link from "next/link";
import { useState } from "react";
import { Batch, api, getActor, useApi } from "@/lib/api";
import { Banner, Btn, Card, Empty, ErrorBox, Loading, PageHeader } from "../_components/ui";

type RunResult = { run_id: number; proposed: number; MATCHED: number; SUGGESTED: number; AMBIGUOUS: number; banks_considered: number; deposits_considered: number; inference_calls: number };

export default function RunPage() {
  const batches = useApi<Batch[]>("/batches");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true); setError(null);
    try { setResult(await api<RunResult>("/reconcile/run", { method: "POST" })); await batches.reload(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  const imports = batches.data?.filter((b) => b.kind !== "RUN") ?? [];
  const runs = batches.data?.filter((b) => b.kind === "RUN") ?? [];

  return (
    <>
      <PageHeader title="Ejecutar conciliación" subtitle="Aplica las reglas en orden: R1 comprobante+importe, R2 documento+importe+ventana, R3 importe único en ventana, R4 referencias de IA verificadas. Solo R1 se aprueba sola; el resto queda para revisión humana." />
      {!getActor() && <div className="mb-4"><Banner tone="warn">Indica tu nombre de revisor arriba a la derecha: toda ejecución queda registrada a tu nombre.</Banner></div>}
      <Card title="Ejecución" action={<Btn onClick={run} disabled={busy || imports.length === 0}>{busy ? "Conciliando…" : "Ejecutar conciliación"}</Btn>}>
        <p className="text-sm text-slate-600">Una ejecución procesa todos los movimientos y depósitos que aún no tienen un vínculo efectivo. Repetirla es seguro (idempotente): no duplica candidatos ni toca decisiones humanas.</p>
        {imports.length === 0 && !batches.loading && <p className="mt-3 text-sm text-amber-800">No hay lotes importados. <Link className="underline" href="/import">Importa datos primero</Link>.</p>}
        <div aria-live="polite" className="mt-4">
          {error && <ErrorBox error={error} />}
          {result && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-950" data-testid="run-result">
              <p className="font-semibold">Ejecución #{result.run_id} completada</p>
              <ul className="mt-1 grid grid-cols-2 gap-x-6 sm:grid-cols-3">
                <li>Propuestas: <b>{result.proposed}</b></li><li>Vinculadas (R1): <b>{result.MATCHED}</b></li><li>Sugeridas: <b>{result.SUGGESTED}</b></li>
                <li>Ambiguas: <b>{result.AMBIGUOUS}</b></li><li>Movimientos evaluados: <b>{result.banks_considered}</b></li><li>Llamadas de inferencia: <b>{result.inference_calls}</b></li>
              </ul>
              <Link href="/review" className="mt-2 inline-block font-medium text-teal-800 underline">Ir a la cola de revisión</Link>
            </div>
          )}
        </div>
      </Card>
      <div className="mt-6">
        <Card title="Historial de ejecuciones">
          {batches.loading && !batches.data ? <Loading /> : batches.error ? <ErrorBox error={batches.error} onRetry={batches.reload} /> :
            runs.length === 0 ? <Empty title="Todavía no se ejecutó ninguna conciliación" /> : (
              <ul className="divide-y text-sm">
                {runs.map((r) => (
                  <li key={r.id} className="flex flex-wrap justify-between gap-2 py-2">
                    <span>Ejecución #{r.id} · {r.created_by}</span>
                    <span className="text-slate-600">{r.stats.proposed ?? 0} propuestas · {r.stats.MATCHED ?? 0} auto · {r.stats.AMBIGUOUS ?? 0} ambiguas</span>
                  </li>
                ))}
              </ul>
            )}
        </Card>
      </div>
    </>
  );
}
