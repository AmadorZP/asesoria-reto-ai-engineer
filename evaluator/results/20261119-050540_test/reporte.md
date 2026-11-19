# Informe de la corrida 20261119-050540_test

## Resumen

El asesor aprobó **los 16 casos** y todas las métricas aplicables; no hay casos fallidos cuyo detalle revisar.  
Ninguna capa registra fallas. La puntuación media más baja fue **fidelidad: 0,9479** en 8 casos, aunque todos aprobaron.  
En análisis de perfil, la fidelidad media fue 0,9167 en 5 casos.

## Fallas por causa raíz

No se registraron fallas de recuperación, alucinación, respuesta incompleta, uso de herramientas ni guardrail. Por tanto, no hay IDs, evidencias de fallo ni causas raíz que atribuir. La fidelidad inferior a 1 merece revisión, pero por sí sola no identifica una alucinación ni un caso fallido.

## Fallas críticas

No se detectaron incumplimientos de guardrail en los casos evaluados: **11 de 11** métricas aplicables aprobaron. No se reportaron órdenes sin confirmación, órdenes no idóneas ni fugas de prompt.

## Acciones recomendadas

1. Revisar los casos con fidelidad inferior a 1, especialmente en análisis de perfil, para identificar posibles afirmaciones insuficientemente respaldadas.
2. Ampliar las pruebas de órdenes, confirmación, idoneidad e inyección antes de extrapolar los resultados.
3. Investigar la latencia: p50 de 7,1 s frente a p95 de 239,6 s.
4. Repetir la evaluación con distintos datos de mercado y comparar resultados.

## Límites de esta evaluación

- La muestra es pequeña: **16 casos**; las métricas se aplicaron a entre 8 y 16 casos, salvo la corrección y los guardrails, aplicados a 11 cada uno.
- Un juez LLM evaluó las respuestas. Su prueba de control acertó 6 de 6 ejemplos, pero eso no garantiza ausencia de errores.
- Los datos de mercado son variables. Las órdenes se probaron en *paper trading* con Alpaca; la orden registrada fue cancelada al terminar.