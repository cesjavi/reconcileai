# Arquitectura

```
CSV bancario ─┐                                   ┌───────────────┐
CSV depósitos ┴─► Importador (valida, normaliza,  │  PostgreSQL   │
                  hashea, deduplica) ───────────► │ (SQLite en    │
                                                  │  dev/tests)   │
                  ┌─────────────────────────────┐ └──────▲────────┘
 Ejecutar  ─────► │ Motor determinista R1→R4    │        │ misma transacción
                  │  R1 comprobante + importe   │        │
                  │  R2 documento + imp. + vent.│  Auditoría encadenada (hash)
                  │  R3 importe único en ventana│  Decisiones inmutables
                  │  R4 referencia de IA        │  InferenceLog por llamada
                  └──────────┬──────────────────┘
          propone referencias│ ▲ verifica (token literal en el texto,
                             ▼ │ importe exacto, ventana, igualdad con depósito)
                  ┌──────────────────┐
                  │ Cliente inferencia│── OpenAI-compatible ──► vLLM (AMD ROCm)   [no verificado]
                  │ (JSON + Pydantic) │── o extractor MOCK (regex, rotulado)       [real, es un mock]
                  └──────────────────┘
 Revisión humana ──► approve / reject (X-Actor obligatorio; el motor revalida al aprobar)
 Evolus ◄──────────► adaptador REST tipado (workflow + AI Tool)  [contrato documentado, sin credenciales]
                     API de agente /agent/* (token, solo lectura + recomendación)
```

## Principios de diseño

1. **La IA propone, el motor decide.** Una referencia de IA solo se acepta si (a) aparece literalmente como token(s)
   del texto bancario, (b) coincide con el comprobante/documento de un depósito, (c) el importe es exactamente igual y
   (d) la fecha está en `AI_WINDOW_DAYS`. Además cada ítem devuelto por el modelo debe traer una *evidencia* que
   sea subcadena del texto original, o se descarta (`services/inference/validation.py`). R4 nunca es automático.
2. **Humano en el bucle.** Solo R1 único (comprobante + importe exacto) se vincula solo, y es configurable
   (`AUTO_MATCH_RULES`). Los ambiguos requieren nota. Al aprobar, `check_invariants` revalida la regla.
3. **Unicidad garantizada por la base de datos.** Índices únicos parciales `uq_effective_bank` y
   `uq_effective_deposit` (`WHERE status='MATCHED'`): dos aprobaciones concurrentes sobre el mismo depósito no pueden
   ganar ambas. El perdedor recibe 409.
4. **Idempotencia.** Mismo archivo ⇒ mismo lote (hash SHA-256 por tipo); mismo `id` con el mismo contenido ⇒ se
   omite; mismo `id` con otro contenido ⇒ 409. Repetir la conciliación actualiza candidatos pendientes en el
   lugar, conserva sus ids y no toca decisiones.
5. **Atómico.** Cada endpoint escribe datos y evento de auditoría en la misma transacción. Una fila CSV inválida
   rechaza el archivo entero. En Postgres las ejecuciones se serializan con `pg_advisory_xact_lock`.
6. **Auditoría inmutable a nivel de aplicación.** `AuditEvent`, `ReconciliationDecision`, `InferenceLog` y
   `AgentRecommendation` rechazan UPDATE/DELETE (ORM y sentencias masivas). `seq` único evita bifurcar la cadena.
   Un cambio por SQL directo se detecta en `/audit/verify` (la inmutabilidad en BD, con triggers, está pendiente).
7. **Nada simulado se presenta como real.** Cada `InferenceLog` guarda `is_mock`; el monitor calcula métricas
   solo con llamadas no-mock; Evolus en modo `mock` marca `simulated: true` y ids `mock-*`.

## Estados

`BankTransaction`/`SystemDeposit`: `MATCHED` (vínculo efectivo) · `SUGGESTED` (un candidato por revisar) ·
`AMBIGUOUS` (varios) · `REJECTED` (solo candidatos rechazados) · `UNMATCHED` (ninguno).
`MatchCandidate`: `SUGGESTED | AMBIGUOUS | MATCHED | REJECTED`.

## Modelo de datos (Alembic 0001 → 0003)

`reconciliation_batches` (importaciones y ejecuciones) · `bank_transactions` · `system_deposits` ·
`match_candidates` · `reconciliation_decisions` · `audit_events` · `inference_logs` · `evolus_executions` ·
`agent_recommendations`. Un test compara el esquema de las migraciones con los modelos ORM.
La migración 0002 reemplaza de forma destructiva el esquema del primer prototipo (sin downgrade).

## API (resumen)

| Método y ruta | Función |
|---|---|
| `POST /imports/{bank\|deposits}` | importar CSV (idempotente, atómico) |
| `POST /demo/seed` | cargar dataset sintético |
| `POST /reconcile/run` | ejecutar reglas (idempotente) |
| `GET /candidates`, `/bank-transactions[/{id}]`, `/deposits`, `/summary`, `/batches` | consulta |
| `POST /candidates/{id}/approve \| reject` | decisión humana (`X-Actor` obligatorio) |
| `GET /inference/health \| metrics \| logs` | monitor de inferencia |
| `GET /audit`, `/audit/verify` | auditoría |
| `GET /evolus/status`, `POST /candidates/{id}/evolus-review`, `POST /evolus/executions/{id}/refresh` | Evolus saliente |
| `GET /agent/cases`, `POST /agent/cases/{id}/recommendation` | API entrante para el agente (Bearer + `Idempotency-Key`) |

## Límites conocidos

- Sin autenticación de usuarios: `X-Actor` es declarativo (cualquiera puede escribir cualquier nombre).
- Sin límite de tasa ni TLS propio; se espera un proxy delante.
- Coincidencias 1:N / N:1 (pagos agrupados) no se modelan; las comisiones tampoco.
- Una sola moneda implícita.
