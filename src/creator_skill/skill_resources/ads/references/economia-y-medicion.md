# Economía y medición para decidir

Aplicación operativa de `techo-cpa-contribucion`, `costo-chat-tasa-cierre`, `promocion-contribucion`, `recompra-por-cohortes` y `costos-whatsapp-por-producto`. Consulta [sus fuentes y límites](criterios-curados.md). Las identidades contables siguientes no predicen ventas ni demuestran efecto causal.

## Definir las unidades antes de calcular

**Pedido, venta, comprador y cliente nuevo son unidades diferentes.** Para CAC, el denominador son clientes nuevos adquiridos; para costo por pedido, pedidos. Una conversación con tres compras no equivale a tres conversaciones convertidas. Si el negocio no puede distinguir nuevos y repetidos, informa costo por venta y deja CAC pendiente.

**Ingreso neto** debe tener una definición consistente: cobrado, menos descuentos y devoluciones; aclara tratamiento de impuestos y envío. **Costos variables** incluyen los costos que corresponden a esas ventas: producto o prestación, comisiones, logística, devoluciones y atención variable según el modelo. No vuelvas a descontar un concepto que ya se restó del ingreso.

**Contribución antes de publicidad = ingreso neto − costos variables.** Tras restar publicidad queda contribución después de publicidad; todavía puede faltar pagar costos fijos e impuestos. No la llames beneficio neto. Si se incluyen costos de adquisición adicionales, etiquétalos y evita contarlos dos veces.

## Techo económico de adquisición

Para un cliente nuevo y un horizonte explícito:

```text
contribución previa = ingreso neto por cliente − costos variables por cliente
techo de CAC publicitario = contribución previa − reserva requerida − adquisición no publicitaria
techo publicitario por lead = techo de CAC publicitario × tasa lead→cliente − atención por lead
```

La reserva representa lo que el negocio quiere conservar para estructura y resultado. El techo sin reserva es un equilibrio parcial, no una meta deseable. Si la reserva o los costos eliminan el margen disponible, más volumen no arregla la economía por cliente bajo esos supuestos. El costo de atender leads se descuenta aquí solo si no está incluido ya en los otros costos.

El techo no es el CPA que Meta conseguirá ni el presupuesto recomendado. Para planificar, usa escenarios de costo y tasa de cierre respaldados por historial comparable; cuando no exista, declara incertidumbre y limita la prueba a una pérdida asumible. Un escenario favorable no financia gastos hasta que se cobra.

### Ejemplo ficticio: ecommerce

Pedido inicial medio de un nuevo cliente: ingreso neto S/200; costos variables S/120; reserva S/20; adquisición adicional S/5. Contribución S/80 y techo publicitario por nuevo cliente S/55. Si el gasto observado por cliente es S/70, un ROAS de 2,86 no satisface esa reserva. No debe llamarse rentable por superar un ROAS genérico.

### Ejemplo ficticio: venta consultiva

Ingreso neto inicial S/1.000; entrega variable S/400; reserva S/200; adquisición adicional por nuevo cliente S/50. Techo publicitario por cliente S/350. Con cierre de 10% y atención S/5 por lead, techo publicitario por lead S/30. Si el cierre cae a 5%, queda S/12,50. Cambiar el filtro puede alterar tasa, volumen y tiempo de atención; recalcula todos, no solo CPL.

Calcula estos escenarios con [plan_economics.py](../scripts/plan_economics.py):

```sh
python scripts/plan_economics.py assets/examples/economia-servicio.json
```

Los campos se expresan por **nuevo cliente en la primera compra** y en una misma moneda ISO de tres letras. Usa `basis: "historical"` para historial comparable o `basis: "hypothesis"` para un supuesto. `lead_to_customer_rate` es fracción de 0 a 1, no porcentaje entero; si se incluye, indica también `lead_handling_cost` y evita duplicarlo en otros costos. El script muestra un techo condicional; no elige presupuesto ni acepta LTV futuro como ingreso de primera compra.

## Un embudo comercial comparable

Registra una fila por oportunidad o cliente con identificador interno, fecha de entrada, fuente/campaña/pieza cuando se conoce, primer contacto útil, estado, motivo de descarte, fecha de compra, importe cobrado y costos. Para un informe compartido utiliza agregados o identificadores no personales. No hace falta recoger datos sensibles para medir una caída comercial.

| Etapa | Definición que debe acordar el negocio | Métrica y denominador |
|---|---|---|
| Conversación | Persona/contacto único del periodo, con regla para reingresos | Gasto / conversaciones únicas |
| Atendido | Recibió respuesta útil, no solo acuse automático | Atendidos / conversaciones |
| Calificado | Cumple condiciones observables relevantes para la oferta | Calificados / atendidos y costo/calificado |
| Propuesta o cita | Oferta enviada o cita agendada; no fusionarlas si ambas existen | Avance desde calificados |
| Asistencia | Cita efectivamente atendida | Asistencias / citas vencidas |
| Compra | Pago confirmado; aclarar adelanto, saldo y devolución | Compradores / cohorte de origen |
| Nuevo cliente | Primera compra identificada | Costos de adquisición / nuevos clientes |

Las tasas por etapa solo se multiplican cuando corresponden al mismo grupo y a un recorrido compatible. No multipliques tasas de meses, productos o poblaciones distintos. Si hay rutas paralelas o reingresos, reconstruye el recorrido real.

Para chats utiliza la calculadora existente:

```sh
python scripts/ads_metrics.py assets/examples/cohorte-chat.json
```

El JSON exige `same_cohort: true`. Ese campo es una declaración del operador, no una auditoría de los datos. Con cero ventas el CPA es indefinido; no es cero. `cohort_mature: false` permite describir lo observado, pero impide tratar cierres pendientes como fracaso definitivo.

## Atribución, conciliación e incrementalidad

Mantén tres lecturas separadas: resultados que atribuye la plataforma, ventas cobradas del negocio y efecto incremental estimado mediante una comparación adecuada. No sumes automáticamente ventas atribuidas por varias plataformas; pueden reclamar la misma compra.

Reconcilia una muestra de pedidos o leads: identificador, fecha, moneda, importe, estado y devolución. Busca duplicados y eventos que se disparan antes del pago. Documenta cobertura y pérdidas de señal. Una implementación de medición debe probar correspondencia de eventos y compras reales; instalar una API no acredita ventas adicionales.

**Cohorte de entrada:** sirve para cierre y CAC; conserva oportunidad abierta hasta el plazo pertinente. **Periodo de caja:** sirve para saber qué se cobró y pagó en esas fechas. Pueden mostrar resultados diferentes sin que uno esté mal. No dividas ventas de clientes antiguos entre gasto de captación reciente y lo llames CAC.

Un experimento con asignación comparable puede investigar causalidad; una evolución antes/después ofrece una señal observacional. Cambios de temporada, stock, precio, canal, vendedor o mezcla de clientes pueden explicar el resultado. Para diseñar pruebas consulta [experimentación](experimentacion-y-operacion.md).

## Promociones y recompra

Para una promoción, compara contribución total con y sin incentivo bajo escenarios explícitos: precio, unidades, costo variable, envío, devoluciones, publicidad y compras que podrían adelantarse. Distingue aumentar ticket de aumentar dinero disponible. Un paquete que agrega productos de bajo margen puede empeorar la operación aunque suba la facturación.

Para recompra, agrupa clientes por primera compra y observa contribución acumulada a horizontes iguales. Una cohorte reciente no ha tenido el mismo tiempo que una antigua. Mantén el CAC inicial; calcula por separado costo de retención y contribución de compras posteriores. No justifiques una pérdida inmediata con una recurrencia aún no observada ni con ingresos futuros sin costos.

El tiempo de recuperación importa: si se espera recuperar adquisición en varios meses, modela caja y abandono. No impongas una razón LTV/CAC universal ni extrapoles indefinidamente una tasa de retención inicial.

## Escala y resultado marginal

Calcula el cambio de gasto y el cambio de contribución en ventanas comparables. La contribución promedio histórica puede ocultar que el volumen adicional es más caro o difícil de atender. Esa diferencia sigue siendo observacional si cambian otros factores; no la vendas como causalidad exacta.

Antes de aumentar exposición, anota inventario o cupos disponibles, plazos de cobro/pago, tiempo de atención y señales de reversión. La decisión de escalar necesita economía, demanda y capacidad; una sola cifra no acredita las tres.
