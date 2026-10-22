# Decisiones de Ads con evidencia

Estos procedimientos son una propuesta editorial. Consulta los criterios y sus fragmentos; las cifras de un creador no constituyen umbrales universales. Una transcripción revisada como texto puede seguir teniendo errores de audio. Las anotaciones de una muestra solo validan ese alcance.

## Diagnosticar conversaciones baratas sin ventas

Usa `costo-chat-tasa-cierre`, `tres-frentes` y `destino-calidad-friccion` de [criterios-curados.md](criterios-curados.md).

Pide o identifica la misma cohorte: periodo, moneda, gasto, conversaciones únicas, atendidas, calificadas, con venta pagada, ingreso neto y costos variables. Separa cierres aún pendientes. Si los denominadores no son comparables, corrige el registro antes de elegir un anuncio.

Calcula costo por conversación, tasa conversación→venta y costo por venta. Revisa contribución después de publicidad; no confundirla con beneficio neto. El script `python scripts/ads_metrics.py cohorte.json` verifica ceros, negativos y comparabilidad. Ejemplo de entrada (datos ficticios):

```json
{"same_cohort":true,"cohort_mature":true,"currency":"PEN","period":"semana de ejemplo","spend":300,"conversations":100,"sales":3,"net_revenue":600,"variable_costs":360}
```

Localiza la caída: anuncio→conversación, conversación→atención, atención→calificación o calificación→venta. Contrasta tiempos de respuesta, preguntas recurrentes, stock y motivos de no compra. Diseña una prueba sobre la etapa señalada. Define responsable, gasto máximo tolerable según el negocio, ventana que permita observar cierres y resultado comercial. Para datos inmaduros, establece cuándo volver a medir en vez de declarar un ganador.

## Decidir si escalar

Usa `capacidad-escalado`, `techo-cpa-contribucion` y `estructura-como-hipotesis`.

Comprueba contribución, atribución, estabilidad de los resultados, devoluciones, caja, stock y capacidad de atención. Si faltan datos críticos, entrega el próximo experimento o medición concreta. No completes esos huecos con una receta de siete días ni con porcentajes de aumento tomados de un video.

Si los datos justifican una prueba, documenta el cambio propuesto, su hipótesis, una pérdida máxima que el negocio acepte y señales de reversión. Compara ventanas equivalentes y considera el retraso de las ventas. Mantén un registro para distinguir cambios de presupuesto, creatividad, oferta y atención. Proponer esta prueba no autoriza cambiar una cuenta.

## Crear anuncios que enseñen algo

Usa `argumento-formato` y `registro-creativo`.

Recoge una objeción concreta de clientes. Redacta el argumento y la prueba que lo respalda antes de elegir el formato. Para aislar el argumento, conserva formato, oferta y destino comparables; para explorar varios factores a la vez, declara que el aprendizaje no identifica una causa única.

La ficha de cada pieza debe permitir reproducirla: público y situación, argumento, demostración, formato, llamada a la acción, variable cambiada, métrica comercial y límite de gasto. CTR ayuda a diagnosticar; no apagar una pieza rentable solo por estar bajo 1% o 3%. Una o dos ventas tampoco acreditan estabilidad.

## Evaluar promociones y recompra

Usa `promocion-contribucion` y `recompra-por-cohortes`.

Recalcula contribución con el precio promocional, costos variables, devoluciones, envío y operación. Luego resta publicidad. Más facturación puede producir menos contribución. Para justificar mayor adquisición por recompra, usa cohortes de nuevos clientes con compras pagadas observadas, contribución neta y plazo de recuperación. No reduzcas el CAC inicial dividiendo gasto entre pedidos repetidos ni asumas que una categoría recurrente garantiza retención.

## Resolver consejos contradictorios o cifras dudosas

Reconstruye qué estaba resolviendo cada creador: tipo de negocio, etapa, evento, presupuesto, ventana y evidencia. Presenta el desacuerdo como hipótesis condicionadas cuando esos contextos no coincidan. Si dos modelos discrepan sobre una cifra o sigla, no elijas automáticamente el modelo más grande. Busca audio, subtítulo, pizarra o fuente oficial apropiada y registra lo que sigue incierto.

Cita autor, URL, segundos, segmento y alcance revisado. No uses un fragmento excluido, un hash obsoleto o una frase promocional como prueba de resultados. Las búsquedas con `--reviewed-only` priorizan selección editorial; no significan que cada segundo del video haya sido comprobado.

## Experimentos y funciones actuales

Formula hipótesis, variable modificada, resultado observado y posibles explicaciones alternativas. Meta describe estos componentes en su [guía para elegir el enfoque de medición](https://www.facebookblueprint.com/student/page/671612) y distingue [A/B, conversion lift y brand lift](https://www.facebookblueprint.com/student/path/219763-ab-test-conversion-brand-lift-course). Se consultaron las descripciones públicas el 2026-10-05; no se accedió al curso completo ni a una cuenta publicitaria.

Una comparación antes/después no demuestra causalidad por sí sola. Verifica nombres, disponibilidad y requisitos actuales en documentación oficial cuando la respuesta dependa de una función de Meta. Si no se puede verificar, entrega el principio y deja esa instrucción específica pendiente.

La respuesta final debe dejar clara la decisión propuesta, los datos usados o faltantes, la acción verificable, qué resultado la sostendría o refutaría y las referencias. Ajusta su extensión a la solicitud.
