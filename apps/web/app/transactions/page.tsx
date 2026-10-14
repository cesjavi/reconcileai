"use client";

import Link from "next/link";
import { useState } from "react";
import { STATUSES, Status, Tx, money, useApi } from "@/lib/api";
import { Card, Empty, ErrorBox, Loading, PageHeader, StatusBadge } from "../_components/ui";

export default function Transactions() {
  const [status, setStatus] = useState<Status | "">("");
  const [q, setQ] = useState("");
  const { data, error, loading, reload } = useApi<Tx[]>(`/bank-transactions?limit=500${status ? `&status=${status}` : ""}`);

  const rows = (data ?? []).filter((t) => !q || `${t.external_id} ${t.description} ${t.voucher} ${t.document}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <>
      <PageHeader title="Movimientos bancarios" subtitle="Filtra por estado de conciliación y abre un movimiento para ver su evidencia, candidatos y reglas." />
      <Card>
        <div className="mb-4 flex flex-wrap items-end gap-4">
          <fieldset>
            <legend className="mb-1 text-sm font-medium">Estado</legend>
            <div className="flex flex-wrap gap-1" role="group" aria-label="Filtrar por estado">
              {(["", ...STATUSES] as const).map((s) => (
                <button key={s || "all"} aria-pressed={status === s} onClick={() => setStatus(s)}
                  className={`rounded-full border px-3 py-1 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-600 ${status === s ? "border-teal-700 bg-teal-700 text-white" : "border-slate-300 bg-white hover:bg-slate-50"}`}>
                  {s || "Todos"}
                </button>
              ))}
            </div>
          </fieldset>
          <label className="text-sm font-medium">Buscar
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="ID, texto, comprobante, CUIT…" className="mt-1 block w-64 rounded-lg border border-slate-300 px-3 py-1.5 font-normal" />
          </label>
        </div>
        {loading && !data ? <Loading /> : error ? <ErrorBox error={error} onRetry={reload} /> :
          rows.length === 0 ? <Empty title="No hay movimientos con ese filtro" hint={data?.length === 0 && !status ? "Importa datos para empezar." : undefined} /> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="tx-table">
                <caption className="sr-only">Movimientos bancarios</caption>
                <thead className="text-left text-xs uppercase text-slate-500"><tr><th className="p-2">ID</th><th className="p-2">Fecha</th><th className="p-2 text-right">Importe</th><th className="p-2">Descripción</th><th className="p-2">Comprobante</th><th className="p-2">Estado</th></tr></thead>
                <tbody>
                  {rows.map((t) => (
                    <tr key={t.id} className="border-t hover:bg-slate-50">
                      <td className="p-2"><Link className="font-medium text-teal-800 underline" href={`/transactions/${t.id}`}>{t.external_id}</Link></td>
                      <td className="p-2 whitespace-nowrap">{t.date}</td>
                      <td className="p-2 text-right tabular-nums">{money(t.amount)}</td>
                      <td className="max-w-xs truncate p-2" title={t.description}>{t.description}</td>
                      <td className="p-2">{t.voucher || "—"}</td>
                      <td className="p-2"><StatusBadge status={t.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-xs text-slate-500" aria-live="polite">{rows.length} movimientos</p>
            </div>
          )}
      </Card>
    </>
  );
}
