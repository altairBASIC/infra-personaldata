"""Tests para GET /signals."""

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


@pytest.fixture
def silver_dir(tmp_path: Path) -> Path:
    """Crea Parquet Silver de prueba."""
    registros = []
    for i in range(20):
        raw_id = f"<api-{i}@test.local>"
        registros.append({
            "signal_id": str(uuid.uuid5(NAMESPACE, "mail" + raw_id)),
            "timestamp": datetime(2024, 6, 15, 10 + (i % 10), i % 60, 0, tzinfo=timezone.utc),
            "source": "mail",
            "actor": f"user{i % 5}@example.com",
            "channel": None,
            "content_text": f"Contenido del mensaje de prueba número {i} con texto extenso.",
            "content_meta": None,
            "entities": None,
            "raw_id": raw_id,
            "ingest_run_id": str(uuid4()),
        })
    df = pl.DataFrame(registros).with_columns(
        pl.col("timestamp").cast(pl.Datetime("us", "UTC")),
    )

    dir_silver = tmp_path / "silver" / "mail" / "year=2024" / "month=06"
    dir_silver.mkdir(parents=True)
    df.write_parquet(dir_silver / "data.parquet")
    return tmp_path / "silver"


@pytest.fixture
def app_con_silver(silver_dir: Path):
    """Configura la app con Silver en directorio temporal."""
    os.environ["SILVER_PATH"] = str(silver_dir)
    from api.main import app
    return app


@pytest.mark.asyncio
async def test_signals_sin_filtros(app_con_silver, silver_dir: Path) -> None:
    transport = ASGITransport(app=app_con_silver)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/signals")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "items" in data
    assert data["total"] == 20
    assert len(data["items"]) <= 50


@pytest.mark.asyncio
async def test_signals_con_limit(app_con_silver, silver_dir: Path) -> None:
    transport = ASGITransport(app=app_con_silver)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/signals", params={"limit": 5})
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 5


@pytest.mark.asyncio
async def test_signals_filtro_actor(app_con_silver, silver_dir: Path) -> None:
    transport = ASGITransport(app=app_con_silver)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/signals", params={"actor": "user0@example.com"})
    assert resp.status_code == 200
    for item in resp.json()["items"]:
        assert item["actor"] == "user0@example.com"


@pytest.mark.asyncio
async def test_signals_filtro_source(app_con_silver, silver_dir: Path) -> None:
    transport = ASGITransport(app=app_con_silver)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/signals", params={"source": "mail"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 20


@pytest.mark.asyncio
async def test_signals_offset(app_con_silver, silver_dir: Path) -> None:
    transport = ASGITransport(app=app_con_silver)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/signals", params={"limit": 5, "offset": 15})
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 5


@pytest.mark.asyncio
async def test_health(app_con_silver) -> None:
    transport = ASGITransport(app=app_con_silver)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
