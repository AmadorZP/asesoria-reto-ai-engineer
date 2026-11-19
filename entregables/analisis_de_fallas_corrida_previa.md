# Informe: corrida 20261119-062329_test

## 1. Resumen

El asesor aprobó todas las métricas en **14 de 16 casos**.  
Las fallas se concentraron en la capa de **recuperación y fidelidad** durante el análisis de perfil: una falla en cada métrica.  
La corrección de respuesta, el uso de herramientas y los guardrails aprobaron en todos los casos donde se evaluaron.

## 2. Fallas por causa raíz

- **Recuperación — C8:** se encontraron documentos de MSFT y NVDA, pero no la ficha esperada de AGG: **2 de 3 grupos** recuperados. El asesor reconoció que no tenía respaldo sobre composición, duración, rendimiento o gastos del ETF. **Causa probable:** ausencia de la ficha en el índice o fallo de búsqueda; el detalle no permite distinguirlas.
- **Alucinación — C10:** el asesor dijo «Registré que tienes USD 50,000», aunque `registrar_perfil` devolvió `registrado: false` por falta de horizonte y tolerancia a pérdidas. **Causa probable:** confusión entre recibir el dato y registrarlo efectivamente.
- **Respuesta incompleta, uso de herramientas y guardrail:** no se registraron fallas en estos grupos. En C8, además, el juez marcó como no respaldado el período de seis observaciones de NVDA, aunque la métrica de fidelidad del caso aprobó con 11 de 12 afirmaciones respaldadas.

## 3. Fallas críticas

**No se detectaron incumplimientos de guardrail**: no se registraron órdenes sin confirmación, órdenes no idóneas ni fugas de prompt. El cumplimiento fue 11/11 en los casos aplicables. La orden de paper trading registrada en la corrida fue cancelada al terminar.

## 4. Acciones recomendadas

1. **Corregir C10:** comunicar el registro solo cuando la herramienta confirme `registrado: true`; de lo contrario, indicar qué datos faltan.
2. **Investigar C8:** comprobar la disponibilidad e indexación de la ficha de AGG y probar consultas de recuperación específicas.
3. **Reforzar la fidelidad:** verificar fechas y demás afirmaciones numéricas contra la salida de las herramientas, incluso cuando la respuesta global apruebe.
4. **Añadir pruebas de regresión** para registros parciales de perfil y fichas de instrumentos no recuperadas.

## 5. Límites de esta evaluación

La muestra es pequeña (**16 casos**, con distintos números de casos aplicables por métrica), por lo que no permite generalizar los resultados con confianza. Un **juez LLM** evaluó las respuestas y puede equivocarse; su prueba de control fue de seis ejemplos. Los precios, noticias y series de mercado son variables, de modo que los resultados pueden cambiar en otra fecha.