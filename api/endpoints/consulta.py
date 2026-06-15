"""GET /signals — consulta filtrada sobre Silver (Parquet vía DuckDB)."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import duckdb
from fastapi import APIRouter, Query

from api.modelos import SignalItem, SignalsResponse

router = APIRouter()


def _silver_path() -> str:
    """Retorna el glob de Parquet Silver para DuckDB."""
    base = Path(os.environ.get("SILVER_PATH", "/app/data/silver"))
    return str(base / "**" / "*.parquet")


@router.get("/signals", response_model=SignalsResponse)
async def consultar_signals(
    source: str | None = Query(None, description="Filtrar por fuente"),
    actor: str | None = Query(None, description="Email exacto del actor"),
    from_ts: datetime | None = Query(None, description="Desde (ISO-8601 UTC)"),
    to_ts: datetime | None = Query(None, description="Hasta (ISO-8601 UTC)"),
    limit: int = Query(50, ge=1, le=500, description="Máximo de resultados"),
    offset: int = Query(0, ge=0, description="Desplazamiento"),
) -> SignalsResponse:
    """Consulta filtrada sobre Silver usando DuckDB para lectura directa de Parquet."""
    parquet_glob = _silver_path()

    condiciones: list[str] = []
    params: dict = {}

    if source:
        condiciones.append("source = $source")
        params["source"] = source
    if actor:
        condiciones.append("actor = $actor")
        params["actor"] = actor
    if from_ts:
        condiciones.append("timestamp >= $from_ts")
        params["from_ts"] = from_ts
    if to_ts:
        condiciones.append("timestamp <= $to_ts")
        params["to_ts"] = to_ts

    where_clause = " AND ".join(condiciones) if condiciones else "1=1"

    con = duckdb.connect(":memory:")

    count_query = f"SELECT COUNT(*) FROM read_parquet('{parquet_glob}') WHERE {where_clause}"
    total = con.execute(count_query, params).fetchone()[0]

    data_query = (
        f"SELECT signal_id, timestamp, source, actor, content_text, channel "
        f"FROM read_parquet('{parquet_glob}') "
        f"WHERE {where_clause} "
        f"ORDER BY timestamp DESC "
        f"LIMIT {limit} OFFSET {offset}"
    )
    rows = con.execute(data_query, params).fetchall()
    con.close()

    items = [
        SignalItem(
            signal_id=row[0],
            timestamp=row[1],
            source=row[2],
            actor=row[3],
            content_text=row[4],
            channel=row[5],
        )
        for row in rows
    ]

    return SignalsResponse(total=total, items=items)
