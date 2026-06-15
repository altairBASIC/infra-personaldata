"""POST /search — búsqueda semántica sobre Chroma."""

from __future__ import annotations

from fastapi import APIRouter

from api.modelos import SearchRequest, SearchResponse, SearchResultItem
from pipeline.etapas.embeddings import buscar_en_chroma

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def buscar(body: SearchRequest) -> SearchResponse:
    """Búsqueda semántica sobre el índice Chroma."""
    resultados = buscar_en_chroma(
        query=body.query,
        top_k=body.top_k,
        source=body.source,
    )

    items = [
        SearchResultItem(
            signal_id=r["signal_id"],
            score=r["score"],
            content_text=r["content_text"],
            timestamp=r.get("timestamp", ""),
            actor=r.get("actor", ""),
        )
        for r in resultados
    ]

    return SearchResponse(results=items)
