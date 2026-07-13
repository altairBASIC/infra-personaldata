# Capa de agente: servidor MCP y Hermes Agent

Esta carpeta contiene el servidor Model Context Protocol (MCP) que expone la
infraestructura personaldata a agentes de IA, y esta guia documenta como
conectarle Hermes Agent en dos configuraciones de inferencia: local (Ollama,
sin egress del agente) y nube (Gemini, con egress documentado).

## Coherencia con la tesis: sustrato fijo, consumidor flexible

El pipeline y la API (el sustrato de datos) son soberanos y sin egress: el
contenido de los correos nunca sale de la maquina. El agente es un consumidor
intercambiable que se conecta por un protocolo estandar (MCP). La eleccion del
modelo del agente (local o nube) es una decision separada, con su propio
trade-off entre confiabilidad, latencia y soberania, y no modifica el sustrato.
En la configuracion nube, lo unico que sale de la maquina son los fragmentos de
correo que la tool devuelve al modelo remoto, y eso queda documentado como
decision consciente.

## Arquitectura

```
Hermes Agent (CLI)
   |  stdio (MCP)
servidor.py (adaptador delgado, este directorio)
   |  HTTP localhost:8000
API FastAPI (contenedor, sin egress)
   |  DuckDB / Chroma
Silver + Gold + indice vectorial
```

El servidor expone dos tools con descripciones en espanol:

- `buscar_correos(query, top_k)`: traduce a `POST /search` (busqueda semantica).
- `consultar_senales(actor, from_ts, to_ts, limit)`: traduce a `GET /signals`
  (filtros exactos).

No reimplementa logica del pipeline ni de la API.

## Requisitos

- La infraestructura levantada (`podman compose up` o `make up` en la raiz del
  repo) con datos poblados. Ver el README principal.
- Python 3.12 o superior en el host para el servidor MCP.
- Para el brazo local: Ollama en el host (`brew install ollama`).
- Para el brazo nube: una API key de Gemini con cuota de API habilitada.

## 1. Levantar y verificar el servidor MCP

```bash
# Desde la raiz del repo
python3 -m venv .venv-mcp
.venv-mcp/bin/pip install -r mcp_correos/requirements.txt

# Verificacion aislada (sin agente): inicializa el servidor por stdio,
# comprueba que lista las dos tools y que devuelven datos reales.
.venv-mcp/bin/python -m mcp_correos.probar_servidor
```

Salida esperada: las dos tools listadas y resultados reales de Chroma y Silver,
terminando en "VERIFICACION OK".

El servidor lee la variable `PERSONALDATA_API_URL` (default
`http://localhost:8000`).

## 2. Instalar Hermes Agent y adjuntar el MCP

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
hermes --version && hermes doctor
```

En `~/.hermes/config.yaml` agregar (ajustar las rutas absolutas al clon local):

```yaml
mcp_servers:
  correos-personaldata:
    command: /ruta/al/repo/.venv-mcp/bin/python
    args: ["/ruta/al/repo/mcp_correos/servidor.py"]
    env:
      PERSONALDATA_API_URL: "http://localhost:8000"
    tools:
      include: [buscar_correos, consultar_senales]

platform_toolsets:
  # Solo las tools del MCP: reduce el system prompt de 19.9 KB a 3.7 KB
  # y las schemas de 25 tools a 2. Las tools MCP viven en un toolset
  # propio y hay que listarlas explicitamente.
  cli: [correos-personaldata]

# El default (1.5 s) pierde la carrera contra el arranque del servidor
# MCP y el modelo queda sin tools en modo one-shot.
mcp_discovery_timeout: 15

agent:
  # Refuerza que el modelo invoque tools en vez de describirlas.
  tool_use_enforcement: true
```

Verificar la conexion:

```bash
hermes mcp test correos-personaldata
# Esperado: Connected, Tools discovered: 2
```

Ejecutar Hermes desde la raiz del repo: el archivo `AGENTS.md` del repo se
carga al prompt y contiene la guia de uso de las tools (invocar siempre, citar
signal_id, admitir cuando no hay resultados).

## 3. Brazo LOCAL (Ollama, sin egress del agente)

Hermes exige un contexto minimo de 64 K tokens y Ollama declara menos para los
modelos por defecto, por lo que se crea una variante:

```bash
ollama pull qwen3:8b
printf 'FROM qwen3:8b\nPARAMETER num_ctx 65536\n' > /tmp/Modelfile-qwen3
ollama create qwen3:8b-64k -f /tmp/Modelfile-qwen3
```

En `~/.hermes/config.yaml`, seccion `model`:

```yaml
model:
  default: "qwen3:8b-64k"
  provider: "ollama"
  base_url: "http://localhost:11434/v1"
  context_length: 65536
```

Uso:

```bash
hermes -z "¿Que correos recibi sobre mantenimiento de la base de datos?"
```

Seleccion del modelo local (misma pregunta, 3 intentos, verificacion por traza
dura): qwen2.5:7b y llama3.1:8b invocan la tool solo 1/3 de las veces y
fabrican correos cuando no la invocan; qwen3:8b invoca 3/3 con datos reales.
El detalle esta en `docs/benchmark_agente_local.md`.

## 4. Brazo NUBE (Gemini, con egress documentado)

Estado: configurado pero no evaluado. La suscripcion de consumo Gemini Pro no
otorga cuota de la API de developers (los modelos Pro devuelven 429 con limite
0) y la habilitacion de billing quedo pendiente de procesamiento. La
comparacion completa local contra nube queda como trabajo futuro.

Configuracion lista para cuando haya cuota:

1. La key va en `~/.hermes/.env` (fuera del repo, nunca commiteada):

   ```
   GEMINI_API_KEY=...
   ```

   Hermes acepta `GOOGLE_API_KEY` o `GEMINI_API_KEY`. Advertencia: Hermes a
   veces reescribe ese archivo al actualizar config; verificar que la linea
   siga presente con `grep -c GEMINI_API_KEY ~/.hermes/.env`.

2. Invocacion por brazo, sin tocar la config del brazo local:

   ```bash
   hermes -z "pregunta" --provider gemini -m gemini-pro-latest
   ```

   Si el adaptador nativo devuelve contenido vacio con modelos pensantes,
   forzar el endpoint OpenAI compatible:

   ```bash
   GEMINI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai" \
     hermes -z "pregunta" --provider gemini -m gemini-pro-latest
   ```

3. Egress de este brazo: el system prompt, la pregunta del usuario y los
   fragmentos de correo que las tools devuelven (signal_id, actor, timestamp,
   content_text de los resultados) viajan a la API de Google. El sustrato
   sigue sin egress; el egress es exclusivamente del agente y es una decision
   del usuario. Recordatorio: configurar un tope de gasto en la consola de
   Google AI Studio.

## 5. Reproducir el benchmark

Metodologia completa y resultados en `docs/benchmark_agente_local.md`. En
resumen:

```bash
# 1. Verificar la API antes de cada pregunta
curl -s http://localhost:8000/health

# 2. Correr la pregunta midiendo latencia end to end
/usr/bin/time hermes -z "pregunta" -m qwen3:8b-64k

# 3. Verificar el uso de tool por traza dura (nunca creer lo que el
#    modelo dice): debe haber CallToolRequest y un POST /search o
#    GET /signals con HTTP 200 en el log del MCP.
tail ~/.hermes/logs/mcp-stderr.log
```

Resultados de referencia (2026-07-12, MacBook M4 16 GB, en caliente):
4 de 5 preguntas primarias con uso correcto de tool, latencia media 78.4 s
sobre respuestas validas, y la pregunta trampa (tema inexistente) respondida
con "no encontre correos" en vez de fabricar.

## Notas operativas en macOS

- La VM de Podman puede morir bajo presion de memoria cuando Ollama carga un
  modelo de aprox. 5 GB en un equipo de 16 GB. Mitigacion: tras completar el
  pipeline, bajar MinIO (`podman stop <contenedor-minio>`); la API no lo
  necesita para servir consultas.
- `data/metrics` debe existir en el host antes de levantar la pila, creado con
  permisos de escritura (`mkdir -m 777 data/metrics`). Si compose lo autocrea,
  virtiofs puede exponerlo como root sin escritura dentro de la VM y el
  pipeline falla; en ese caso borrar y recrear el directorio.
- En podman rootless una red `internal: true` no permite reenviar puertos
  publicados al host: por eso la API tiene una segunda red `expuesta` en
  `compose.yml`. El pipeline y MinIO permanecen solo en la red interna.
