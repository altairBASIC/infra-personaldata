"""Genera embeddings con sentence-transformers e indexa en Chroma."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import polars as pl

from pipeline.utils.logging_cfg import get_logger

logger = get_logger("embeddings")


def _cargar_modelo(nombre_modelo: str | None = None) -> Any:
    """Carga el modelo de sentence-transformers.

    Args:
        nombre_modelo: Nombre del modelo. Si es ``None``, usa la variable
            de entorno ``EMBEDDING_MODEL`` o el modelo por defecto.

    Returns:
        Modelo SentenceTransformer cargado.
    """
    from sentence_transformers import SentenceTransformer

    modelo = nombre_modelo or os.environ.get(
        "EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
    )
    logger.info("Cargando modelo de embeddings: %s", modelo)
    return SentenceTransformer(modelo, device="cpu")


def _chunk_texto(texto: str, max_tokens: int = 512, solapamiento: int = 50) -> list[str]:
    """Divide texto en chunks con solapamiento si excede max_tokens.

    Usa palabras como proxy de tokens (aprox. 1 palabra ≈ 1.3 tokens).

    Args:
        texto: Texto a dividir.
        max_tokens: Máximo de tokens por chunk.
        solapamiento: Tokens de solapamiento entre chunks.

    Returns:
        Lista de chunks de texto.
    """
    palabras = texto.split()
    max_palabras = int(max_tokens / 1.3)
    solap_palabras = int(solapamiento / 1.3)

    if len(palabras) <= max_palabras:
        return [texto]

    chunks: list[str] = []
    inicio = 0
    while inicio < len(palabras):
        fin = min(inicio + max_palabras, len(palabras))
        chunk = " ".join(palabras[inicio:fin])
        chunks.append(chunk)
        if fin >= len(palabras):
            break
        inicio = fin - solap_palabras

    return chunks


def indexar_en_chroma(
    df: pl.DataFrame,
    chroma_path: Path | None = None,
    nombre_modelo: str | None = None,
    batch_size: int | None = None,
    collection_name: str = "signals",
) -> int:
    """Genera embeddings del Silver y los indexa en Chroma.

    Args:
        df: DataFrame Silver con al menos ``signal_id``, ``content_text``,
            ``timestamp``, ``actor``, ``source``.
        chroma_path: Directorio de persistencia de Chroma.
        nombre_modelo: Modelo de sentence-transformers a usar.
        batch_size: Tamaño de batch para embeddings.
        collection_name: Nombre de la colección en Chroma.

    Returns:
        Cantidad total de documentos indexados.
    """
    import chromadb

    chroma_dir = chroma_path or Path(os.environ.get("CHROMA_PATH", "/app/data/chroma"))
    chroma_dir.mkdir(parents=True, exist_ok=True)

    bs = batch_size or int(os.environ.get("EMBEDDING_BATCH_SIZE", "32"))

    modelo = _cargar_modelo(nombre_modelo)
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    ids_doc: list[str] = []
    textos: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for row in df.iter_rows(named=True):
        signal_id = row["signal_id"]
        content = row.get("content_text", "") or ""
        if not content.strip():
            continue

        chunks = _chunk_texto(content)
        ts_str = ""
        if row.get("timestamp") is not None:
            ts_str = str(row["timestamp"])

        for idx, chunk in enumerate(chunks):
            doc_id = f"{signal_id}_chunk{idx}" if len(chunks) > 1 else signal_id
            ids_doc.append(doc_id)
            textos.append(chunk)
            metadatas.append({
                "signal_id": signal_id,
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "actor": row.get("actor", ""),
                "source": row.get("source", ""),
                "timestamp": ts_str,
            })

    if not textos:
        logger.warning("No hay textos para indexar")
        return 0

    total_indexados = 0
    for i in range(0, len(textos), bs):
        inicio_batch = time.monotonic()
        batch_textos = textos[i:i + bs]
        batch_ids = ids_doc[i:i + bs]
        batch_meta = metadatas[i:i + bs]

        embeddings = modelo.encode(batch_textos, show_progress_bar=False).tolist()

        collection.upsert(
            ids=batch_ids,
            embeddings=embeddings,
            documents=batch_textos,
            metadatas=batch_meta,
        )
        total_indexados += len(batch_textos)
        duracion_batch = time.monotonic() - inicio_batch

        logger.info(
            json.dumps({
                "batch": i // bs + 1,
                "documentos": len(batch_textos),
                "tiempo_s": round(duracion_batch, 3),
            })
        )

    logger.info("Indexación completada: %d documentos en Chroma", total_indexados)
    return total_indexados


def buscar_en_chroma(
    query: str,
    top_k: int = 10,
    source: str | None = None,
    chroma_path: Path | None = None,
    nombre_modelo: str | None = None,
    collection_name: str = "signals",
) -> list[dict[str, Any]]:
    """Busca documentos similares en Chroma.

    Args:
        query: Texto de consulta en lenguaje natural.
        top_k: Cantidad de resultados a retornar.
        source: Filtro opcional por fuente.
        chroma_path: Directorio de Chroma.
        nombre_modelo: Modelo de embeddings.
        collection_name: Nombre de la colección.

    Returns:
        Lista de resultados con signal_id, score, content_text y metadata.
    """
    import chromadb

    chroma_dir = chroma_path or Path(os.environ.get("CHROMA_PATH", "/app/data/chroma"))
    modelo = _cargar_modelo(nombre_modelo)

    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_collection(name=collection_name)

    query_embedding = modelo.encode([query], show_progress_bar=False).tolist()

    where_filter = {"source": source} if source else None
    resultados = collection.query(
        query_embeddings=query_embedding,
        n_results=top_k,
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )

    items: list[dict[str, Any]] = []
    if resultados["ids"] and resultados["ids"][0]:
        for i, doc_id in enumerate(resultados["ids"][0]):
            meta = resultados["metadatas"][0][i] if resultados["metadatas"] else {}
            distance = resultados["distances"][0][i] if resultados["distances"] else 0.0
            score = 1.0 - distance

            items.append({
                "signal_id": meta.get("signal_id", doc_id),
                "score": round(score, 4),
                "content_text": resultados["documents"][0][i] if resultados["documents"] else "",
                "timestamp": meta.get("timestamp", ""),
                "actor": meta.get("actor", ""),
            })

    return items
