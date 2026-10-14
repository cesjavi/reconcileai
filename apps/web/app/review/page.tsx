"use client";

import Link from "next/link";
import { useState } from "react";
import { Candidate, EvolusStatus, RULES, api, getActor, money, useApi } from "@/lib/api";
import { Banner, Btn, Card, Empty, ErrorBox, Loading, PageHeader, StatusBadge } from "../_components/ui";

function Case({ c, evolus, onDone }: { c: Candidate; evolus: EvolusStatus | null; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const ambiguous = c.status === "AMBIGUOUS";

  const decide = async (kind: "approve" | "reject") => {
    setBusy(true); setError(null);
    try { await api(`/candidates/${c.id}/${kind}`, { method: "POST", body: JSON.stringify({ note: note.trim() || null }) }); onDone(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const evo = async () => {
    setBusy(true); setError(null);
    try {
      const r = await api<{ status: string; simulated: boolean; remote_execution_id: string | null }>(`/candidates/${c.id}/evolus-review`, { method: "POST" });
      setInfo(`${r.simulated ? "SIMULADO · " : ""}Evolus: ejecución ${r.remote_execution_id} (${r.status})`);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <li data-testid="review-case" data-status={c.status}>
      <Card title={`Candidato #${c.id} · ${c.rule}`} action={<StatusBadge status={c.status} />}>
        <p className="mb-3 text-sm text-slate-700">{RULES[c.rule]}</p>
        <div className="grid gap-3 text-sm md:grid-cols-2">
          {([["Banco", c.bank], ["Depósito", c.deposit]] as const).map(([t, x]) => (
            <div key={t} className="rounded-lg bg-slate-50 p-3">
              <div className="text-xs font-semibold uppercase text-slate-500">{t} · {x.external_id}</div>
              <div className="mt-1 text-lg font-semibold tabular-nums">{money(x.amount)}</div>
              <div>{x.date} · {x.voucher || "sin comprobante"} · {x.document || "sin CUIT/DNI"}</div>
              {x.description && <div className="text-slate-600">{x.description}</div>}
            </div>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-500">Evidencia: <code>{JSON.stringify(c.evidence)}</code> · <Link className="underline" href={`/transactions/${c.bank.id}`}>ver detalle</Link></p>
        {ambiguous && <div className="mt-3"><Banner tone="warn">Caso ambiguo: la nota es obligatoria para aprobarlo y debe justificar por qué esta combinación y no la otra.</Banner></div>}
        <div className="mt-3">
          <label htmlFor={`note-${c.id}`} className="text-sm font-medium">Nota {ambiguous ? "(obligatoria para aprobar)" : "(opcional)"}</label>
          <textarea id={`note-${c.id}`} value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={500} className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm" />
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <Btn variant="success" disabled={busy || (ambiguous && !note.trim())} onClick={() => decide("approve")}>Aprobar</Btn>
          <Btn variant="danger" disabled={busy} onClick={() => decide("reject")}>Rechazar</Btn>
          {evolus?.enabled && <Btn variant="ghost" disabled={busy} onClick={evo}>Pedir análisis a Evolus{evolus.simulated ? " (simulado)" : ""}</Btn>}
        </div>
        <div aria-live="polite" className="mt-2 space-y-2">{info && <Banner tone="info">{info}</Banner>}{error && <ErrorBox error={error} />}</div>
      </Card>
    </li>
  );
}

export default function Review() {
  const pending = useApi<Candidate[]>("/candidates?limit=500");
  const evo = useApi<EvolusStatus>("/evolus/status");
  const queue = (pending.data ?? []).filter((c) => c.status === "SUGGESTED" || c.status === "AMBIGUOUS")
    .sort((a, b) => Number(b.status === "AMBIGUOUS") - Number(a.status === "AMBIGUOUS") || a.id - b.id);

  return (
    <>
      <PageHeader title="Cola de revisión humana" subtitle="Nada que no sea una coincidencia exacta de comprobante se aplica sin tu decisión. Al aprobar, el motor vuelve a validar importe, fechas y evidencia." />
      {!getActor() && <div className="mb-4"><Banner tone="warn">Escribe tu nombre de revisor arriba a la derecha: es obligatorio para decidir.</Banner></div>}
      {pending.loading && !pending.data ? <Loading /> : pending.error ? <ErrorBox error={pending.error} onRetry={pending.reload} /> :
        queue.length === 0 ? <Empty title="No hay casos pendientes" hint="Ejecuta una conciliación para generar candidatos." /> : (
          <>
            <p className="mb-3 text-sm text-slate-600" aria-live="polite" data-testid="queue-count">{queue.length} caso(s) pendientes · los ambiguos primero</p>
            <ul className="space-y-4">{queue.map((c) => <Case key={c.id} c={c} evolus={evo.data} onDone={pending.reload} />)}</ul>
          </>
        )}
    </>
  );
}
