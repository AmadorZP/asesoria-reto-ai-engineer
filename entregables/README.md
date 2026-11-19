# Entregables del reto

| Entregable pedido | Dónde está |
|---|---|
| Diagrama simple de arquitectura | [README, sección 1](../README.md#1-arquitectura). Flujo de decisiones del agente: [docs/flujo_de_decisiones.md](../docs/flujo_de_decisiones.md). Versión editable de todos los diagramas: [docs/diagramas.drawio](../docs/diagramas.drawio) |
| README con el detalle de la solución, flujo de ejecución, variables de entorno y tiempo invertido | [README](../README.md). Guía práctica de uso: [docs/INSTRUCTIVO.md](../docs/INSTRUCTIVO.md) |
| Código | Este repositorio: `advisor/` (agente asesor), `kb/` (base de conocimiento), `evaluator/` (agente evaluador), `tests/` |
| Exportación de las cinco métricas en JSON y CSV | [`metricas_evaluador.json`](metricas_evaluador.json) y [`metricas_evaluador.csv`](metricas_evaluador.csv) |
| Evidencia de ejecución (video) | Se entrega aparte |

## Archivos de esta carpeta

| Archivo | Contenido |
|---|---|
| `metricas_evaluador.json` | Corrida final sobre el split de test: metadatos de la corrida, definición de las cinco métricas, agregados (globales, por categoría, por perfil de riesgo, por capital, desglose de guardrails), chequeo del juez y detalle por caso con la evidencia de cada veredicto |
| `metricas_evaluador.csv` | Una fila por caso con las cinco métricas, si pasó todas, etiquetas de falla, latencia y tokens; al final, promedio y número de casos aplicables |
| `metricas_por_caso_y_metrica.csv` | Formato largo (caso × métrica), cómodo para tablas dinámicas |
| `analisis_de_fallas.md` | Análisis redactado por el agente evaluador para la corrida final |
| `analisis_de_fallas_corrida_previa.md` | Análisis de la corrida anterior sobre el mismo split, en la que fallaron dos casos; es la que motivó las últimas correcciones |

Las celdas vacías en los CSV significan que la métrica no aplica a ese caso (no equivalen a cero).

Todas las corridas, con sus respuestas crudas y trazas (`raw.jsonl`), están en [`evaluator/results/`](../evaluator/results/).
