# Guion de demo — 3 minutos

Datos: `demo/bank.csv` (109 movimientos + 1 línea duplicada) y `demo/deposits.csv` (108). Sintéticos.
Resultado esperado (verificado por tests): 40 `MATCHED` (R1), 41 `SUGGESTED`, 10 `AMBIGUOUS`, 18 `UNMATCHED`.

## Antes de grabar (checklist)

- [ ] API y web arriba, base vacía (borra `e2e.db`/SQLite o usa un volumen nuevo). Escribe tu nombre en **Revisor**.
- [ ] Decide la variante y **dila en voz alta**:
  - **Variante A — endpoint AMD real:** `INFERENCE_PROVIDER=vllm` con tu instancia verificada
    ([guía](amd-vllm-deploy.md)). Solo entonces puedes decir "inferencia en AMD".
  - **Variante B — mock:** `INFERENCE_PROVIDER=mock`. El banner MOCK es visible; di "en esta demo la extracción
    es un mock; el endpoint AMD está documentado pero no lo estoy mostrando".
- [ ] Evolus: solo muestra "Pedir análisis a Evolus" si `EVOLUS_MODE=live` y verificaste una ejecución real. Con
  `mock` aparece el rótulo SIMULADO; con `disabled` el botón no existe. No lo presentes como real.
- [ ] Ten abierto `bad.csv` (ver paso 1) y el cursor en `/import`.

## Guion (tiempos orientativos)

| Tiempo | Pantalla | Qué hacer | Qué decir |
|---|---|---|---|
| 0:00–0:20 | Dashboard (vacío) | Mostrar "Aún no hay datos" | "Conciliar el banco con el sistema es manual, lento y sin rastro. ReconcileAI propone coincidencias, explica por qué y deja la decisión en una persona." |
| 0:20–0:50 | **Importar** | Subir `bad.csv` (fecha 2025-13-45) → error por línea y "nada se importó". Luego `bank.csv` y `deposits.csv` → "1 duplicada dentro del archivo". Resubir `bank.csv` → "ya había sido importado" | "La importación valida CUIT con dígito verificador, importes Decimal y fechas, es atómica e idempotente." |
| 0:50–1:15 | **Conciliar** → Dashboard | Ejecutar. Resultado: 40 vinculadas (R1), 41 sugeridas, 14 pares ambiguos | "Reglas ordenadas. Solo comprobante + importe exacto y único se vincula solo: 40 movimientos. Todo lo demás espera a una persona." |
| 1:15–1:50 | **Movimientos** → B0090 (`TRANSF REF 0002000 CLIENTE`) | Filtrar SUGGESTED, abrir B0090. Mostrar texto original, campos extraídos, "El motor aceptó una referencia verificada", `request_id`, latencia | "El modelo no tiene comprobante en el CSV: lo lee del texto. Cada dato trae su evidencia literal. El motor lo verifica: token exacto, mismo importe, ventana de fechas. Si el modelo inventa algo, se descarta." (Variante B: "esto es el mock") |
| 1:50–2:20 | **Revisión** | Ambiguos primero. B0080: dos depósitos con el mismo importe. Aprobar está deshabilitado sin nota; escribir nota y decidir | "Con evidencia idéntica no adivinamos. El caso ambiguo exige nota y al aprobar el motor revalida." |
| 2:20–2:40 | Revisión → Evolus *(solo si es real)* | "Pedir análisis a Evolus" → mostrar `executionId`, estado | "Evolus ejecuta el workflow con el modelo abierto en AMD. Su salida es informativa: no puede aprobar nada." Si no es real: **omitir este tramo**. |
| 2:40–3:00 | **AMD Inference** + **Auditoría** | Monitor (A: latencias medidas p50/p95; B: "Sin llamadas reales registradas"). Auditoría: "Cadena íntegra" | "Métricas medidas, nunca simuladas. Cada decisión queda en una cadena de hashes; 101 tests Python y 6 e2e pasan." |

## Notas para el que presenta

- Las cifras de tests son las medidas el 2026-10-13 ([progress.md](progress.md)); repite `pytest` antes de grabar y
  corrige la cifra si cambia.
- No digas "usa AMD" ni "integrado con Evolus" si no completaste los pasos de la variante A/Evolus live.
- Si algo falla en vivo, muestra el error: la UI lo reporta con alertas accesibles; es parte del diseño.
- Plan B ante cortes de red: variante B y Evolus `disabled`, y declararlo.
