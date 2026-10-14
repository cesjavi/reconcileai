# Pitch, guion de video y diapositivas

Texto escrito para jurados del hackathon (negocio + técnica). Reemplaza los marcadores `[ ]` solo con cosas que
hayas verificado.

## Pitch (30 segundos)

Cada empresa que cobra por transferencia concilia a mano su extracto contra el sistema: horas de trabajo, errores y
ningún rastro de por qué se vinculó cada pago. **ReconcileAI** concilia con reglas deterministas, usa un modelo
abierto solo para leer referencias escondidas en el texto libre del banco, verifica todo lo que el modelo propone y
deja la decisión final en una persona, con una auditoría que no se puede reescribir sin que se note.

## Problema y usuario

Usuario: analista de tesorería/cuentas a cobrar de una pyme o un estudio contable argentino. Dolor: cobros por
transferencia con comprobante o CUIT en texto libre, importes repetidos, pagos que llegan días después. Riesgo
real: una conciliación errónea cierra mal un período. Por eso el sistema prioriza **no equivocarse en silencio**.

## Qué lo diferencia

1. **La IA no decide.** Propone; el motor exige evidencia literal, importe exacto y ventana de fechas.
2. **Ambigüedad explícita.** Nunca elige entre candidatos iguales; los muestra primero y pide justificación.
3. **Honestidad operativa.** El monitor de inferencia nunca muestra datos simulados como reales; el mock se rotula.
4. **Auditable.** Cadena de hashes, decisiones inmutables, `request_id` por llamada de inferencia.

## Valor de negocio (sin cifras inventadas)

Qué se midió: sobre el dataset sintético, 40 de 109 movimientos (36,7 %) se vinculan solos con evidencia exacta y
41 más llegan con candidato único para aprobar con un clic; los 10 ambiguos y los 18 sin candidato quedan para
revisión/gestión manual. Es un dataset **diseñado**, no una tasa de acierto en producción: no se puede extrapolar.
Ahorro de tiempo real: `[medir con usuarios — no medido]`.

## Estado técnico a declarar

Real y probado: motor, API, UI, auditoría, 101 tests Python + 6 e2e. No verificado: ejecución sobre GPU AMD y sobre
un workspace de Evolus (faltan endpoint/credenciales al 2026-10-13). Si completaste esos pasos, actualiza esta sección
con las evidencias de [submission.md](submission.md).

## Guion de video (≈ 3 min, para la entrega)

| # | Tiempo | Imagen | Locución |
|---|---|---|---|
| 1 | 0:00–0:20 | Equipo/dolor: planilla de conciliación manual | problema y usuario |
| 2 | 0:20–0:50 | Importación con error por línea y archivo repetido | confianza en datos: validación, atomicidad, idempotencia |
| 3 | 0:50–1:15 | Conciliación: 40 R1 + dashboard | reglas ordenadas; solo lo exacto se vincula solo |
| 4 | 1:15–1:50 | Detalle B0090 con evidencia | la IA lee, el motor verifica; `[AMD real / mock — decirlo]` |
| 5 | 1:50–2:20 | Cola de revisión, caso ambiguo con nota | humano en el bucle |
| 6 | 2:20–2:40 | `[Evolus real, solo si verificado]` | workflow + AI Tool, salida informativa |
| 7 | 2:40–3:00 | Monitor + auditoría + tests | métricas medidas, cadena íntegra, cierre y llamado |

Detalle de clics: [demo-script.md](demo-script.md).

## Diapositivas (7)

1. **Título y promesa** — "Conciliación bancaria con IA que no decide sola". Logo, equipo, track Evolus Business Agents on AMD.
2. **Problema** — proceso manual, errores silenciosos, sin trazabilidad; quién lo sufre.
3. **Solución** — flujo: importar → reglas R1–R4 → revisión humana → auditoría (diagrama de [architecture.md](architecture.md)).
4. **Dónde entra la IA** — extracción de referencias con evidencia literal; verificación determinista; qué pasa si alucina (test).
5. **AMD + Evolus** — arquitectura: vLLM sobre ROCm `[evidencia real o "pendiente"]`, workflow y AI Tool de Evolus
   `[evidencia real o "pendiente"]`; tabla real/simulado/pendiente de [progress.md](progress.md).
6. **Demo y resultados medidos** — capturas; 101 tests Python + 6 e2e; 40/41/10/18 sobre el dataset sintético; latencias reales solo si hay vLLM.
7. **Negocio y siguiente paso** — usuarios objetivo, modelo de uso, roadmap (auth real, 1:N, multimoneda, PDFs vía Document Extractor).
