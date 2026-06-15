# Infraestructura de Datos Personal — Pipeline de Correo

Proyecto académico (INFB6074, UTEM). Pipeline reproducible y conteinerizado que ingesta correo desde un archivo `.mbox`, lo normaliza al patrón medallón (Bronze → Silver → Gold), aplica reglas de calidad documentadas, indexa el contenido con embeddings y expone los datos vía una API local.

## Requisitos

- **Motor de contenedores OCI**: Docker Engine + Docker Compose v2 **o** Podman ≥ 4.x + Podman Compose
- Python 3.12 (solo para desarrollo local sin contenedores)
- Un archivo `.mbox` con correos a procesar

### Portabilidad de motor

El proyecto es neutral respecto al motor de contenedores. Todo funciona con Docker o Podman de forma equivalente. El `Makefile` detecta automáticamente cuál está disponible.

### Operación rootless

Ningún servicio requiere privilegios de root. El `Dockerfile` declara un usuario no-root (`appuser`). El `compose.yml` no usa `privileged: true` ni monta sockets del motor. El pipeline puede levantarse sin `sudo` en cualquier entorno con Podman rootless o Docker en modo rootless.

## Inicio rápido

### 1. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env si se necesitan cambios (los valores por defecto funcionan)
```

### 2. Colocar el archivo mbox

```bash
mkdir -p data/input
cp /ruta/a/correos.mbox data/input/correos.mbox
```

### 3. Levantar la infraestructura

Con Docker:

```bash
docker compose -f compose.yml up --build
```

Con Podman:

```bash
podman compose -f compose.yml up --build
```

O usando el Makefile (detecta automáticamente):

```bash
make up
```

El pipeline procesa el archivo `.mbox`, genera los artefactos Silver (Parquet) e indexa en Chroma. Al finalizar, la API queda disponible en `http://localhost:8000`.

### 4. Detener

```bash
make down
# o: docker compose -f compose.yml down -v
# o: podman compose -f compose.yml down -v
```

## API

Documentación interactiva disponible en `http://localhost:8000/docs` (OpenAPI/Swagger).

### GET /signals

Consulta filtrada sobre Silver.

```bash
# Todos los signals (primeros 50)
curl http://localhost:8000/signals

# Filtrar por actor
curl "http://localhost:8000/signals?actor=user@example.com"

# Filtrar por rango de tiempo
curl "http://localhost:8000/signals?from_ts=2024-01-01T00:00:00Z&to_ts=2024-12-31T23:59:59Z&limit=10"
```

### POST /search

Búsqueda semántica sobre el índice de embeddings.

```bash
# Búsqueda por texto libre
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "reunión planificación proyecto", "top_k": 5}'

# Con filtro de fuente
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "factura servidor", "top_k": 3, "source": "mail"}'
```

### GET /health

```bash
curl http://localhost:8000/health
```

## Pipeline

El pipeline ejecuta las siguientes etapas en orden:

1. **Ingesta**: lee el `.mbox` y lo sube a MinIO (Bronze)
2. **Normalización**: parsea los mensajes y construye el esquema unificado Silver
3. **Calidad**: aplica las 6 reglas de calidad, descarta filas inválidas
4. **Embeddings**: genera vectores con `sentence-transformers` e indexa en Chroma
5. **Silver**: escribe Parquet particionado por año/mes

## Reglas de calidad

| ID | Descripción | Severidad |
|---|---|---|
| r01 | actor debe cumplir formato de email RFC 5322 simplificado | error |
| r02 | timestamp no nulo, no futuro (> ahora + 1 día), no anterior a 2000-01-01 | error |
| r03 | content_text con longitud > 10 caracteres tras strip | error |
| r04 | raw_id (Message-ID) no debe repetirse en el mismo run | error |
| r05 | content_text debe ser UTF-8 válido tras decodificación | error |
| r06 | signal_id debe ser determinístico: uuid5(NAMESPACE_URL, source + raw_id) | error |

Las reglas son declarativas y aisladas. Agregar una nueva regla no requiere modificar las existentes (patrón registry con decorador `@regla`).

## Tests

Ejecutar tests localmente:

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

Ejecutar solo tests rápidos (sin embeddings):

```bash
python -m pytest tests/ -v -m "not slow"
```

Con contenedor:

```bash
make test
```

## Estructura del proyecto

```
proyecto/
├── compose.yml           # orquestación OCI neutral
├── .env.example          # variables de entorno (sin secretos)
├── requirements.txt      # dependencias con versiones fijadas
├── Dockerfile            # imagen OCI rootless
├── Makefile              # detección automática Docker/Podman
├── catalogo.yaml         # contrato de datos
├── reglas_calidad.yaml   # contrato de calidad
├── pipeline/
│   ├── main.py           # orquestador
│   ├── etapas/
│   │   ├── ingesta.py    # mbox → Bronze (MinIO)
│   │   ├── normaliza.py  # Bronze → Silver (Polars + Parquet)
│   │   ├── calidad.py    # aplica reglas declarativas
│   │   └── embeddings.py # Silver → Chroma (sentence-transformers)
│   ├── metadata/
│   │   ├── catalogo.py   # carga y valida catalogo.yaml (Pydantic)
│   │   └── linaje.py     # escribe linaje.json (thread-safe)
│   └── utils/
│       ├── minio_client.py
│       └── logging_cfg.py
├── api/
│   ├── main.py           # FastAPI app
│   ├── endpoints/
│   │   ├── consulta.py   # GET /signals (DuckDB → Parquet)
│   │   └── busqueda.py   # POST /search (Chroma)
│   └── modelos.py        # Pydantic schemas
└── tests/
    ├── test_catalogo.py
    ├── test_normaliza.py
    ├── test_calidad.py
    ├── test_embeddings.py
    ├── test_api_consulta.py
    └── test_api_busqueda.py
```

## Verificación de portabilidad

El proyecto fue diseñado para funcionar con ambos motores de contenedores OCI:

- **Docker Engine + Docker Compose v2**: verificado
- **Podman ≥ 4.x + Podman Compose**: diseñado para compatibilidad

Si solo un motor está disponible en el entorno de desarrollo, la verificación se limita a ese motor. El `Makefile` detecta automáticamente cuál usar.

## Restricciones

- **No egress**: la red interna del compose no permite conexiones salientes
- **Sin datos reales en el repo**: solo datos sintéticos generados por fixtures
- **Versiones fijadas**: todas las dependencias en `requirements.txt` con `==`
- **Rootless por diseño**: sin `sudo`, sin `privileged`, sin sockets del motor
