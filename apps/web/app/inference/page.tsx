"use client";

import { EvolusStatus, InfHealth, InfMetrics, Inference, useApi } from "@/lib/api";
import { Banner, Card, Empty, ErrorBox, Loading, PageHeader } from "../_components/ui";

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="text-xs font-medium uppercase text-slate-500">{label}</div>
      <div className="text-2xl font-bold tabular-nums">{value}</div>
      {note && <div className="text-xs text-slate-500">{note}</div>}
    </div>
  );
}

export default function InferenceMonitor() {
  const health = useApi<InfHealth>("/inference/health");
  const metrics = useApi<InfMetrics>("/inference/metrics");
  const logs = useApi<Inference[]>("/inference/logs?limit=20");
  const evo = useApi<EvolusStatus>("/evolus/status");
  const fmt = (n: number | null) => (n === null ? "—" : `${n} ms`);

  return (
    <>
      <PageHeader title="AMD Inference Monitor" subtitle="Solo se muestran datos medidos a partir de llamadas registradas. Las llamadas MOCK nunca se cuentan como inferencia real." />
      <div className="space-y-4">
        <Card title="Endpoint de inferencia" action={<button onClick={() => { health.reload(); metrics.reload(); logs.reload(); }} className="text-sm font-medium text-teal-800 underline">Actualizar</button>}>
          {health.loading && !health.data ? <Loading /> : health.error ? <ErrorBox error={health.error} onRetry={health.reload} /> : health.data && (
            health.data.is_mock ? (
              <Banner tone="warn"><b>MODO MOCK.</b> {health.data.detail}. Para usar un endpoint vLLM propio configura <code>INFERENCE_PROVIDER=vllm</code>, <code>INFERENCE_BASE_URL</code> e <code>INFERENCE_MODEL</code>.</Banner>
            ) : (
              <div className="space-y-2 text-sm">
                <Banner tone={health.data.status === "ok" ? "ok" : "warn"}>
                  Estado del endpoint: <b>{health.data.status}</b>{health.data.detail && ` — ${health.data.detail}`}
                </Banner>
                <dl className="grid grid-cols-[10rem_1fr] gap-y-1">
                  <dt className="text-slate-500">Modelo configurado</dt><dd>{health.data.model}{health.data.model_listed === false && " (no listado por el endpoint)"}</dd>
                  <dt className="text-slate-500">Latencia /models</dt><dd>{fmt(health.data.latency_ms === null ? null : Math.round(health.data.latency_ms))}</dd>
                  <dt className="text-slate-500">Hardware declarado</dt><dd>{health.data.hardware_label || "no declarado"} <span className="text-xs text-slate-500">(texto del operador; la aplicación no puede verificar la GPU)</span></dd>
                </dl>
              </div>
            )
          )}
        </Card>

        <Card title="Métricas medidas">
          {metrics.loading && !metrics.data ? <Loading /> : metrics.error ? <ErrorBox error={metrics.error} onRetry={metrics.reload} /> : metrics.data && (
            !metrics.data.has_real_inference ? (
              <Empty title="Sin llamadas reales registradas" hint={metrics.data.mock_calls > 0 ? `Hay ${metrics.data.mock_calls} llamadas MOCK, que no se muestran como métricas de inferencia.` : "Ejecuta una conciliación con INFERENCE_PROVIDER=vllm para generar datos."} />
            ) : (
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4" data-testid="real-metrics">
                <Stat label="Llamadas reales" value={String(metrics.data.real_calls)} note={`${metrics.data.real_ok} ok · ${metrics.data.real_invalid_output} salida inválida · ${metrics.data.real_errors} error`} />
                <Stat label="Latencia media" value={fmt(metrics.data.real_latency_ms.avg)} note={`${metrics.data.real_latency_ms.samples} muestras`} />
                <Stat label="Latencia p50 / p95" value={`${metrics.data.real_latency_ms.p50 ?? "—"} / ${metrics.data.real_latency_ms.p95 ?? "—"}`} note="ms" />
                <Stat label="Con reintentos" value={String(metrics.data.real_retried)} />
                <Stat label="Aceptadas por el motor" value={String(metrics.data.accepted_by_engine)} note="referencias verificadas" />
                <Stat label="Descartadas por validación" value={String(metrics.data.items_dropped_by_validation)} note="evidencia ausente en el texto" />
                <Stat label="Modelos" value={metrics.data.models.join(", ") || "—"} />
              </div>
            )
          )}
        </Card>

        <Card title="Evolus">
          {evo.data ? (
            <div className="text-sm">
              {evo.data.mode === "disabled" && <Banner tone="info">Evolus deshabilitado (<code>EVOLUS_MODE=disabled</code>).</Banner>}
              {evo.data.mode === "mock" && <Banner tone="warn"><b>SIMULADO.</b> Las ejecuciones de Evolus son locales y no usan el servicio real.</Banner>}
              {evo.data.mode === "live" && <Banner tone="ok">Modo live · API key {evo.data.configured.api_key ? "configurada" : "ausente"} · workflow {evo.data.configured.workflow_id ? "configurado" : "sin configurar"}.</Banner>}
            </div>
          ) : <Loading />}
        </Card>

        <Card title="Últimas llamadas">
          {logs.loading && !logs.data ? <Loading /> : logs.error ? <ErrorBox error={logs.error} onRetry={logs.reload} /> :
            !logs.data?.length ? <Empty title="Sin llamadas registradas" /> : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <caption className="sr-only">Últimas llamadas de inferencia</caption>
                  <thead className="text-left text-xs uppercase text-slate-500"><tr><th className="p-2">Origen</th><th className="p-2">Modelo</th><th className="p-2">Estado</th><th className="p-2">Latencia</th><th className="p-2">Intentos</th><th className="p-2">Aceptada</th><th className="p-2">Request</th></tr></thead>
                  <tbody>
                    {logs.data.map((l) => (
                      <tr key={l.request_id} className="border-t">
                        <td className="p-2">{l.is_mock ? <span className="rounded bg-amber-100 px-1.5 text-xs font-bold text-amber-900">MOCK</span> : <span className="rounded bg-teal-100 px-1.5 text-xs font-bold text-teal-900">vLLM</span>}</td>
                        <td className="p-2">{l.model}</td><td className="p-2">{l.status}</td>
                        <td className="p-2">{l.is_mock ? "n/a" : `${l.latency_ms.toFixed(0)} ms`}</td><td className="p-2">{l.attempts}</td>
                        <td className="p-2">{l.accepted ? "sí" : "no"}</td><td className="p-2 font-mono text-xs">{l.request_id.slice(0, 8)}</td>
                      </tr>
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
