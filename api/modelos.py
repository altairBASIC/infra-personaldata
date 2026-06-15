"""Esquemas Pydantic para la API REST."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SignalItem(BaseModel):
    """Señal individual del esquema Silver."""

    signal_id: str
    timestamp: datetime | None = None
    source: str
    actor: str
    content_text: str
    channel: str | None = None


class SignalsResponse(BaseModel):
    """Respuesta de GET /signals."""

    total: int
    items: list[SignalItem]


class SearchRequest(BaseModel):
    """Body de POST /search."""

    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)
    source: str | None = None


class SearchResultItem(BaseModel):
    """Resultado individual de búsqueda semántica."""

    signal_id: str
    score: float
    content_text: str
    timestamp: str = ""
    actor: str = ""


class SearchResponse(BaseModel):
    """Respuesta de POST /search."""

    results: list[SearchResultItem]
