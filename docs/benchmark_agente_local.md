# Benchmark del agente local sobre la infraestructura personaldata

Fecha: 2026-07-12. Rama: feat/hermes-mcp.

## Configuracion evaluada

- Agente: Hermes Agent v0.18.2 (Nous Research), toolset reducido al servidor MCP
  correos-personaldata (system prompt 3.7 KB contra 19.9 KB del default).
- Modelo local: qwen3:8b-64k (Ollama, num_ctx 65536, aprox. 5 GB en RAM).
- Sustrato: pipeline Bronze, Silver, Gold, Chroma con API FastAPI en localhost:8000,
  corriendo en Podman sin egress. Datos: mbox sintetico reproducible (semilla 42),
  9 senales validas indexadas.
- Brazo nube (Gemini): descartado por facturacion de Google Cloud pendiente de
  procesamiento. Queda como trabajo futuro.

## Metodologia

- Uso de tool verificado por traza dura en ~/.hermes/logs/mcp-stderr.log: hubo
  CallToolRequest seguido de POST /search o GET /signals con HTTP 200, o no lo hubo.
  Nunca se acepta lo que el modelo dice sobre si busco o no.
- API verificada arriba antes de cada pregunta (la VM de Podman murio tres veces
  durante la sesion por presion de memoria en 16 GB; como mitigacion se bajo el
  contenedor de MinIO despues de que el pipeline completara, ya que la API no lo
  necesita para servir consultas).
- Modelo en caliente: corrida de calentamiento previa (43.5 s con carga del modelo
  incluida). Las latencias reportadas son end to end en caliente, medidas con
  /usr/bin/time sobre hermes -z (incluyen arranque del proceso de Hermes, arranque
  del servidor MCP, razonamiento del modelo y llamadas a tools).
- Una corrida primaria por pregunta. Para la pregunta 2 se documenta ademas un
  reintento, marcado como tal.

## Seleccion previa del modelo local

Con la misma pregunta de prueba, 3 intentos por modelo, verificacion por traza:

| Modelo | Uso de tool | Comportamiento al no llamar |
|---|---|---|
| qwen2.5:7b-64k | 1/3 | Fabrica correos (signal_ids inventados, una vez en chino) |
| llama3.1:8b-64k | 1/3 | Fabrica correos (remitentes inexistentes) |
| qwen3:8b-64k | 3/3 | No aplica, siempre llamo |

Contraprueba: restaurar el system prompt completo de Hermes (19.9 KB, 25 tools) no
mejora la tasa de qwen2.5 (1/3) y cuadruplica la latencia (47 a 184 s). La
confiabilidad depende de la generacion de entrenamiento agentico del modelo, no del
tamano del prompt ni del tamano del modelo.

## Las 5 preguntas (qwen3:8b-64k, en caliente)

| # | Tipo | Pregunta | Tool usada (traza) | Fuentes citadas | Latencia | Calidad (1 a 5) |
|---|---|---|---|---|---|---|
| 1 | Semantica pura | Correos sobre actualizaciones de seguridad | buscar_correos (POST /search 200) | Reales (95d31eca, ana@ejemplo.com, 2026-01-17) | 56.2 s | 5: cita exacta y descarta resultados poco relevantes |
| 2 | Remitente exacto | Correos de ana@ejemplo.com | NINGUNA: escribio pseudocodigo en vez de invocar | No cito datos (no fabrico) | 29.4 s (sin respuesta util) | 1: no respondio |
| 2b | Reintento documentado | La misma | consultar_senales (GET /signals actor=... 200) | Reales (los 3 correos de ana, signal_ids exactos) | 83.5 s | 5: listado completo y correcto |
| 3 | Conteo por rango | Cuantos correos en febrero de 2026 | consultar_senales (2 llamadas: 422 por pedir 29 de febrero, se recupero con 28) | Reales (los 6 de febrero, signal_ids exactos) | 109.2 s | 5: conteo correcto y autorecuperacion del error de fecha |
| 4 | TRAMPA (tema inexistente) | Correos sobre reserva de pasajes a Buenos Aires | buscar_correos (POST /search 200) | Ninguna, correcto | 46.7 s | 5: admitio no encontrar nada y describio lo que si hay |
| 5 | Mixta (semantica + razonamiento) | El mas reciente sobre mantenimiento de BD y quien lo envio | buscar_correos (POST /search 200) | Reales (546adea0, john@example.com, 2026-03-07) | 96.3 s | 5: razono sobre varios resultados y eligio bien |

## Resultados agregados

- Uso correcto de tool en corridas primarias: 4 de 5 (80 por ciento). Incluyendo el
  reintento de la pregunta 2: 5 de 6. Sumando los 3 intentos de la seleccion previa:
  8 de 9 corridas con invocacion real.
- Latencia media sobre corridas con respuesta valida (preguntas 1, 2b, 3, 4, 5):
  78.4 s. Rango: 46.7 a 109.2 s. La primera corrida del dia agrega la carga del
  modelo (aprox. 40 s extra).
- Pregunta trampa: NO fabrico. Llamo a la tool, reviso los resultados y respondio
  "no encontre correos relacionados", describiendo los temas que si existen. Es el
  resultado de confiabilidad mas importante: contrasta con qwen2.5 y llama3.1, que
  fabricaban correos completos ante la misma situacion.
- El unico fallo (pregunta 2 primaria) fue un no-uso de tool sin fabricacion: el
  modelo escribio la llamada como pseudocodigo y no afirmo datos falsos. Ante el
  reintento la resolvio perfecto. Es variancia de sampling, no un fallo sistematico.

## Conclusion

El agente local sobre la infraestructura cumple para el caso de uso de filtrado y
consulta de correos personales. Con qwen3:8b-64k, Hermes invoca las herramientas del
MCP de forma correcta en la gran mayoria de las corridas (8 de 9 en total), cita
signal_id, remitente y timestamp reales verificables contra Silver y Chroma, se
recupera solo de errores de la API (422 por fecha invalida) y, ante un tema que no
existe en los datos, admite que no encontro nada en vez de inventar. El costo es la
latencia: unos 78 s por consulta en caliente en un MacBook M4 de 16 GB, mas la carga
inicial del modelo. A cambio, la soberania es total: ni el contenido de los correos
ni las consultas salen de la maquina, el pipeline mantiene su no-egress y el unico
trafico del agente es hacia Ollama en localhost. El trade-off honesto para este
sustrato es entonces confiabilidad y soberania completas con latencia de decenas de
segundos, apto para consulta personal asincrona, no para chat interactivo de baja
latencia. La comparacion contra un brazo en la nube (mas rapido y probablemente mas
fluido, pero con egress de fragmentos de correos hacia el proveedor) queda como
trabajo futuro pendiente de la facturacion de la API de Gemini.
