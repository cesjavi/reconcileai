# Progreso y estado real

Última verificación: 2026-10-13 (Windows 11, Python 3.11.9, Node 24.18, sin Docker instalado).
Fecha límite indicada por el equipo: **18-oct-2026 07:00 (Argentina)**. La página del evento en lablab.ai
no publica hora ni zona de la entrega (indica "To be announced"): **confirmar en la plataforma**.

## Resultados de tests (medidos, no estimados)

| Suite | Comando | Resultado |
|---|---|---|
| Reglas deterministas | `pytest services/reconciliation` | 14 passed |
| Inferencia (servidor HTTP simulado) | `pytest services/inference` | 14 passed, 1 skipped (integración real) |
| Cliente Evolus (servidor con el contrato documentado) | `pytest services/evolus` | 18 passed, 1 skipped (integración real) |
| API: importación, motor, concurrencia, auditoría, Evolus, migraciones | `pytest apps/api` | 55 passed |
| **Total Python** | `pytest` en la raíz | **101 passed, 2 skipped** |
| End-to-end (Playwright, Chromium) | `cd tests && npx playwright test` | **6 passed** |
| Build web con chequeo de tipos | `npm run build` | OK |

Los tests de concurrencia se repitieron 3 veces seguidas sin fallos. La cobertura de código **no se midió**.
Tiempos medidos en el dataset de demo (SQLite local, extractor mock): importar ambos CSV 72 ms; primera
conciliación 111 ms (24 llamadas al extractor); reejecución 29 ms. No son benchmarks de producción.

## Qué funciona realmente / simulado / pendiente

| Componente | Estado | Detalle |
|---|---|---|
| Importación CSV (esquema, Decimal, fechas, CUIT con dígito verificador, DNI, comprobantes, hashes, dedupe) | **Real, probado** | atómica; mismo archivo ⇒ mismo lote |
| Motor R1–R4, ambigüedad, ventana de fechas, unicidad, idempotencia | **Real, probado** | resultado contra `demo/expected.json` coincide fila a fila |
| Concurrencia (aprobaciones, importaciones y ejecuciones simultáneas) | **Real, probado en SQLite** | en Postgres: no probado |
| Auditoría encadenada + inmutabilidad en la aplicación | **Real, probado** | sin triggers en BD |
| UI (8 pantallas) conectada a la API real | **Real, probado** (e2e) | — |
| Cliente OpenAI-compatible para vLLM | **Real como código; probado solo contra un servidor simulado** | no se ha llamado a ningún vLLM real |
| **Inferencia sobre AMD (MI300X/ROCm)** | **PENDIENTE — no verificada** | no hay endpoint ni credenciales; ninguna métrica de la UI proviene de GPU AMD |
| Extractor `mock` | **Simulado** (regex) | rotulado MOCK en API y UI; excluido de las métricas reales |
| Cliente REST de Evolus (workflow, AI Tool, extractor) | **Real como código; probado solo contra un servidor que replica el contrato publicado** | nunca se llamó a `api.evolus.ai` |
| Integración Evolus en la app (AI Tool `summarize` + ejecución de workflow + API de agente) | **Implementada; sin ejecución real** | falta workspace, claves y el workflow creado en Evolus |
| Document Extractor de Evolus (PDF bancarios) | **Solo adaptador** (`extract_document`); no está conectado a la API ni a la UI | el esquema del extractor no está documentado públicamente |
| Docker Compose / imágenes / migración en PostgreSQL | **No verificado** | Docker no está instalado en la máquina; el YAML se parsea correctamente y las migraciones corren en SQLite |
| Python 3.12 (Dockerfile) | **No verificado** | los tests corrieron en 3.11 |
| Repositorio público | **Hecho** | https://github.com/cesjavi/reconcileai (`prompt1.md` quedó en el historial del 2.º commit; solo contiene el prompt inicial, sin secretos) |
| Video de demo, deck, URL desplegada | **No hechos** | hay guion y estructura en `docs/pitch.md` |

## Problemas encontrados y resueltos

- `1e999` rompía `Decimal.quantize` (excepción no controlada): ahora se valida el rango antes. Cubierto por test.
- Un "DNI" de 7 dígitos aceptaba `20-1234-5`: era un caso de prueba mal planteado, no un fallo del parser.
- El primer prototipo interpretó "Evolus" como un módulo de ajuste de pesos. Era un error: Evolus es una plataforma
  externa (evolus.ai). Se eliminó ese módulo y `services/evolus` ahora es el cliente de su API.
- El primer prototipo usaba puntuación difusa; se reemplazó por reglas deterministas ordenadas (migración 0002).

## Evidencia sobre Evolus y contratos faltantes

Contratos usados (fuente: https://evolus.ai/developers, leída mediante una herramienta que resume páginas;
**verificar contra la página original y la referencia interna del workspace**):
`POST /workflows/{id}/execute` (multipart; 202 con `executionId`), `GET …/executions/{executionId}`
(`Pending|Running|Completed|Failed`), `POST /ai-tools/{tool}/run`, `POST /agents/{agentId}/json/{extractorId}/ask-file`,
cabeceras `X-ApiKey` + `X-Application-Id`. Lo que **falta** y está listado en [docs/evolus-workflow.md](evolus-workflow.md#información-pendiente).

## Comandos exactos

```bash
# tests Python
.venv/Scripts/python -m pytest
# build web y e2e
cd apps/web && NEXT_PUBLIC_API_URL=http://localhost:8100 npm run build
cd ../../tests && npx playwright test
# regenerar el dataset sintético y su resultado esperado
.venv/Scripts/python demo/generate.py
# migraciones
cd apps/api && DATABASE_URL=sqlite:///./x.db ../../.venv/Scripts/python -m alembic upgrade head
```

## Pendiente (ordenado por impacto para la entrega)

1. Levantar un vLLM propio en AMD Developer Cloud ([guía](amd-vllm-deploy.md)), ejecutar la integración real y
   capturar métricas reales del monitor. **Sin esto no se puede afirmar uso de AMD.**
2. Crear el workspace de Evolus con el código del evento, conectar el modelo, crear el workflow y una API key;
   ejecutar `EVOLUS_INTEGRATION=1`. **Sin esto no se puede afirmar uso real de Evolus.**
3. ~~Publicar el repositorio~~ (hecho).
4. Probar `docker compose up` en una máquina con Docker y corregir lo que falle.
5. Grabar el video y armar el deck con [docs/pitch.md](pitch.md).
6. Autenticación real de usuarios, triggers de inmutabilidad en PostgreSQL, límites de tasa.
