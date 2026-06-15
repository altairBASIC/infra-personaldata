"""Aplicación FastAPI para consulta de señales y búsqueda semántica."""

from fastapi import FastAPI

from api.endpoints.busqueda import router as busqueda_router
from api.endpoints.consulta import router as consulta_router

app = FastAPI(
    title="Infraestructura de Datos Personal",
    description="API local para consulta de señales normalizadas y búsqueda semántica.",
    version="1.0.0",
)

app.include_router(consulta_router, tags=["Signals"])
app.include_router(busqueda_router, tags=["Search"])


@app.get("/health")
async def health() -> dict:
    """Endpoint de salud."""
    return {"status": "ok"}
