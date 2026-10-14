# Entrega — AMD Developer Hackathon: ACT III

Fecha límite indicada por el equipo: **18-oct-2026 07:00 hora de Argentina**. La página del evento
([lablab](https://lablab.ai/ai-hackathons/amd-developer-hackathon-act-iii)) dice "Online build: 12–18 de octubre" y no
publica hora ni zona de entrega: **confirmar en la plataforma antes de depender de esa hora**.

## Campos del formulario (borrador)

- **Título:** ReconcileAI
- **Descripción corta:** Conciliación bancaria asistida por IA, auditable y con revisión humana: un motor
  determinista decide, un modelo abierto solo propone referencias que el motor verifica.
- **Descripción larga:** ver [README](../README.md) y [architecture.md](architecture.md). Texto sugerido: «ReconcileAI
  concilia extractos bancarios contra depósitos del sistema con reglas ordenadas (comprobante+importe, documento+
  importe+ventana, importe único, referencias verificadas). Los casos ambiguos y todo lo que no sea una coincidencia
  exacta pasan a una cola de revisión humana. Un modelo abierto servido con vLLM extrae CUIT/DNI, comprobantes y
  referencias del texto libre; cada dato conserva su evidencia literal y el motor determinista lo valida: la IA nunca
  aprueba. Cada acción queda en una cadena de auditoría con hashes.» **Añadir las frases sobre AMD y Evolus solo
  cuando estén verificadas** (ver checklist).
- **Track:** Evolus Business Agents on AMD (y AMD como tecnología obligatoria).
- **Tags:** FastAPI, Next.js, PostgreSQL, vLLM, ROCm, Evolus, fintech.
- **Repositorio público:** `[PENDIENTE: URL]` — hoy la carpeta no es un repositorio Git.
- **Aplicación/URL:** `[PENDIENTE: despliegue]`.
- **Video / deck / portada:** `[PENDIENTE]` — guion y estructura en [pitch.md](pitch.md).

## Checklist de requisitos

Leyenda: ✅ verificado · 🟡 parcial / simulado · ❌ pendiente. Solo se marca ✅ lo que se ejecutó y se observó.

### AMD

| Requisito | Estado | Evidencia / qué falta |
|---|---|---|
| Tecnología AMD usada (obligatoria para premios) | ❌ | No hay endpoint ni ejecución en AMD Developer Cloud |
| Modelo abierto servido con vLLM propio en AMD Developer Cloud | ❌ | Guía lista: [amd-vllm-deploy.md](amd-vllm-deploy.md). Falta ejecutarla |
| Compatibilidad ROCm / memoria GPU comprobadas en la instancia | ❌ | Salidas de `rocm-smi`, PyTorch/HIP y versión de vLLM por capturar |
| La app consume ese endpoint | 🟡 | Cliente OpenAI-compatible probado contra servidor simulado; integración real opcional sin correr |
| Métricas de inferencia reales en la UI | 🟡 | Se calculan solo con llamadas no-mock; hoy no hay ninguna real |
| Mock claramente identificado | ✅ | Rótulo MOCK en API (`is_mock`) y UI; excluido de métricas; test e2e |

### Evolus

| Requisito | Estado | Evidencia / qué falta |
|---|---|---|
| Workspace gratuito con código del evento | ❌ | Se crea en app.evolus.ai con el código del kickoff |
| Agente principal con modelo abierto en AMD (vLLM propio) | ❌ | Depende de los dos puntos anteriores |
| ≥ 2 building blocks de Evolus | 🟡 | Workflows + AI Tools implementados en el cliente y la app; **sin ejecución real**. Document Extractor: solo adaptador |
| Manejar Evolus desde la app vía API | 🟡 | `POST /candidates/{id}/evolus-review` y `refresh`; probado contra el contrato documentado, no contra `api.evolus.ai` |
| Ids/estados/errores de ejecución registrados | ✅ | Tabla `evolus_executions` + auditoría (probado con doble del contrato) |
| Herramientas seguras e idempotentes; nunca aprueban ambiguos | ✅ | API `/agent/*` con tests (422 al recomendar APPROVE en ambiguo; sin endpoint de decisión) |
| Contratos faltantes documentados | ✅ | [evolus-workflow.md](evolus-workflow.md#información-pendiente) |

### Entrega general

| Requisito | Estado | Evidencia / qué falta |
|---|---|---|
| App contenerizada | 🟡 | Dockerfiles y compose escritos; **no probados** (sin Docker en la máquina) |
| Repositorio público de GitHub | ❌ | Sin Git ni remoto |
| README que se ejecuta | 🟡 | Pasos locales verificados; Docker sin verificar |
| Claves fuera del repositorio | ✅ | `.env` ignorado; búsqueda de secretos sin hallazgos (solo un token falso en un test); `.env.example` sin valores |
| Migraciones | ✅ | `alembic upgrade head` en SQLite; test de deriva modelos↔migraciones. PostgreSQL: sin verificar |
| Tests unitarios, de integración y e2e | ✅ | 101 passed + 2 skipped; 6 e2e (ver [progress.md](progress.md)) |
| Video de demo, deck, portada | ❌ | Ver [pitch.md](pitch.md) |
| Dataset sintético con casos esperados | ✅ | `demo/bank.csv` (109), `demo/deposits.csv` (108), `demo/expected.json` |

## Revisión de seguridad básica (hecha)

| Punto | Resultado |
|---|---|
| Secretos en el código | Ninguno encontrado (patrón de claves/tokens/contraseñas); `.gitignore` excluye `.env*` salvo el ejemplo |
| Entrada | Carga CSV limitada a 5 MB y 50 000 filas, UTF-8, columnas desconocidas rechazadas; consultas por ORM (sin SQL armado a mano) |
| Datos personales | CUIT/DNI se enmascaran antes de salir hacia Evolus; los logs de inferencia no incluyen texto ni claves (test) |
| Autenticación | **Débil**: `X-Actor` es declarativo; sin usuarios ni roles. Pendiente antes de producción |
| Agente | Token Bearer comparado en tiempo constante; API apagada si no hay token |
| Red | CORS restringido por variable; sin TLS ni límite de tasa propios (requiere proxy) |
| Contenedores | API corre como usuario no root; la web usa `USER node` |
| vLLM | Sin autenticación por defecto: la guía exige `--api-key` y restringir el puerto |

## Qué NO afirmar en la entrega mientras siga pendiente

- "Corre sobre AMD / MI300X" sin las evidencias de la sección 8 de la guía AMD.
- "Integrado con Evolus" sin una ejecución real registrada (`remote_execution_id` de `api.evolus.ai`).
- Cualquier cifra de ahorro, precisión o latencia que no salga de una medición propia.
- "Contenerizado y probado" sin haber corrido `docker compose up`.

## Pasos para cerrar la entrega (orden sugerido)

1. Instancia vLLM en AMD → capturas y `INFERENCE_INTEGRATION=1`.
2. Workspace Evolus → workflow, claves y `EVOLUS_INTEGRATION=1`.
3. `docker compose up --build` en una máquina con Docker; corregir lo que falle.
4. `git init`, revisar `git status` (sin `.env`, `*.db`, `node_modules`), crear repo público y subir.
5. Desplegar una URL (o declarar que la demo es local con video).
6. Grabar video con [demo-script.md](demo-script.md), armar deck, actualizar este checklist y [progress.md](progress.md).
