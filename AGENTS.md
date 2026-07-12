# Guia para agentes

Este entorno expone los correos personales del usuario a traves del
servidor MCP `correos-personaldata`, que ofrece dos herramientas:

- `buscar_correos(query, top_k)`: busqueda semantica por significado
  sobre el contenido de los correos. Usala para preguntas por tema
  ("que correos hablan de X", "recibi algun aviso de Y").
- `consultar_senales(actor, from_ts, to_ts, limit)`: listado con
  filtros exactos por remitente y rango de fechas. Usala para
  preguntas por remitente, fecha o conteo.

Reglas:

1. Cuando el usuario pregunte por sus correos, INVOCA estas
   herramientas mediante una llamada de funcion real (tool call)
   antes de responder. Nunca escribas la llamada como texto o como
   bloque de codigo, nunca digas que buscaste sin haber invocado la
   herramienta, no respondas de memoria y no sugieras que el usuario
   busque a mano.
2. Cita remitente (actor), fecha (timestamp) y signal_id de cada
   correo que menciones, para que la respuesta sea verificable.
3. Si las herramientas no devuelven nada relevante para la consulta,
   dilo explicitamente ("no encontre correos sobre eso"). No inventes
   correos ni completes con conocimiento general.
