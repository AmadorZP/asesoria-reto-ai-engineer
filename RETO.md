# AsesorIA - Reto Técnico AI Engineer

## Detalle del reto
En Credicorp Capital, distintas áreas de Inversiones y soporte operativo manejan información clave distribuida en documentos, reportes y procesos internos, lo que dificulta el acceso oportuno al conocimiento y genera dependencia de personas específicas.

El equipo de GenAI & Innovación ha impulsado la iniciativa AsesorIA, una plataforma agéntica que busca habilitar capacidades de consulta inteligente, automatización y soporte interno, utilizando una base cognitiva y semántica común. Además de consultar documentación interna, los agentes pueden consultar información externa relacionada al mundo de las inversiones, por ejemplo, APIs públicas o información disponible en la web.

Como parte de la evolución de AsesorIA desde experimentación hacia una etapa de piloto, se requiere validar que los equipos técnicos puedan construir y operar componentes clave de la plataforma, con foco en ejecución práctica, alineamiento estratégico y nivel intermedio operativo.

El foco del rol es la construcción de agentes de IA y de una base semántica para apoyar decisiones de inversión. El objetivo es diseñar e implementar:

1. Un **agente asesor** que responda consultas de inversión fundamentadas en una base de conocimiento documental (RAG), analice oportunidades combinando dicha base con datos de mercado obtenidos mediante un servidor MCP público y ejecute órdenes simuladas (paper trading) solo tras confirmación explícita del usuario.
2. Un **agente evaluador** que ejecute un set de evaluación contra el agente asesor, calcule cinco métricas de calidad y exporte sus resultados.

### Escenario de uso
Un asesor de inversiones conversa con el agente:

- "¿Qué riesgos menciona Apple en su último reporte anual?" → respuesta vía RAG con citas de la fuente.
- "Tengo un perfil moderado y USD 10,000. ¿Qué oportunidades ves entre MSFT, NVDA y un ETF de bonos?" → el agente consulta la base de conocimiento y datos de mercado vía MCP, y propone un análisis justificado.
- "Compra 5 acciones de MSFT." → el agente valida perfil y poder de compra, muestra un resumen de la orden, solicita confirmación y luego la ejecuta en paper trading.

## Alcance obligatorio
- Backend desarrollado en Python.
- Uso de Microsoft Agent Framework.
- Uso de un LLM mediante API, localmente o con modelos open source en la nube.
- Implementación de RAG con un vector store sobre documentos financieros públicos.
- Integración con al menos un servidor MCP público (no se debe construir un servidor MCP propio).
- Herramientas del agente:
  - Búsqueda en la base de conocimiento (RAG) con citas de la fuente.
  - Análisis de oportunidades: precio, tendencia, noticias y fundamentales del activo, contrastados con el perfil de riesgo del cliente.
  - Ejecución de órdenes de compra en modo paper trading, con confirmación humana obligatoria (human-in-the-loop).
- Tools locales implementadas en el backend y disponibles para el agente:
  - Calculadora financiera para operaciones y estimaciones usadas en el análisis.
  - Consulta del perfil de riesgo e idoneidad del cliente.
  - Búsqueda RAG local sobre la base documental.
- Agente evaluador independiente del flujo de asesoría, que ejecute el set de evaluación y exporte las métricas descritas en la sección de evaluación.
- Contexto conversacional básico (memoria de la sesión y perfil del cliente).
- Prompt base claro, que incluya el rol, los límites del agente y el disclaimer de que no constituye asesoría financiera real.
- Endpoint simple para interactuar con el agente.

## Requisito clave de IA
El agente asesor debe decidir de forma autónoma cuándo usar la base de conocimiento, las tools locales o consultar datos de mercado vía MCP y cuándo proponer una acción, manteniendo trazabilidad de cada decisión. El agente evaluador debe poder ejecutarse sobre casos de prueba sin intervenir en la asesoría al usuario.

Implementacion esperada:
- Ingesta, chunking y embeddings de documentos financieros, con la estrategia justificada.
- Conexión al servidor MCP mediante las herramientas MCP de Microsoft Agent Framework.
- Restricción de las herramientas MCP expuestas al agente (por ejemplo, solo datos de mercado, noticias, cuenta y órdenes de compra).
- Aprobación explícita del usuario antes de cualquier orden.
- Respuesta "no tengo información suficiente" cuando la base de conocimiento no respalde la respuesta.
- Log de las herramientas invocadas, sus entradas y salidas.
- Implementación de las tools locales (function tools).
- Agente evaluador conectado al set de evaluación, con resultados exportables en JSON y CSV.

## Servidores MCP públicos sugeridos
| Servidor | Uso en el reto | Requisito |
|---|---|---|
| [Alpaca MCP Server](https://github.com/alpacahq/alpaca-mcp-server) (oficial) | Datos de mercado, noticias, cuenta, posiciones y órdenes. Paper trading activo por defecto (`ALPACA_PAPER_TRADE=true`). Permite restringir herramientas con `ALPACA_TOOLSETS` | Cuenta gratuita de paper trading |
| [Alpha Vantage MCP](https://mcp.alphavantage.co/) (oficial) | Fundamentales, indicadores técnicos, noticias con sentimiento, datos macro | API key gratuita |
| [Financial Datasets MCP](https://github.com/financial-datasets/mcp-server) | Estados financieros, precios y noticias de empresas de EE. UU. | API key |

Obligatorio: Alpaca, para la ejecución de órdenes en paper trading. Opcional: un segundo MCP para enriquecer el análisis.

## Fuentes sugeridas para la base de conocimiento
Documentos públicos. Seleccionar entre 20 y 50 documentos.

- **Reportes corporativos:** reportes anuales 10-K y trimestrales 10-Q de [SEC EDGAR](https://www.sec.gov/edgar/search/) para las empresas analizadas.
- **Fondos y ETFs:** fact sheets y prospectos publicados por los emisores, como iShares o Vanguard.
- **Mercado local:** prospectos de fondos mutuos en la [SMV](https://www.smv.gob.pe/), y memorias anuales y hechos de importancia en la [BVL](https://www.bvl.com.pe/).
- **Educación al inversor y perfiles de riesgo:** guías de [Investor.gov (SEC)](https://www.investor.gov/).
- **Políticas internas simuladas:** política de perfiles de riesgo (conservador, moderado, agresivo), límites de concentración por activo y reglas de idoneidad (suitability). Las redacta el candidato.

## Entregables
- Diagrama simple de arquitectura (agente asesor, agente evaluador, tools locales, RAG, MCP, LLM y endpoint).
- README con el detalle de la solución, el flujo de ejecución, las variables de entorno y el tiempo invertido.
- Código (link del repositorio en GitHub).
- Exportación de las cinco métricas calculadas por el agente evaluador en JSON y CSV.
- Evidencia de ejecución (demo en video o link de prueba) que muestre los tres escenarios de uso, incluida una orden ejecutada en paper trading.

## Se valorara especialmente
- Diseño lógico del agente: orquestación entre RAG, herramientas MCP y confirmación humana.
- Correcta construcción y uso de la base semántica (chunking, embeddings y metadatos justificados).
- Evaluación de calidad: métricas de recuperación y de respuesta, más análisis de los casos que fallan.
- Guardrails: validación del perfil de riesgo, límites por orden, respuesta "no sé", disclaimers y mitigación de prompt injection.
- Seguridad: manejo de credenciales por variables de entorno y restricción de herramientas MCP.
- Capacidad de justificar decisiones técnicas y trade-offs.
- Alineamiento de la solución con un escenario corporativo real.
- Claridad para explicar el funcionamiento end-to-end.
- Consideraciones de performance a nivel conceptual, como latencia, costo y calidad de respuesta.
 