# Desplegar vLLM en AMD Developer Cloud (guía, no ejecutada)

> **Estado:** esta guía se redactó a partir de documentación pública (fuentes abajo). **Nadie la ejecutó todavía en
> hardware AMD** y no existe un endpoint asignado a este proyecto. No se inventa ninguna GPU, IP ni URL: usa los
> valores de tu propia instancia. Cada paso indica de dónde sale y qué debes comprobar tú.

## Fuentes consultadas (2026-10-13)

| Fuente | Qué aporta |
|---|---|
| [AMD – How to Get Started on the AMD Developer Cloud](https://www.amd.com/en/developer/resources/technical-articles/2025/how-to-get-started-on-the-amd-developer-cloud-.html) | imágenes ROCm vanilla y *Quick Start* con vLLM, acceso por SSH, contenedor `rocm` |
| [lablab – Host your first LLM on AMD Developer Cloud](https://lablab.ai/ai-tutorials/amd-developer-cloud-host-llm-vllm) | imagen "vLLM Quick Start", comandos de arranque, puerto 8000, nota sobre firewall y sin autenticación por defecto |
| [vLLM – Docker deployment](https://docs.vllm.ai/en/latest/deployment/docker/) | imagen `vllm/vllm-openai-rocm`, flags de `docker run` para ROCm |
| [lablab – página del evento](https://lablab.ai/ai-hackathons/amd-developer-hackathon-act-iii) | requisito: modelo abierto servido con tu propio endpoint vLLM en AMD Developer Cloud |

Las búsquedas encontraron además guías de AMD (ROCm AI Developer Hub) con imágenes `rocm/vllm-dev`; los tags y
versiones cambian rápido. **Verifica el tag exacto en la documentación vigente antes de copiar.**

## 0. Prerrequisitos (los pones tú)

- Cuenta en el AMD AI Developer Program y créditos/activación de AMD Developer Cloud (según AMD y lablab, la
  activación es por un código de crédito en tu cuenta; no está en este repositorio).
- Clave SSH cargada en la consola (el tutorial indica que las instancias exigen autenticación por clave).
- Tu token de Hugging Face si el modelo lo requiere (`HF_TOKEN`).

## 1. Crear la instancia

1. En la consola de AMD Developer Cloud crea una instancia GPU con la imagen **"vLLM Quick Start"** (el tutorial de
   lablab la llama "vLLM (recommended)"; incluye un contenedor Docker llamado `rocm` con vLLM y ROCm).
2. Espera el aprovisionamiento (el tutorial indica 2–4 minutos).
3. `ssh root@<IP-DE-TU-INSTANCIA>` (la IP te la da la consola).

## 2. Verificar compatibilidad ROCm y memoria de GPU

Comprobaciones con herramientas estándar de ROCm (confirma que existen en tu imagen):

```bash
rocm-smi                      # modelo de GPU, memoria total/usada
rocminfo | grep -i "gfx"      # arquitectura (p. ej. gfx942 corresponde a MI300X)
docker exec -it rocm bash -lc 'python -c "import torch; print(torch.__version__, torch.version.hip, torch.cuda.is_available())"'
docker exec -it rocm bash -lc 'python -c "import vllm; print(vllm.__version__)"'
```
Debes ver `torch.version.hip` no vacío, `is_available() == True` y la versión de vLLM instalada.
Guarda esa salida: es evidencia de que corres sobre ROCm y se puede citar en la entrega.

**Memoria** (aritmética propia, no una cifra de AMD): los pesos ocupan ≈ `parámetros × bytes por parámetro`
(16 bits ⇒ 2 bytes). Un modelo de 1,5 B ≈ 3 GB; de 7 B ≈ 14 GB; de 70 B ≈ 140 GB. A eso suma la caché KV, que
crece con `--max-model-len` y la concurrencia. El tutorial de lablab afirma 192 GB de VRAM en MI300X; **comprueba
la cifra real con `rocm-smi` en tu instancia**. Limita el uso con `--gpu-memory-utilization` y `--max-model-len`.

## 3. Elegir el modelo

- Requisito del hackathon: **modelo abierto**. Revisa su licencia y que figure en la lista de modelos soportados de
  vLLM para ROCm en la versión instalada.
- El tutorial de lablab usa `Qwen/Qwen2.5-1.5B-Instruct` (carga rápida). Para extracción de identificadores con JSON
  estricto conviene un modelo *instruct* de ~7 B; **no se ha evaluado ningún modelo para esta tarea**. Mide con el
  monitor de la app (campo "descartadas por validación" y salidas inválidas) antes de elegir.

## 4. Arrancar vLLM con clave de API

Entra al contenedor y arranca (adaptado del tutorial de lablab; añade clave de API y límites):

```bash
docker exec -it rocm /bin/bash
export VLLM_API_KEY="$(openssl rand -hex 24)"; echo "$VLLM_API_KEY"   # guárdala; irá en INFERENCE_API_KEY
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-1.5B-Instruct \
  --host 0.0.0.0 --port 8000 \
  --dtype float16 \
  --max-model-len 4096 \
  --api-key "$VLLM_API_KEY" \
  > /tmp/vllm.log 2>&1 &
tail -f /tmp/vllm.log      # esperar: "Application startup complete."
```
- El tutorial usa `python -m vllm.entrypoints.openai.api_server`; versiones nuevas prefieren `vllm serve <modelo> …`.
  Usa el que exista en tu versión (`vllm --help`).
- `--api-key`, `--max-model-len`, `--dtype` son opciones del servidor OpenAI de vLLM; **la página de despliegue
  Docker de vLLM no menciona `--api-key`**, así que confírmala con `vllm serve --help` o `python -m
  vllm.entrypoints.openai.api_server --help` en tu contenedor.
- Alternativa documentada por vLLM (imagen oficial ROCm, en lugar de la Quick Start):
  ```bash
  docker run --rm --group-add=video --cap-add=SYS_PTRACE --security-opt seccomp=unconfined \
    --device /dev/kfd --device /dev/dri -v ~/.cache/huggingface:/root/.cache/huggingface \
    --env "HF_TOKEN=$HF_TOKEN" -p 8000:8000 --ipc=host \
    vllm/vllm-openai-rocm:<tag> --model Qwen/Qwen2.5-1.5B-Instruct --api-key "$VLLM_API_KEY"
  ```
  (flags tomados de la página de vLLM; `<tag>` y `--api-key` los verificas tú.)

## 5. Seguridad de red

El tutorial advierte que vLLM **no exige autenticación por defecto** y que el puerto 8000 queda público porque
Docker evita las reglas de UFW al publicar puertos. Por eso:
- arranca siempre con `--api-key`;
- restringe el acceso al puerto 8000 desde el firewall de la consola a la IP de tu app (confirma en tu consola qué
  controles ofrece; no asumas que UFW basta);
- no uses `--allowed-origins '["*"]'` (solo hace falta para chats desde navegador; ReconcileAI llama desde el servidor);
- apaga la instancia al terminar para no gastar créditos.

## 6. Probar el endpoint

```bash
curl -s http://<IP-DE-TU-INSTANCIA>:8000/v1/models -H "Authorization: Bearer $VLLM_API_KEY"
curl -s http://<IP-DE-TU-INSTANCIA>:8000/v1/chat/completions \
  -H "Authorization: Bearer $VLLM_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"Qwen/Qwen2.5-1.5B-Instruct","messages":[{"role":"user","content":"Responde OK"}],"max_tokens":8}'
```
`/v1/models` debe listar exactamente el id que pondrás en `INFERENCE_MODEL`.

## 7. Conectar ReconcileAI

```bash
INFERENCE_PROVIDER=vllm
INFERENCE_BASE_URL=http://<IP-DE-TU-INSTANCIA>:8000/v1
INFERENCE_API_KEY=<la clave de arriba>
INFERENCE_MODEL=Qwen/Qwen2.5-1.5B-Instruct
INFERENCE_HARDWARE_LABEL="AMD Developer Cloud / ROCm"   # texto tuyo; la app no lo verifica
```
Si el servidor rechaza `response_format` (HTTP 400), pon `INFERENCE_JSON_MODE=false`: el cliente igual valida el
JSON con Pydantic y descarta lo que no esté respaldado por el texto.

Prueba de integración real (no se ejecuta por defecto):
```bash
INFERENCE_INTEGRATION=1 INFERENCE_PROVIDER=vllm INFERENCE_BASE_URL=… INFERENCE_API_KEY=… INFERENCE_MODEL=… \
  python -m pytest services/inference -k real_endpoint -s
```
Después carga el dataset, ejecuta la conciliación y abre **AMD Inference** en la UI: las métricas aparecen solo
cuando hay llamadas no-mock, con latencias medidas por el cliente.

## 8. Qué guardar como evidencia para la entrega

Salida de `rocm-smi`, de la comprobación de PyTorch/HIP y de la versión de vLLM; la respuesta de `/v1/models`; una
captura del monitor con llamadas `vLLM` reales; el `request_id` de alguna llamada y su fila en `/inference/logs`.
Sin estas evidencias, la entrega debe decir que el uso de AMD está **pendiente de verificación**.
