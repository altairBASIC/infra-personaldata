"""Servidor MCP para la infraestructura personaldata.

Adaptador delgado entre el Model Context Protocol y la API REST local
del proyecto (FastAPI, por defecto en http://localhost:8000). No
reimplementa logica del pipeline ni de la API: cada tool traduce la
llamada del agente a una peticion HTTP y devuelve la respuesta tal cual.

Uso directo (transporte stdio, el que consumen los agentes):

    python -m mcp_correos.servidor

Variables de entorno:

    PERSONALDATA_API_URL  URL base de la API (default http://localhost:8000)
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

API_URL = os.environ.get("PERSONALDATA_API_URL", "http://localhost:8000").rstrip("/")

# El primer /search tras el arranque de la API puede tardar mas de lo
# normal si el modelo de embeddings aun no esta cargado en el proceso.
TIMEOUT = httpx.Timeout(60.0, connect=5.0)

mcp = FastMCP("correos-personaldata")


def _error(mensaje: str) -> dict[str, Any]:
    return {"error": mensaje}


async def _llamar_api(metodo: str, ruta: str, **kwargs: Any) -> dict[str, Any]:
    """Ejecuta una peticion HTTP contra la API local y normaliza errores."""
    try:
        async with httpx.AsyncClient(base_url=API_URL, timeout=TIMEOUT) as cliente:
            respuesta = await cliente.request(metodo, ruta, **kwargs)
    except httpx.ConnectError:
        return _error(
            f"No se pudo conectar a la API en {API_URL}. "
            "Verifica que la infraestructura este levantada (podman compose up)."
        )
    except httpx.TimeoutException:
        return _error(f"La API en {API_URL} no respondio dentro del tiempo limite.")
    if respuesta.status_code != 200:
        return _error(f"La API respondio HTTP {respuesta.status_code}: {respuesta.text[:300]}")
    return respuesta.json()


@mcp.tool()
async def buscar_correos(query: str, top_k: int = 5) -> dict[str, Any]:
    """Busca correos personales por significado (busqueda semantica).

    Usa esta herramienta cuando el usuario pregunte por el contenido de
    sus correos: temas tratados, avisos recibidos, facturas, reuniones,
    quien escribio sobre algo, etc. La busqueda es semantica sobre
    embeddings, no literal: formula la consulta como una frase con el
    significado buscado (por ejemplo "aviso de mantenimiento de la base
    de datos"), no como palabras clave sueltas. Funciona en espanol y
    en ingles.

    Args:
        query: Frase que describe lo que se busca en los correos.
        top_k: Cantidad maxima de fragmentos a devolver (1 a 100, default 5).

    Returns:
        Diccionario con la lista "results". Cada resultado trae
        signal_id (identificador unico del correo), score (similitud,
        mas alto es mas relevante), content_text (el texto del correo),
        timestamp (fecha de envio) y actor (email del remitente).
        Cita signal_id, actor y timestamp al responder para que el
        usuario pueda verificar la fuente.
    """
    return await _llamar_api("POST", "/search", json={"query": query, "top_k": top_k})


@mcp.tool()
async def consultar_senales(
    actor: str | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Lista correos (senales) con filtros exactos, sin busqueda semantica.

    Usa esta herramienta cuando el usuario pida correos por remitente o
    por rango de fechas, o quiera un listado o conteo general, no una
    busqueda por tema. Por ejemplo: "que correos me mando ana@ejemplo.com",
    "cuantos correos recibi en febrero", "muestrame los ultimos correos".

    Args:
        actor: Email exacto del remitente (por ejemplo "ana@ejemplo.com").
            Omitir para no filtrar por remitente.
        from_ts: Fecha y hora minima en ISO-8601 UTC (por ejemplo
            "2026-02-01T00:00:00Z"). Omitir para no acotar el inicio.
        to_ts: Fecha y hora maxima en ISO-8601 UTC. Omitir para no
            acotar el final.
        limit: Maximo de correos a devolver (1 a 500, default 50).

    Returns:
        Diccionario con "total" (cuantos correos cumplen los filtros) e
        "items". Cada item trae signal_id, timestamp, source, actor,
        content_text y channel. Los resultados vienen ordenados del mas
        reciente al mas antiguo.
    """
    params: dict[str, Any] = {"limit": limit}
    if actor is not None:
        params["actor"] = actor
    if from_ts is not None:
        params["from_ts"] = from_ts
    if to_ts is not None:
        params["to_ts"] = to_ts
    return await _llamar_api("GET", "/signals", params=params)


if __name__ == "__main__":
    mcp.run()
