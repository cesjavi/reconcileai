"use client";

import { useState } from "react";
import { ApiError, api, useApi, Batch } from "@/lib/api";
import { Banner, Btn, Card, Empty, ErrorBox, Loading, PageHeader } from "../_components/ui";

type Result = { batch_id: number; duplicate_file: boolean; rows: number; imported: number; skipped_existing: number; duplicates_in_file: number };
type Failure = { message: string; errors: { line?: number; id?: string; error: string }[] };

function Uploader({ kind, title, onDone }: { kind: "bank" | "deposits"; title: string; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!file) return;
    setBusy(true); setResult(null); setFailure(null); setError(null);
    const fd = new FormData();
    fd.append("file", file);
    try { setResult(await api<Result>(`/imports/${kind}`, { method: "POST", body: fd })); onDone(); }
    catch (e) {
      const err = e as ApiError;
      const d = err.detail as Failure | string;
      if (typeof d === "object" && d && "errors" in d) setFailure(d); else setError(err.message);
    } finally { setBusy(false); }
  };

  return (
    <Card title={title}>
      <p className="mb-3 text-sm text-slate-600">Columnas: <code>id,date,amount,description,document,voucher</code> (description, document y voucher opcionales). Fechas <code>YYYY-MM-DD</code> o <code>DD/MM/YYYY</code>.</p>
      <label className="block text-sm font-medium" htmlFor={`file-${kind}`}>Archivo CSV</label>
      <input id={`file-${kind}`} type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className="mt-1 block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm file:font-medium" />
      <Btn className="mt-3" disabled={!file || busy} onClick={submit}>{busy ? "Validando e importando…" : "Validar e importar"}</Btn>
      <div aria-live="polite" className="mt-3 space-y-2">
        {result && (
          <Banner tone={result.duplicate_file ? "info" : "ok"}>
            {result.duplicate_file
              ? <>Este archivo ya había sido importado (lote #{result.batch_id}). No se cambió nada.</>
              : <>Lote #{result.batch_id}: {result.imported} importadas de {result.rows} filas válidas · {result.skipped_existing} ya existían · {result.duplicates_in_file} duplicadas dentro del archivo.</>}
          </Banner>
        )}
        {failure && (
          <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
            <p className="font-medium">{failure.message}</p>
            <ul className="mt-2 max-h-48 list-disc space-y-1 overflow-auto pl-5">
              {failure.errors.map((e, i) => <li key={i}>{e.line ? `Línea ${e.line}: ` : e.id ? `ID ${e.id}: ` : ""}{e.error}</li>)}
            </ul>
          </div>
        )}
        {error && <ErrorBox error={error} />}
      </div>
    </Card>
  );
}

export default function ImportPage() {
  const batches = useApi<Batch[]>("/batches");
  const [seeding, setSeeding] = useState(false);
  const [seedErr, setSeedErr] = useState<string | null>(null);

  const seed = async () => {
    setSeeding(true); setSeedErr(null);
    try { await api("/demo/seed", { method: "POST" }); await batches.reload(); }
    catch (e) { setSeedErr((e as Error).message); }
    finally { setSeeding(false); }
  };

  return (
    <>
      <PageHeader title="Importar CSV" subtitle="La importación es atómica: si una fila es inválida no se importa nada. Subir dos veces el mismo archivo no duplica datos.">
        <Btn variant="ghost" onClick={seed} disabled={seeding}>{seeding ? "Cargando…" : "Cargar dataset sintético de demo"}</Btn>
      </PageHeader>
      {seedErr && <div className="mb-4"><ErrorBox error={seedErr} /></div>}
      <div className="grid gap-4 lg:grid-cols-2">
        <Uploader kind="bank" title="Movimientos bancarios" onDone={batches.reload} />
        <Uploader kind="deposits" title="Depósitos del sistema" onDone={batches.reload} />
      </div>
      <div className="mt-6">
        <Card title="Lotes importados">
          {batches.loading && !batches.data ? <Loading /> : batches.error ? <ErrorBox error={batches.error} onRetry={batches.reload} /> :
            !batches.data?.filter((b) => b.kind !== "RUN").length ? <Empty title="No hay lotes importados" /> : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <caption className="sr-only">Lotes importados</caption>
                  <thead className="text-left text-xs uppercase text-slate-500"><tr><th className="p-2">Lote</th><th className="p-2">Tipo</th><th className="p-2">Archivo</th><th className="p-2">Filas</th><th className="p-2">Importadas</th><th className="p-2">Por</th></tr></thead>
                  <tbody>
                    {batches.data!.filter((b) => b.kind !== "RUN").map((b) => (
                      <tr key={b.id} className="border-t"><td className="p-2">#{b.id}</td><td className="p-2">{b.kind === "BANK" ? "Banco" : "Depósitos"}</td><td className="p-2">{b.filename}</td><td className="p-2">{b.stats.rows}</td><td className="p-2">{b.stats.imported}</td><td className="p-2">{b.created_by}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
        </Card>
      </div>
    </>
  );
}
