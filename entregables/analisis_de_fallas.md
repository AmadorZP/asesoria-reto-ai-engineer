# Informe: corrida 20261119-063229_test

## Resumen

El asesor aprobó los **16 de 16 casos**; no hubo métricas fallidas.  
Todas las métricas tuvieron una tasa de aprobación del 100 % en los casos donde aplicaban.  
La puntuación media más baja fue **fidelidad: 0,9792** en 8 casos, aunque todos aprobaron. No se identifica una capa con fallas.

## Fallas por causa raíz

No hay casos fallidos que agrupar por recuperación, alucinación, respuesta incompleta, uso de herramientas o guardrail. La lista de casos fallidos está vacía, por lo que no había detalles de fallos que consultar ni causas que atribuir.

## Fallas críticas

**No se registraron incumplimientos de guardrail** en los 11 casos donde se evaluó esa métrica. No se reportaron órdenes sin confirmación, órdenes no idóneas ni fugas de prompt.

## Acciones recomendadas

1. Revisar el detalle de las puntuaciones de fidelidad inferiores a 1, especialmente la del segmento de capital 100.000, sin asumir que constituyen fallas.
2. Ampliar los casos de órdenes, idoneidad e inyección para reforzar la cobertura de guardrails.
3. Repetir la evaluación con más perfiles, capitales y condiciones de mercado.

## Límites de esta evaluación

- La muestra es pequeña: **16 casos**, con distintas métricas aplicables a subconjuntos.
- La evaluación utiliza un **juez LLM**; sus resultados pueden contener errores de criterio.
- Los datos de mercado son variables, por lo que los resultados pueden cambiar al repetir la corrida. Las órdenes se realizaron en *paper trading* y la orden registrada se canceló al finalizar.