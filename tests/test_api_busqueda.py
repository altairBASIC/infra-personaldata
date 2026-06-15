"""Tests para POST /search."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import polars as pl
import pytest
from httpx import ASGITransport, AsyncClient

NAMESPACE = uuid.NAMESPACE_URL


def _indexar_fixture(chroma_dir: Path) -> None:
    """Indexa datos de prueba en Chroma."""
    from pipeline.etapas.embeddings import indexar_en_chroma

    temas = [
        "reunión de planificación del proyecto de infraestructura",
        "factura del proveedor de servidores del mes",
        "invitación a la conferencia de tecnología",
        "solicitud de vacaciones para julio",
        "reporte mensual de métricas del equipo",
    ]
    registros = []
    for i, tema in enumerate(temas):
        raw_id = f"<search-{i}@test.local>"
        registros.append({
            "signal_id": str(uuid.uuid5(NAMESPACE, "mail" + raw_id)),
            "timestamp": datetime(2024, 6, 15, 10 + i, 0, 0, tzinfo=timezone.utc),
            "source": "mail",
            "actor": f"user{i}@example.com",
            "channel": None,
            "content_text": tema,
            "content_meta": None,
            "entities": None,
            "raw_id": raw_id,
            "ingest_run_id": str(uuid4()),
        })
    df = pl.DataFrame(registros).with_columns(
        pl.col("timestamp").cast(pl.Datetime("us", "UTC")),
    )
    indexar_en_chroma(df, chroma_path=chroma_dir, collection_name="signals")


@pytest.fixture
def chroma_fixture(tmp_path: Path) -> Path:
    """Prepara Chroma con datos de prueba."""
    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()
    _indexar_fixture(chroma_dir)
    return chroma_dir


@pytest.fixture
def app_con_chroma(chroma_fixture: Path):
    """Configura la app con Chroma en directorio temporal."""
    os.environ["CHROMA_PATH"] = str(chroma_fixture)
    silver_dir = chroma_fixture.parent / "silver_dummy" / "mail" / "year=2024" / "month=06"
    silver_dir.mkdir(parents=True)
    os.environ["SILVER_PATH"] = str(chroma_fixture.parent / "silver_dummy")
    from api.main import app
    return app


@pytest.mark.asyncio
@pytest.mark.slow
async def test_search_basico(app_con_chroma) -> None:
    transport = ASGITransport(app=app_con_chroma)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/search", json={
            "query": "planificación proyecto",
            "top_k": 3,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert len(data["results"]) > 0


@pytest.mark.asyncio
@pytest.mark.slow
async def test_search_con_source(app_con_chroma) -> None:
    transport = ASGITransport(app=app_con_chroma)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/search", json={
            "query": "factura servidor",
            "top_k": 1,
            "source": "mail",
        })
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1


@pytest.mark.asyncio
@pytest.mark.slow
async def test_search_tiene_campos_requeridos(app_con_chroma) -> None:
    transport = ASGITransport(app=app_con_chroma)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/search", json={
            "query": "vacaciones julio",
            "top_k": 1,
        })
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert "signal_id" in result
    assert "score" in result
    assert "content_text" in result


@pytest.mark.asyncio
async def test_search_query_vacio() -> None:
    from api.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/search", json={"query": "", "top_k": 1})
    assert resp.status_code == 422
