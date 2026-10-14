"use client";

import { Fragment, useState } from "react";
import { AuditRow, useApi } from "@/lib/api";
import { Banner, Card, Empty, ErrorBox, Loading, PageHeader } from "../_components/ui";

export default function Audit() {
  const log = useApi<AuditRow[]>("/audit?limit=200");
  const chain = useApi<{ valid: boolean; checked: number; broken_at: number | null }>("/audit/verify");
  const [open, setOpen] = useState<number | null>(null);

  return (
    <>
      <PageHeader title="Historial de auditoría" subtitle="Cada importación, ejecución y decisión queda registrada en una cadena de hashes. Los registros no se pueden modificar desde la aplicación." />
      <div className="mb-4" aria-live="polite">
        {chain.data && (chain.data.valid
          ? <Banner tone="ok"><span data-testid="chain-ok">Cadena íntegra</span> · {chain.data.checked} eventos verificados.</Banner>
          : <Banner tone="warn">Cadena rota en el evento id {chain.data.broken_at}: hubo una modificación fuera de la aplicación.</Banner>)}
      </div>
      <Card>
        {log.loading && !log.data ? <Loading /> : log.error ? <ErrorBox error={log.error} onRetry={log.reload} /> :
          !log.data?.length ? <Empty title="Todavía no hay eventos" /> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <caption className="sr-only">Eventos de auditoría, del más reciente al más antiguo</caption>
                <thead className="text-left text-xs uppercase text-slate-500"><tr><th className="p-2">#</th><th className="p-2">Fecha</th><th className="p-2">Actor</th><th className="p-2">Acción</th><th className="p-2">Entidad</th><th className="p-2">Hash</th><th className="p-2"><span className="sr-only">Detalle</span></th></tr></thead>
                <tbody>
                  {log.data.map((a) => (
                    <Fragment key={a.seq}>
                      <tr className="border-t">
                        <td className="p-2">{a.seq}</td><td className="p-2 whitespace-nowrap">{new Date(a.ts).toLocaleString("es-AR")}</td>
                        <td className="p-2">{a.actor}</td><td className="p-2 font-medium">{a.action}</td>
                        <td className="p-2">{a.entity}{a.entity_id ? ` #${a.entity_id}` : ""}</td>
                        <td className="p-2 font-mono text-xs">{a.hash.slice(0, 12)}</td>
                        <td className="p-2"><button aria-expanded={open === a.seq} onClick={() => setOpen(open === a.seq ? null : a.seq)} className="text-teal-800 underline">{open === a.seq ? "Ocultar" : "Detalle"}</button></td>
                      </tr>
                      {open === a.seq && <tr><td colSpan={7} className="bg-slate-50 p-3"><pre className="overflow-auto text-xs">{JSON.stringify(a.payload, null, 2)}</pre></td></tr>}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </Card>
    </>
  );
}
