# ReconcileAI

Conciliación bancaria asistida por IA, **auditable y con revisión humana** — AMD Developer Hackathon: ACT III
(track *Evolus Business Agents on AMD*).

Un motor **determinista** concilia movimientos bancarios contra depósitos del sistema con reglas ordenadas.
Un modelo abierto (vLLM, pensado para AMD ROCm) solo **propone** referencias extraídas del texto libre; el motor
las verifica y nunca aprueba por sí mismo. Toda decisión humana queda en una cadena de auditoría con hashes.
Todos los datos de `demo/` son **sintéticos**.

> **Estado honesto** (detalle en [docs/progress.md](docs/progress.md)): el motor, la API, la UI y los tests son
> reales y se ejecutan localmente. La inferencia sobre AMD y la integración con Evolus **no están verificadas contra
> servicios reales** (faltan endpoint y credenciales); por defecto corren en modo `mock`/`disabled`, y la UI lo
> rotula como tal.

## Cómo funciona

| Regla | Evidencia | Resultado |
|---|---|---|
| R1 | comprobante + importe exacto | `MATCHED` automático (si es único) |
| R2 | CUIT/DNI + importe + ventana de fechas | `SUGGESTED` |
| R3 | importe único dentro de la ventana | `SUGGESTED` |
| R4 | referencia propuesta por IA **y** verificada de forma determinista | `SUGGESTED` (nunca automático) |

Varios candidatos para un mismo movimiento (o al revés) ⇒ `AMBIGUOUS`: solo una persona lo resuelve, con nota
obligatoria. Sin candidato ⇒ `UNMATCHED`. Candidato rechazado ⇒ `REJECTED` y no vuelve a proponerse.
La base de datos impide dos vínculos efectivos sobre el mismo movimiento o depósito (índices únicos parciales).

## Estructura

| Ruta | Contenido |
|---|---|
| `apps/web` | Next.js + TypeScript + Tailwind: dashboard, importación, conciliación, movimientos, revisión, monitor de inferencia, auditoría |
| `apps/api` | FastAPI, SQLAlchemy, Alembic, auditoría encadenada, endpoints de agente |
| `services/reconciliation` | Reglas deterministas (librería pura) |
| `services/inference` | Cliente OpenAI-compatible para vLLM + extractor `mock` |
| `services/evolus` | Cliente tipado de la API REST de Evolus + mock simulado |
| `demo` | CSV sintéticos (109 y 108 filas), `expected.json` y `generate.py` |
| `tests` | Playwright e2e |
| `docs` | arquitectura, despliegue AMD, workflow Evolus, guion de demo, pitch, entrega |

## Ejecutar con Docker (no verificado en esta máquina: no tiene Docker)

```bash
cp .env.example .env          # define POSTGRES_PASSWORD
docker compose up --build     # web :3000 · API :8000/docs
```
Luego en la UI: **Importar → Cargar dataset sintético de demo → Conciliar → Revisión**.

## Ejecutar en local (verificado en Windows 11, Python 3.11, Node 24)

```bash
python -m venv .venv
.venv/Scripts/pip install -r apps/api/requirements-dev.txt        # Linux/macOS: .venv/bin/pip
export PYTHONPATH="$PWD/apps/api:$PWD/services/reconciliation:$PWD/services/inference:$PWD/services/evolus"
export DEMO_DIR="$PWD/demo"
cd apps/api && ../../.venv/Scripts/python -m uvicorn app.main:app --port 8000     # SQLite por defecto
# otra terminal
cd apps/web && npm install && NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```
En PowerShell usa `$env:PYTHONPATH = "...;..."` con `;` como separador.

## Tests

```bash
.venv/Scripts/python -m pytest                       # 101 passed, 2 skipped (integraciones reales opcionales)
cd apps/web && NEXT_PUBLIC_API_URL=http://localhost:8100 npm run build
cd tests && npm install && npx playwright install chromium && npx playwright test    # 6 e2e
```
Integraciones reales (opcionales, requieren tus credenciales):
`INFERENCE_INTEGRATION=1 INFERENCE_PROVIDER=vllm INFERENCE_BASE_URL=… INFERENCE_MODEL=… pytest services/inference`
y `EVOLUS_INTEGRATION=1 EVOLUS_MODE=live EVOLUS_API_KEY=… EVOLUS_APPLICATION_ID=… pytest services/evolus`.

## Configuración y secretos

Todo por variables de entorno ([.env.example](.env.example)). `.env` está ignorado por Git; ninguna clave vive en el
repositorio. Si `INFERENCE_PROVIDER=vllm` está mal configurado la API responde 503: **nunca cae a mock en silencio**.

## Documentación

[Arquitectura](docs/architecture.md) · [Progreso y estado real](docs/progress.md) ·
[Desplegar vLLM en AMD Developer Cloud](docs/amd-vllm-deploy.md) · [Workflow Evolus](docs/evolus-workflow.md) ·
[Guion de demo (3 min)](docs/demo-script.md) · [Pitch, video y diapositivas](docs/pitch.md) ·
[Entrega y checklist](docs/submission.md)
