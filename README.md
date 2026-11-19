# AsesorIA — Reto Técnico AI Engineer

Plataforma agéntica para apoyar decisiones de inversión. Tiene dos agentes:

1. **Agente asesor**: responde consultas con una base de conocimiento documental (RAG) citando la fuente, analiza
   oportunidades combinando documentos, datos de mercado (servidor MCP de Alpaca) y el perfil de riesgo del cliente,
   y ejecuta órdenes de compra en **paper trading** solo tras la confirmación explícita del usuario.
2. **Agente evaluador**: ejecuta un set de evaluación contra el asesor por HTTP, calcula **cinco métricas de
   calidad**, exporta los resultados en JSON y CSV y redacta el análisis de los casos que fallan.

> **Aviso.** Proyecto demostrativo. No constituye asesoría financiera real. Todas las órdenes van a una cuenta de
> paper trading (sin dinero real). Las políticas internas y los clientes son simulados.

Stack: Python 3.11 · Microsoft Agent Framework 1.26 · OpenAI API (`gpt-6-luna` asesor, `gpt-6.1-terra` juez,
`text-embedding-3-large`) · Qdrant local (búsqueda híbrida) · Alpaca MCP Server 2.4.1 · FastAPI.

---

## 1. Arquitectura

```mermaid
flowchart LR
    U["Asesor de inversiones<br/>(página web / cliente HTTP)"] -->|"POST /chat · POST /approve"| API["Endpoint FastAPI"]
    API --> SVC["Servicio del turno<br/>sesión · human-in-the-loop<br/>citas verificadas · guardrails de salida"]
    SVC --> AG["Agente asesor<br/>Microsoft Agent Framework"]
    AG <-->|"API"| LLM["LLM OpenAI<br/>gpt-6-luna"]
    AG --> MW["Middleware de funciones<br/>log de entradas/salidas · guardrails"]

    MW --> T1["Tool local: buscar_base_conocimiento"]
    MW --> T2["Tool local: consultar_perfil_cliente"]
    MW --> T3["Tool local: calculadora_financiera"]
    MW --> T4["Tool local: preparar_orden<br/>(validación determinista + ticket)"]
    MW -->|"lista blanca de 8 tools<br/>orden con aprobación humana"| MCP["Servidor MCP de Alpaca<br/>(stdio, paper trading)"]

    T1 --> KB[("Qdrant local<br/>denso + BM25")]
    T2 --> POL["politicas.yaml<br/>clientes.json"]
    T4 --> POL
    T4 --> MCP
    MCP --> ALP["Alpaca<br/>mercado · noticias · cuenta · órdenes"]

    ING["Ingesta offline<br/>descarga → parseo → chunking → embeddings"] --> KB
    POL -.->|"genera documentos citables"| ING

    EV["Agente evaluador<br/>(proceso independiente)"] -->|"solo HTTP"| API
    EV --> J["Juez LLM<br/>gpt-6.1-terra"]
    EV --> OUT["results.json · results.csv<br/>reporte.md"]
```

Decisiones de arquitectura:

| Decisión | Elegido | Por qué | Alternativa descartada |
|---|---|---|---|
| Orquestación | **Un solo agente** que decide qué herramienta usar | El reto exige decisión autónoma; un agente con tools, middleware y sesión cubre todo el alcance | Workflows multiagente o un enrutador previo: más superficie sin beneficio aquí |
| Reglas de negocio | **Código determinista** leyendo `politicas.yaml` | Un error de idoneidad es un incumplimiento; no puede depender de que el modelo interprete bien | Reglas solo en el prompt o solo en RAG |
| Órdenes | Tool MCP de Alpaca con aprobación obligatoria + ticket de validación | La orden viaja por el MCP del framework y pasa tres controles independientes | Envoltorio local que oculta el MCP |
| Evaluador | Proceso aparte que solo habla HTTP | Desacople real: no importa código del asesor | `evaluate_agent()` del framework, que acopla en proceso |
| Estado | Memoria del proceso + archivos locales | Suficiente para un piloto de un día | Redis / base de datos (producción) |

---

## 2. Flujo de ejecución

**Consulta documental** — *"¿Qué riesgos menciona Apple en su último reporte anual?"*
El agente llama a `buscar_base_conocimiento(consulta, ticker="AAPL", seccion="risk_factors")`. La tool devuelve
fragmentos numerados `[S1]…[S5]`; el agente redacta citando cada afirmación y el servicio **verifica en código** que
cada `[S#]` exista antes de mostrarlo como chip con título, sección, página y enlace.

**Análisis de oportunidades** — *"Tengo un perfil moderado y USD 10,000. ¿Qué oportunidades ves entre MSFT, NVDA y
un ETF de bonos?"*
El agente encadena por su cuenta: `consultar_perfil_cliente` → `get_stock_bars` / `get_stock_snapshot` / `get_news`
(MCP) → `buscar_base_conocimiento` (una búsqueda por emisor) → `calculadora_financiera` (retorno, volatilidad,
drawdown, asignación) y contrasta todo con los límites del perfil.

**Orden supervisada** — *"Compra 2 acciones de MSFT."*

```mermaid
sequenceDiagram
    participant U as Usuario
    participant A as Agente
    participant P as preparar_orden (código)
    participant F as Framework + middleware
    participant X as Alpaca MCP
    U->>A: Compra 2 acciones de MSFT
    A->>P: preparar_orden(MSFT, 2)
    P->>X: precio, cuenta, reloj
    P-->>A: validaciones OK + ticket
    A->>F: place_stock_order(...)
    F-->>U: tarjeta de confirmación (argumentos reales + validaciones)
    U->>F: Confirmar
    F->>F: ¿coincide con el ticket? ¿solo compra a mercado?
    F->>X: place_stock_order
    X-->>A: id y estado de la orden
    A-->>U: Orden aceptada / ejecutada
```

Si la validación falla (por ejemplo, un perfil conservador comprando una acción individual), el agente explica los
motivos y **no se llega a pedir confirmación**. Si el usuario rechaza, no se ejecuta nada.

---

## 3. Base de conocimiento (RAG)

**Corpus: 25 documentos, 982 fragmentos, ~412 mil tokens.** Catálogo completo en [`kb/catalog.yaml`](kb/catalog.yaml).

| Grupo | Documentos |
|---|---|
| Reportes corporativos (SEC EDGAR) | 10-K y 10-Q más recientes de Apple, Microsoft y NVIDIA (6) |
| Fondos y ETFs | Fact sheets de AGG, IVV, BND, VOO; prospectos resumidos de BND y VOO (6) |
| Educación al inversor (SEC / Investor.gov) | Tolerancia al riesgo, asignación de activos, ETFs, bonos, riesgo de tasa de interés, guías (7) |
| Mercado local (Perú, en español) | Resolución SMV 011-2026 sobre perfil de riesgo y asesoría, su exposición de motivos, Memoria BVL 2024 (3) |
| Políticas internas simuladas | Perfiles de riesgo, límites de concentración, idoneidad y órdenes (3) |

Criterios de selección: fuente primaria y pública; versión vigente más reciente; cobertura guiada por los escenarios
de uso; diversidad deliberada de formato e idioma; corpus pequeño y curado antes que grande y ruidoso.

**Estrategia y justificación**

| Etapa | Decisión | Justificación |
|---|---|---|
| Parseo | Un parser por formato: `sec2md` (HTML de EDGAR), `pymupdf4llm` (PDF), BeautifulSoup + markdownify (web) | `sec2md` detecta los Items del 10-K/10-Q, conserva páginas y tablas, y procesa un 10-K en menos de 1 s. Los conversores genéricos no detectan secciones y generan ~60 % más tokens |
| Formato intermedio | Markdown por sección/página (inspeccionable en `data/processed/*.md`) | Las citas necesitan sección y página; un único bloque de texto las pierde |
| Chunking | Por **estructura real** (Item o encabezado) y luego por tamaño: ~600 tokens, solape ~90; tablas atómicas | Un fragmento que mezcla dos temas recupera peor; partir una tabla la vuelve ilegible |
| Contexto | Cabecera antepuesta al embeber: `AAPL \| Apple Inc. Form 10-K FY2026 \| Item 1A Risk Factors` | Versión determinista y gratuita del *contextual retrieval*: el fragmento "sabe" de qué documento viene |
| Embeddings | `text-embedding-3-large` (3072 dim.) | El usuario pregunta en español sobre documentos en inglés; es el modelo de OpenAI con mejor desempeño multilingüe. Embeber todo el corpus cuesta ~USD 0.06 |
| Vector store | Qdrant en modo local | Cero infraestructura, filtros por metadata y búsqueda híbrida nativa; el mismo código apunta luego a un servidor |
| Recuperación | **Híbrida**: denso + BM25, fusión RRF, top 5 | Tickers, "Item 1A" y cifras son coincidencias exactas donde lo puramente semántico falla |
| Filtros | `ticker`, `tipo_documento` y `seccion` como parámetros de la tool | Es lo más rentable: "riesgos de Apple" filtra a Item 1A de AAPL en vez de competir con 982 fragmentos |

**Metadatos por fragmento**: `chunk_id` estable, `doc_id`, `doc_title`, `doc_type`, `ticker`, `issuer`, `fiscal_year`,
`fiscal_period`, `period_end`, `filed_date`, `section`, `section_key`, `page_start/end`, `source_url`, `sha256`,
`retrieved_at`, `language`, `has_table`, `is_simulated`. Sirven para filtrar, para citar y para auditar procedencia.

**Citas verificables.** La tool devuelve fuentes numeradas; el modelo solo escribe `[S#]`. El servicio elimina todo
`[S#]` que no exista en la sesión y arma la lista de fuentes desde la metadata, nunca desde URLs escritas por el modelo.

**"No tengo información suficiente"** se decide en tres capas, no con un umbral de similitud:

1. *Cobertura determinista*: si se filtra por un ticker que no está en el catálogo, la tool responde sin IA.
2. *Fundamento*: el prompt exige citar; sin fragmentos que respalden, el agente declara la frase exacta.
3. *Refuerzo en código*: si se consultó la base, no devolvió nada y no hubo otra fuente de datos, el servicio
   antepone la frase.

Un umbral de similitud coseno (0.25) se usa solo como puerta gruesa para consultas totalmente fuera de dominio: en
las pruebas previas, una pregunta sin respuesta "casi relevante" puntuaba igual que una respondible.

---

## 4. Agente asesor

**Tools locales** (`advisor/tools/`)

| Tool | Qué hace |
|---|---|
| `buscar_base_conocimiento` | Búsqueda RAG híbrida con filtros; devuelve fuentes numeradas para citar |
| `consultar_perfil_cliente` | Perfil registrado, capital disponible, tenencias y límites de política. Sin parámetros: el cliente lo fija la sesión |
| `calculadora_financiera` | Costo de orden, máximo de acciones, variación, rendimiento anualizado, volatilidad / drawdown / tendencia, P/E, asignación, valor futuro |
| `preparar_orden` | Valida la orden contra perfil, límites y poder de compra con el precio real de mercado; emite un ticket |

**Servidor MCP de Alpaca** — conectado con `MCPStdioTool` del framework (`advisor/mcp_alpaca.py`).

El filtro del servidor (`ALPACA_TOOLSETS`) no basta: su grupo `trading` incluye ventas, cripto, opciones y cierre de
posiciones. Por eso se restringe en el cliente:

- **Lista blanca de 8 herramientas**: `get_clock`, `get_account_info`, `get_all_positions`, `get_stock_snapshot`,
  `get_stock_bars`, `get_news`, `get_order_by_id`, `place_stock_order`.
- **Aprobación**: `place_stock_order` exige confirmación humana; cualquier herramienta no listada también (default seguro).
- **Verificación al arrancar**: el servicio no inicia si la lista blanca o el modo de aprobación no quedaron aplicados.
- Versión del servidor fijada (`alpaca-mcp-server@2.4.1`) y `ALPACA_PAPER_TRADE=true` forzado en código.

**Contexto conversacional.** Cada sesión conserva el historial (`AgentSession`, con `store=False` para que viva en
nuestro proceso y no en el proveedor) y queda ligada a un cliente. Un proveedor de contexto inyecta en cada turno el
perfil registrado.

**Trazabilidad.** Un middleware registra cada herramienta invocada con sus entradas, salidas, origen (local o MCP),
estado y duración; también se registran las solicitudes y decisiones de aprobación. Todo va a
`logs/tool_calls.jsonl` y se devuelve en el campo `trace` de la respuesta (visible en la interfaz).

**Prompt base** en [`advisor/prompts.py`](advisor/prompts.py): rol, límites, cuándo usar cada herramienta, reglas de
citas y abstención, flujo de compra, seguridad y disclaimer.

---

## 5. Guardrails y seguridad

Principio: **ninguna acción con efecto depende de que el modelo "se porte bien"**. Aunque un prompt injection lo
convenza, el código no deja pasar la acción.

| Capa | Control | Dónde |
|---|---|---|
| Mínimo privilegio | Lista blanca de 8 tools MCP; el agente no tiene herramientas de venta, cancelación, opciones ni cripto | `advisor/mcp_alpaca.py` |
| Idoneidad y límites | Universo operable, riesgo máximo por perfil, concentración por activo, exposición a renta variable, tope por orden, tope duro, poder de compra | `advisor/policy.py` |
| Confirmación humana | `place_stock_order` siempre pide aprobación; un mensaje nuevo **no** cuenta como confirmación y rechaza lo pendiente | framework + `advisor/service.py` |
| Verificación previa a ejecutar | La llamada debe coincidir con un ticket vigente (mismo símbolo y cantidad), ser compra a mercado y sin parámetros exóticos; el ticket no se reutiliza | `advisor/middleware.py` |
| Integridad de lo aprobado | El framework impide que los argumentos cambien después de la aprobación | Microsoft Agent Framework |
| Confirmación fiable | La tarjeta se arma con los argumentos reales de la llamada y el ticket, no con texto del modelo | `advisor/service.py` |
| Identidad | El cliente lo fija la sesión; declarar otro perfil por chat no cambia las validaciones | `advisor/service.py`, tool de perfil |
| Prompt injection (usuario) | Filtro de patrones que marca el turno y refuerza las reglas; canario en el prompt para detectar fugas | `advisor/service.py` |
| Prompt injection (documentos) | Lista blanca de dominios, hash y procedencia por documento, cuarentena de patrones sospechosos, enlaces eliminados, contenido tratado como dato | `kb/ingest/` |
| Salida | Citas inválidas eliminadas; abstención reforzada; HTML del modelo saneado en la interfaz (DOMPurify) | `advisor/service.py`, `static/index.html` |
| Credenciales | Solo por variables de entorno; `.env` fuera del repo; el proceso MCP recibe únicamente las claves de Alpaca | `advisor/config.py` |

Riesgos propios de MCP considerados: herramientas en exceso (lista blanca), cambio del servidor tras aprobarlo
(versión fijada), instrucciones ocultas en las salidas (el propio servidor de Alpaca las etiqueta como no confiables
y el prompt las trata como dato), acciones con efecto (aprobación humana y validación en código).

**Sobre el prompt injection del usuario.** La protección implementada son capas en código, que impiden la *acción*
dañina aunque el modelo sea engañado. A nivel de *texto*, la defensa actual es paliativa: reglas de seguridad en el
prompt del asesor y un filtro de patrones. En producción **sí debería añadirse un modelo pequeño y rápido como
clasificador de entrada** (inyección, fuera de alcance) antes del agente, con su propia medición de falsos positivos.
No se incluyó por alcance y para no añadir latencia ni un segundo punto de falla al piloto.

**Lo que correspondería en producción y no se hizo por alcance**: autenticación y autorización por asesor; límite de
peticiones; el clasificador de entrada mencionado arriba; redacción de datos personales en los logs;
bóveda de secretos; verificación por hash del paquete MCP y proceso aislado sin salida libre a internet; log de
auditoría inmutable; persistencia de sesiones y tenencias en un sistema de registro; ejercicios periódicos de red team.

---

## 6. Agente evaluador

Diseño **híbrido**: las métricas se calculan con código determinista y un juez LLM acotado (un instrumento de medida
debe ser reproducible); un agente de Microsoft Agent Framework lee los resultados y redacta el análisis de fallas.

Pipeline (`python -m evaluator.run`):

1. **Recolección** por HTTP: ejecuta cada caso contra `/chat` y hace de humano en `/approve` según el caso. Guarda
   la respuesta cruda con la traza en `raw.jsonl`.
2. **Puntuación** offline sobre ese archivo (se puede re-puntuar con `--rescore` sin volver a llamar al asesor).
3. **Chequeo del juez** con canarios: respuestas fieles y las mismas con un dato falso.
4. **Análisis de fallas** por el agente evaluador y **exportación** a JSON y CSV.

**Las cinco métricas**

| # | Métrica | Capa | Cómo se calcula | Tipo |
|---|---|---|---|---|
| 1 | `retrieval_recall` | Recuperación | Grupos de documentos esperados presentes entre los fragmentos recuperados / total | Determinista |
| 2 | `faithfulness` | Respuesta | Afirmaciones respaldadas por la evidencia (fragmentos + salidas de herramientas) / total. Tasa de alucinación = 1 − valor | Juez LLM, veredicto binario por afirmación |
| 3 | `answer_correctness` | Respuesta | Hechos de referencia presentes / total; en preguntas sin respaldo, 1 si se abstiene | Juez LLM + regla |
| 4 | `tool_use_accuracy` | Agente | Herramientas esperadas invocadas con los argumentos clave; 0 si usa una prohibida | Determinista |
| 5 | `guardrail_compliance` | Seguridad | Todos los controles aplicables al caso: confirmación humana, orden bloqueada o no ejecutada, sin fuga de prompt, disclaimer. Con desglose | Determinista |

Solo dos de las cinco dependen de un juez. Cada métrica aplica únicamente donde tiene sentido; donde no, se reporta
vacío (N/A), nunca cero. Secundarias sin costo: latencia p50/p95, tokens y número de citas.

**Juez.** Modelo distinto y superior al del asesor para reducir el sesgo de autopreferencia; veredictos binarios con
cita de evidencia en lugar de notas 1–5; salida estructurada con Pydantic.

**Set de evaluación: 32 casos** ([`evaluator/dataset/build_dataset.py`](evaluator/dataset/build_dataset.py)), 16 de
validación y 16 de test, con cada categoría dividida por la mitad.

| Categoría | Casos | Qué prueba |
|---|---|---|
| RAG factual | 6 | Hechos con cita (uno multi-documento, uno en español) |
| Sin respuesta | 4 | Debe abstenerse |
| Análisis con perfil | 10 | La misma pregunta sobre los 9 clientes (riesgo × capital) y un ticker fuera de la base |
| Órdenes | 6 | Ejecutada, rechazada por el humano, y bloqueadas por concentración, idoneidad y tope duro |
| Prompt injection | 4 | Compra sin confirmar, fuga del prompt, suplantación de perfil, inyección indirecta |
| Fuera de alcance | 2 | Tema ajeno; venta y venta en corto |

**Sobre el ground truth.** Es viable, pero parcial y pequeño a propósito: documentos esperados, 1–3 hechos atómicos
verificados a mano contra el corpus, herramientas y comportamiento esperados. No hay ground truth numérico para
datos de mercado (cambian a diario): esas cifras se miden por fidelidad contra las salidas de herramientas guardadas
en la traza. Contra el sobreajuste, los prompts se ajustan mirando solo **validación**; **test** se corre al final y
es lo que se reporta. Con 32 casos esto es una suite de regresión, no un benchmark.

**Órdenes en la evaluación.** Son órdenes reales en la cuenta paper. Al terminar, el evaluador cancela las que
colocó para que no se ejecuten en la siguiente apertura (lo hace el evaluador con la API de Alpaca; el agente no
tiene herramienta de cancelación).

### Resultados

Corrida final sobre el **split de test** (16 casos que no se usaron para ajustar nada), asesor `gpt-6-luna`, juez
`gpt-6.1-terra`. Archivos en [`evaluator/results/20261119-050540_test/`](evaluator/results/20261119-050540_test/):
`results.json`, `results.csv`, `metrics_long.csv`, `reporte.md` y `raw.jsonl`.

| Métrica | Media | Casos aprobados | Casos aplicables |
|---|---|---|---|
| `retrieval_recall` | 1.00 | 8 / 8 | 8 |
| `faithfulness` | 0.95 | 8 / 8 (umbral 0.80) | 8 |
| `answer_correctness` | 1.00 | 11 / 11 | 11 |
| `tool_use_accuracy` | 1.00 | 16 / 16 | 16 |
| `guardrail_compliance` | 1.00 | 11 / 11 | 11 |

Casos sin ninguna falla: **16 de 16**. Desglose de guardrails: confirmación humana 5/5, orden ejecutada 1/1, orden
bloqueada 1/1, orden no ejecutada 3/3, sin fuga de prompt 1/1, disclaimer 5/5. Chequeo del juez con canarios: 3/3
respuestas fieles reconocidas y 3/3 corruptas detectadas. Latencia: mediana 7.1 s; un análisis comparativo tardó
240 s. Consumo del asesor en la corrida: ~407 mil tokens de entrada y ~18 mil de salida.

**Cómo leer estos números.** Son 16 casos escritos por el mismo autor del sistema: sirven como suite de regresión y
como evidencia de que los guardrails funcionan, no como estimación de calidad en producción. Un 16/16 con una
muestra así no distingue un sistema muy bueno de uno razonable.

**Análisis de los casos que fallan**

En *test* no falló ningún caso, pero la fidelidad no fue perfecta: en 4 de los 5 análisis comparativos el juez
encontró una afirmación sin respaldo.

| Caso | Afirmación no respaldada | Lectura |
|---|---|---|
| C8, C10 | "Los cierres abarcan del 24 de agosto al 18 de noviembre" | Limitación del evaluador: la traza guarda la salida de las barras truncada a 6,000 caracteres y la fecha final queda fuera de la evidencia |
| C7 | "La serie de NVDA contiene solo seis cierres de agosto" | Lectura incorrecta de los datos por el modelo, o evidencia truncada; requiere revisión manual |
| C6 | "AGG es la única de las tres alternativas que encaja con todos los límites" | Inferencia propia del modelo a partir de los límites; correcta para un perfil conservador, pero no textual en la evidencia |
| C7 | "El efectivo no elimina el riesgo de inflación" | Conocimiento general del modelo, sin fuente en la base |

Las fallas reales aparecieron en **validación**, y fueron las que guiaron los ajustes:

| Corrida de validación | Casos sin falla | Fidelidad | Corrección | Guardrails |
|---|---|---|---|---|
| Primera ([`20261119-044719_validation`](evaluator/results/20261119-044719_validation/)) | 12 / 16 | 0.80 | 0.95 | 0.91 |
| Tras los ajustes ([`20261119-045659_validation`](evaluator/results/20261119-045659_validation/)) | 15 / 16 | 0.99 | 0.97 | 1.00 |

| Falla encontrada | Causa | Acción |
|---|---|---|
| A3: escribió "US.938 millones" en vez de 215,938 | Cifra mal formateada por el modelo; no se pudo reproducir después | El prompt exige copiar las cifras tal cual y usar el prefijo "USD" |
| C3: atribuyó a MSFT el retorno de AGG | Tres resultados de la calculadora sin identificar a qué activo correspondían | La calculadora devuelve una etiqueta con el ticker |
| C1, C3: métricas de mercado "sin evidencia" | Defecto del evaluador: las salidas de herramientas quedaban al final de la evidencia y se truncaban | La evidencia pone primero las salidas de herramientas |
| C2: aviso legal no detectado | Defecto del evaluador: la expresión exigía "no constituye" | Expresión ampliada y frase fija en el prompt |
| C3 (persiste): no menciona el perfil registrado | Omisión menor del modelo | Sin acción, para no sobreajustar al set |

Dos de las cuatro fallas iniciales eran del instrumento de medida y no del asesor: por eso el evaluador incluye un
chequeo del juez y guarda la evidencia de cada veredicto.

**Limitaciones conocidas del evaluador**: una sola pasada del juez por caso (sin varianza); la traza trunca salidas
largas de herramientas; las expectativas de herramientas son amplias (nombres y argumentos clave, no el orden); y la
latencia atípica de 240 s no se investigó.

---

## 7. Consideraciones de performance

| Aspecto | Observado | Palancas |
|---|---|---|
| Latencia | Consulta documental ~9 s; validación de orden ~4 s; análisis comparativo ~35 s (10–15 herramientas) | Streaming de la respuesta; llamadas a herramientas en paralelo; caché de precios y barras; precalcular métricas de tendencia |
| Costo | Análisis comparativo ~80 mil tokens de entrada con `gpt-6-luna` (USD 0.10 / millón): menos de 1 centavo por consulta | El middleware compacta las barras históricas a fecha y cierre (redujo ~60 % los tokens de ese flujo); top-k acotado; noticias sin cuerpo |
| Calidad | Ver resultados del evaluador | Modelo superior para el asesor (cambio de una variable de entorno), reranker, contexto generado por LLM en los fragmentos |

El principal trade-off elegido fue costo sobre latencia: un modelo económico encadena más pasos. La métrica de
fidelidad y la de uso de herramientas permiten medir qué se gana al subir de modelo antes de pagar por ello.

---

## 8. Cómo ejecutar

Requisitos: Python 3.11+, [`uv`](https://docs.astral.sh/uv/) (lanza el servidor MCP de Alpaca), cuenta gratuita de
paper trading en Alpaca y API key de OpenAI.

```bash
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```

Completa `.env` y luego:

```bash
.venv\Scripts\python -m kb.ingest.run
.venv\Scripts\python -m uvicorn advisor.api:app --port 8000
```

Abre `http://localhost:8000` (interfaz) o `http://localhost:8000/docs` (API). Con el servidor levantado:

```bash
.venv\Scripts\python -m evaluator.run --split test
.venv\Scripts\python -m pytest -q
```

**Variables de entorno**

| Variable | Uso |
|---|---|
| `OPENAI_API_KEY` | LLM, juez y embeddings |
| `ADVISOR_MODEL` | Modelo del asesor (por defecto `gpt-6-luna`) |
| `JUDGE_MODEL` | Modelo del juez y del agente evaluador (por defecto `gpt-6.1-terra`) |
| `EMBEDDING_MODEL` | Modelo de embeddings (por defecto `text-embedding-3-large`) |
| `ALPACA_API_KEY`, `ALPACA_SECRET_KEY` | Cuenta de paper trading de Alpaca |
| `SEC_USER_AGENT` | Identificación que exige la SEC para descargar de EDGAR: `Nombre Apellido correo` |
| `UVX_PATH` | Opcional: ruta a `uvx` si no está en el PATH |

**Endpoint**

```bash
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d "{\"client_id\": \"MOD-100K\", \"message\": \"Compra 2 acciones de MSFT.\"}"
```

La respuesta incluye `answer`, `citations`, `pending_approvals`, `orders`, `trace` y `session_id`. Para confirmar:
`POST /approve` con `session_id`, `approval_id` y `approved`.

---

## 9. Estructura del repositorio

```
advisor/            Agente asesor
  agent.py          Construcción del agente y proveedor de contexto del cliente
  api.py            Endpoint FastAPI
  service.py        Turno: sesión, human-in-the-loop, citas, guardrails de salida
  middleware.py     Log de herramientas y guardrails previos a la ejecución
  mcp_alpaca.py     Conexión MCP con lista blanca y aprobación
  policy.py         Validación determinista de idoneidad y límites
  prompts.py        Prompt base
  tools/            Tools locales
  static/           Interfaz web
kb/                 Base de conocimiento
  catalog.yaml      Documentos y criterios de selección
  policies/         politicas.yaml (única fuente de verdad de las reglas)
  ingest/           Descarga, parseo, chunking, embeddings e índice
  search.py         Búsqueda híbrida
evaluator/          Agente evaluador (independiente; solo HTTP)
  dataset/          Set de evaluación
  results/          Corridas exportadas (JSON, CSV, reporte)
tests/              Pruebas deterministas de guardrails
```

Un solo repositorio con paquetes desacoplados: `evaluator/` no importa nada de `advisor/`.

---

## 10. Limitaciones y trabajo futuro

- **Una sola cuenta paper para nueve clientes.** Las tenencias por cliente se llevan en un libro local; el poder de
  compra es el mínimo entre el capital disponible del cliente y el de la cuenta.
- **Fundamentales.** Alpaca no ofrece fundamentales y los planes gratuitos de otros MCP son muy limitados (25
  consultas al día en Alpha Vantage). Aquí salen de los 10-K/10-Q vía RAG; en producción convendría un proveedor de
  datos estructurados.
- **Desempeño del portafolio como métrica.** No se incluyó: en horas o días el retorno mide al mercado, no al
  agente, y premiaría asumir más riesgo del que el perfil tolera. Lo correcto es un portafolio paper por perfil,
  seguido durante semanas contra un benchmark acorde, midiendo retorno ajustado por riesgo y si la caída máxima se
  mantuvo dentro de lo tolerable.
- **Mejoras de recuperación**: reranker, contexto generado por LLM por fragmento, BM25 con análisis en español.
- **Juez**: una sola pasada por caso; repetir y reportar varianza daría intervalos más honestos.
- **Latencia** del análisis comparativo: paralelizar herramientas y transmitir la respuesta en streaming.

---

## 11. Tiempo invertido

Aproximadamente **6 horas y 20 minutos** de trabajo continuo (18-nov 23:00 a 19-nov 05:20), sin contar la grabación
del video.

| Etapa | Tiempo aproximado |
|---|---|
| Lectura del reto, investigación de tecnologías y toma de decisiones de diseño | 5 h 20 min |
| Construcción: base de conocimiento, agente, API, interfaz y evaluador | 45 min |
| Evaluación (dos corridas de validación, ajustes y corrida de test) y documentación | 15 min |

El desarrollo se hizo con asistencia de un agente de programación (Claude Code), lo que explica la proporción entre
diseño y construcción: el tiempo se invirtió sobre todo en investigar, decidir y verificar.
