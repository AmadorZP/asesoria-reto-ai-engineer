# Instructivo de uso de AsesorIA

Guía práctica para instalar, levantar y usar la plataforma. El detalle de diseño está en el [README](../README.md).

## 1. Requisitos

| Requisito | Para qué |
|---|---|
| Python 3.11 o superior | Backend (Microsoft Agent Framework lo exige) |
| [`uv`](https://docs.astral.sh/uv/) | Lanza el servidor MCP de Alpaca en un entorno aislado (`uvx`) |
| API key de OpenAI | Modelo del asesor, juez del evaluador y embeddings |
| Cuenta gratuita de paper trading en [Alpaca](https://alpaca.markets/) | Datos de mercado y órdenes simuladas |

En Windows, `uv` se instala con `winget install astral-sh.uv`.

## 2. Instalación

```bash
py -3.11 -m venv .venv
```

```bash
.venv\Scripts\python -m pip install -r requirements.txt
```

```bash
copy .env.example .env
```

Completa `.env` (el archivo no se sube al repositorio):

| Variable | Valor |
|---|---|
| `OPENAI_API_KEY` | Tu API key de OpenAI |
| `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | Claves de la cuenta **paper** de Alpaca |
| `SEC_USER_AGENT` | `Nombre Apellido correo@dominio.com` (la SEC lo exige para descargar de EDGAR) |
| `ADVISOR_MODEL`, `JUDGE_MODEL`, `EMBEDDING_MODEL` | Opcionales; ya traen valores por defecto |

## 3. Construir la base de conocimiento

Se hace una sola vez (o cuando cambien los documentos o las políticas). Descarga los 22 documentos públicos, genera
las 3 políticas internas, los parte en fragmentos y crea el índice en `data/qdrant`. Tarda unos 3 minutos y cuesta
menos de USD 0.10 en embeddings.

```bash
.venv\Scripts\python -m kb.ingest.run
```

Si solo cambiaste `kb/policies/politicas.yaml`, evita volver a descargar:

```bash
.venv\Scripts\python -m kb.ingest.run --skip-download
```

> El servidor debe estar **detenido** al reindexar: Qdrant en modo local admite un solo proceso a la vez.

## 4. Levantar el asesor

```bash
.venv\Scripts\python -m uvicorn advisor.api:app --port 8000
```

El arranque tarda unos 20 segundos porque conecta con el servidor MCP de Alpaca y verifica la lista blanca de
herramientas. Luego:

- Interfaz: `http://localhost:8000`
- Documentación de la API: `http://localhost:8000/docs`
- Estado: `http://localhost:8000/health`

## 5. Usar la interfaz

**Barra izquierda.** Lista las conversaciones. Cada una muestra el perfil obtenido en el chat: nivel de riesgo, si fue
*declarado* o *inferido*, y el capital. La entrada morada, **Cuenta Alpaca (paper real)**, es la sesión ligada a la
cuenta real: su capital y tenencias se leen de Alpaca.

**Qué puedes pedir**

| Tipo de consulta | Ejemplo | ¿Pide perfil? |
|---|---|---|
| Hechos de documentos | "¿Qué riesgos menciona Apple en su último reporte anual?" | No |
| Datos de mercado | "¿A cuánto cotiza MSFT y cómo viene su tendencia?" | No |
| Políticas y educación | "¿Qué límites tiene un perfil moderado?" | No |
| Oportunidades y asignaciones | "¿Qué oportunidades ves entre MSFT, NVDA y un ETF de bonos?" | Sí |
| Compras | "Compra 5 acciones de MSFT." | Sí |

**Cómo dar tu perfil.** Puedes declararlo ("tengo un perfil moderado y USD 10,000") o describirte ("tengo USD 100,000,
mi horizonte es de 7 años y toleraría una caída de hasta 20 %"). En el segundo caso el sistema lo clasifica:

| Pérdida que toleras | Perfil |
|---|---|
| Hasta 10 % | Conservador |
| Hasta 25 % | Moderado |
| Más de 25 % | Agresivo |

Si tu horizonte es menor a 3 años, el perfil baja un nivel.

**Citas.** Los chips `S1`, `S2`… dentro de la respuesta abren la fuente: documento, sección, página, extracto y enlace.

**Trazabilidad.** Bajo cada respuesta, "Trazabilidad" muestra cada herramienta invocada con su entrada, salida, origen
(tool local o MCP de Alpaca) y duración, además de advertencias, decisiones de confirmación y cambios de perfil.

**Comprar**

1. Pide la compra. Si la orden está dentro de lo recomendado para tu perfil, aparece la tarjeta de confirmación.
2. Si excede lo recomendado, recibes una primera advertencia con el monto recomendado y el exceso. Responde si
   quieres continuar.
3. Si continúas, recibes una segunda advertencia con los riesgos y una pérdida ilustrativa. Responde de nuevo.
4. Si continúas, aparece la tarjeta de confirmación con las advertencias visibles. **Confirmar compra** la envía a
   Alpaca; **Rechazar** la descarta.
5. Si el monto supera tu dinero disponible, la orden se bloquea sin excepción.

Escribir un mensaje nuevo mientras hay una tarjeta pendiente equivale a rechazarla.

**Horario de mercado.** La bolsa de EE. UU. opera de 9:30 a 16:00 hora de Nueva York (misma hora que Lima entre
noviembre y marzo). Fuera de ese horario la orden queda *aceptada y en cola* hasta la apertura.

**Universo operable.** AAPL, MSFT, NVDA, AGG, BND, IVV y VOO. Solo compras a mercado.

## 6. Usar la API directamente

Conversar (si omites `session_id` se crea una conversación nueva y la respuesta trae su id):

```bash
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d "{\"message\": \"Tengo un perfil moderado y USD 100,000. Compra 2 acciones de MSFT.\"}"
```

Confirmar o rechazar una orden pendiente (`approval_id` viene en `pending_approvals` de la respuesta anterior):

```bash
curl -X POST http://localhost:8000/approve -H "Content-Type: application/json" -d "{\"session_id\": \"<id>\", \"approval_id\": \"<id>\", \"approved\": true}"
```

Otros recursos:

| Recurso | Uso |
|---|---|
| `GET /sessions` | Conversaciones con su perfil |
| `GET /sessions/{id}` | Transcripción de una conversación |
| `"session_id": "cuenta-alpaca"` en `/chat` | Sesión ligada a la cuenta real |
| `POST /admin/reset` | Borra las conversaciones (solo desarrollo y evaluación) |

## 7. Ejecutar el agente evaluador

Con el asesor levantado:

```bash
.venv\Scripts\python -m evaluator.run --split test
```

| Opción | Efecto |
|---|---|
| `--split validation` / `test` / `all` | Qué casos ejecutar |
| `--only A1,D3` | Solo esos casos |
| `--rescore evaluator/results/<corrida>/raw.jsonl` | Volver a puntuar sin llamar al asesor |
| `--keep-orders` | No cancelar las órdenes paper que colocó la corrida |
| `--no-report` | Omitir el análisis de fallas del agente |

Cada corrida deja en `evaluator/results/<fecha>_<split>/`: `results.json`, `results.csv` (una fila por caso),
`metrics_long.csv` (caso × métrica), `reporte.md` (análisis de fallas) y `raw.jsonl` (respuestas crudas con traza).
La corrida final está copiada en [`entregables/`](../entregables/).

> El evaluador borra las conversaciones del servidor antes de cada caso y, al terminar, cancela en Alpaca las órdenes
> que él mismo colocó.

Para regenerar el set de casos tras editarlo:

```bash
.venv\Scripts\python -m evaluator.dataset.build_dataset
```

## 8. Pruebas deterministas

No llaman a ningún modelo ni a Alpaca:

```bash
.venv\Scripts\python -m pytest -q
```

## 9. Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `No se encontro uvx` al arrancar | Instala `uv` o define `UVX_PATH` en `.env` con la ruta a `uvx.exe` |
| El venv falla o usa otro Python | Crea el entorno con `py -3.11`, no con un `python` de MSYS2 o Git Bash |
| Error de bloqueo de Qdrant al reindexar | Detén el servidor antes de `kb.ingest.run` |
| `Falta SEC_USER_AGENT` en la descarga | Completa esa variable en `.env` |
| La orden queda en `accepted` o `pending_new` | El mercado está cerrado; se ejecuta en la apertura |
| La barra lateral aparece vacía | Las conversaciones viven en memoria y se pierden al reiniciar el servidor |
| Errores `server/discover` en la consola al arrancar | Ruido del servidor MCP al negociar el protocolo; no afecta |
| Caracteres raros en la consola de Windows | Ejecuta con `set PYTHONUTF8=1` |
