# Integración con Evolus

Track: *Evolus Business Agents on AMD* — un agente que ejecuta un proceso de negocio real sobre Evolus, con un
modelo abierto servido en AMD, usando ≥ 2 building blocks y manejando Evolus desde la app por API.

## Qué se pudo verificar de la documentación pública

Fuentes: [lablab – evento](https://lablab.ai/ai-hackathons/amd-developer-hackathon-act-iii),
[evolus.ai/developers](https://evolus.ai/developers), [blog de Evolus](https://evolus.ai/en/blog/evolus-amd-developer-hackathon-lablab).
(Leídas con una herramienta que resume páginas: **contrasta cada contrato con la página original y con la
referencia de API dentro de tu workspace**.)

| Elemento | Contrato publicado | Usado en el código |
|---|---|---|
| Auth REST | `X-ApiKey` + `X-Application-Id`, base `https://api.evolus.ai/api/v1` | sí |
| Ejecutar workflow | `POST /workflows/{id}/execute`, multipart (`input`, `parameters` JSON plano, `file`, `callbackUrl`…), `202` con `jobId/executionId/enqueuedAt/traceId` y cabecera `X-Workflow-Execution-Id`; `409` si está apagado | sí (`input`, `parameters`) |
| Consultar ejecución | `GET /workflows/{id}/executions/{executionId}`, `status` ∈ Pending/Running/Completed/Failed | sí |
| AI Tools | `POST /ai-tools/{tool}/run` `{text, secondaryText, options}` → `{tool, output, creditsConsumed, truncated}`; 11 herramientas (`summarize`, `anonymize`, …) | sí (`summarize`) |
| Document Extractor | `POST /agents/{agentId}/json/{extractorId}/ask-file?useWebhook=false`, campo `file`; cabeceras `X-AskFile-*` | adaptador y test; **no conectado a la app** |
| Chat OpenAI-compatible | `https://api.evolus.ai/v1`, modelo `<applicationId>:<agentId>`, Bearer | no usado |
| MCP | `https://api.evolus.ai/mcp` | no usado |
| Límite | 60 req/min por workspace; 402 sin créditos | el cliente reintenta 429/5xx y no reintenta 402 |

## Building blocks y su estado

| Building block | Para qué lo usa ReconcileAI | Estado |
|---|---|---|
| **Workflows** | revisión asistida de un candidato: la app lanza una ejecución con el caso y guarda `executionId`/`traceId`/estado | cliente implementado y probado contra un doble del contrato; **workflow no creado en Evolus; sin ejecución real** |
| **AI Tools** (`summarize`) | resumen del caso para el revisor humano (texto informativo) | igual que arriba |
| **Document Extractors** | extraer movimientos desde PDFs de extractos | solo `extract_document`; faltan el esquema del extractor y su cableado |
| Agente principal con modelo abierto en AMD | modelo propio de Evolus apuntando al vLLM de AMD | **pendiente**: depende de la configuración del workspace y del endpoint AMD |

Hasta ejecutar contra el workspace real no se puede afirmar "al menos dos building blocks de Evolus usados":
el código y los contratos están, la ejecución real no.

## Diseño del flujo (workflow)

```
1 Entrada        la app (humano o evento) pide análisis de un candidato SUGGESTED/AMBIGUOUS
2 Normalización  importador ya normalizó; el caso sale con CUIT/DNI enmascarados (***786)
3 Candidatos     motor determinista R1–R4 (en la app, NO en Evolus)
4 Inferencia AMD (a) extracción de referencias: cliente vLLM de la app → verificadas por el motor
                 (b) análisis del caso: agente/workflow de Evolus con el modelo abierto conectado
5 Validación     el motor revalida importe, ventana y evidencia al aprobar; ninguna salida de Evolus la salta
6 Derivación     ambiguos y R2–R4 → cola humana; el agente solo puede NEEDS_HUMAN en ambiguos
7 Auditoría      evento encadenado por cada llamada (evolus_review_started/failed, execution_completed, agent_recommendation)
8 Respuesta      ejecución con ids, estado y error visible en la UI; recomendación guardada como informativa
```

### Llamadas salientes (app → Evolus)

`POST /candidates/{id}/evolus-review`: (1) AI Tool `summarize` del caso enmascarado → texto informativo;
(2) `execute_workflow(input=<caso>, parameters={candidate_id, rule, engine_status})` (plano, como exige el contrato).
Idempotente por `review:{candidate_id}:{status}`: repetir devuelve la misma ejecución; solo se reintenta si quedó en
`Error`. `POST /evolus/executions/{id}/refresh` consulta el estado. Se registran `remote_execution_id`, `trace_id`,
`status`, `error`, `credits_consumed` y modo (`live`/`mock`).

### API entrante para el agente (Evolus → app)

Protegida con `Authorization: Bearer $AGENT_API_TOKEN` (comparación en tiempo constante; vacío ⇒ desactivada).
- `GET /agent/cases`: solo candidatos pendientes, con CUIT/DNI enmascarados.
- `POST /agent/cases/{id}/recommendation` + cabecera `Idempotency-Key`: guarda `APPROVE|REJECT|NEEDS_HUMAN`.

Garantías **impuestas por el código y cubiertas por tests**: ningún endpoint con ese token aprueba, rechaza ni cambia
estados; un agente no puede recomendar `APPROVE` sobre un candidato `AMBIGUOUS` (422); no se puede recomendar sobre
casos ya decididos (409); repetir la misma clave no duplica (idempotente); el token del agente no sirve como
identidad para `approve/reject` (requieren `X-Actor`).

## Qué debes hacer en el workspace (manual)

1. Crear el workspace con el **código del evento** (según lablab, un workspace creado antes no cuenta).
2. Conectar el modelo: endpoint OpenAI-compatible de tu vLLM en AMD (ver [amd-vllm-deploy.md](amd-vllm-deploy.md)).
3. Crear una API key y anotar `applicationId`. Crear el workflow (p. ej. "Revisión de candidato") y anotar su id.
4. Si el workflow debe leer/escribir en la app (`/agent/*`), esta debe ser alcanzable por HTTPS desde Evolus
   (túnel o despliegue); `localhost` no sirve.
5. Exportar `EVOLUS_MODE=live`, `EVOLUS_API_KEY`, `EVOLUS_APPLICATION_ID`, `EVOLUS_WORKFLOW_ID`, `AGENT_API_TOKEN`
   y ejecutar `EVOLUS_INTEGRATION=1 pytest services/evolus -k real_evolus`.

## Información pendiente

Lo siguiente **no está en la documentación pública consultada** y no se ha inventado:
1. Formato de creación/definición de workflows (¿solo UI o también API?) y los pasos disponibles.
2. Si un paso de workflow puede llamar a una API HTTP externa con cabecera Bearer propia (necesario para `/agent/*`).
3. Cuerpo completo de `GET …/executions/{id}`: dónde viene el resultado (el cliente conserva el JSON en `raw`).
4. Payload del webhook/callback y semántica de `callbackApiKey`/`callbackApiKeyName`.
5. Cómo se define el esquema de un Document Extractor y la forma exacta de su respuesta (hay que mapearla a filas CSV).
6. Campos para registrar un endpoint vLLM propio como modelo del workspace.
7. Cuerpo de errores y comportamiento al superar los 60 req/min (¿429? ¿`Retry-After`?).
8. Opciones válidas de `summarize` (`options`) y límites por herramienta.
9. Inconsistencia a aclarar: lablab indica workspace gratis hasta el 31-oct-2026; el blog de Evolus, hasta el
   15-nov-2026 23:59 (hora de Italia).
10. Cómo se obtiene el código del evento y el cupón de créditos (se comparten en el kickoff).
