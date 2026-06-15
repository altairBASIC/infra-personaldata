"""Tests para generación de embeddings e indexación en Chroma."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import polars as pl
import pytest

NAMESPACE = uuid.NAMESPACE_URL


def _df_fixture(n: int = 10) -> pl.DataFrame:
    """Crea un DataFrame Silver de prueba con n filas."""
    temas = [
        "reunión de planificación del proyecto de infraestructura",
        "factura del proveedor de servidores del mes de junio",
        "invitación a la conferencia de tecnología en Santiago",
        "solicitud de vacaciones para la última semana de julio",
        "reporte mensual de métricas del equipo de desarrollo",
        "actualización de seguridad crítica para el servidor principal",
        "propuesta de migración a contenedores para producción",
        "resumen del standup diario del equipo backend",
        "notificación de mantenimiento programado del datacenter",
        "feedback sobre la presentación del producto nuevo",
    ]
    registros = []
    for i in range(n):
        raw_id = f"<emb-{i}@test.local>"
        registros.append({
            "signal_id": str(uuid.uuid5(NAMESPACE, "mail" + raw_id)),
            "timestamp": datetime(2024, 6, 15, 10 + (i % 12), 0, 0, tzinfo=timezone.utc),
            "source": "mail",
            "actor": f"user{i}@example.com",
            "channel": None,
            "content_text": temas[i % len(temas)],
            "content_meta": None,
            "entities": None,
            "raw_id": raw_id,
            "ingest_run_id": str(uuid4()),
        })
    df = pl.DataFrame(registros)
    return df.with_columns(pl.col("timestamp").cast(pl.Datetime("us", "UTC")))


@pytest.fixture
def chroma_dir(tmp_path: Path) -> Path:
    """Directorio temporal para Chroma."""
    d = tmp_path / "chroma_test"
    d.mkdir()
    return d


class TestIndexar:
    """Tests de indexación en Chroma."""

    @pytest.mark.slow
    def test_indexar_10_correos(self, chroma_dir: Path) -> None:
        from pipeline.etapas.embeddings import indexar_en_chroma

        df = _df_fixture(10)
        total = indexar_en_chroma(
            df,
            chroma_path=chroma_dir,
            collection_name="test_signals",
        )
        assert total == 10

    @pytest.mark.slow
    def test_idempotencia(self, chroma_dir: Path) -> None:
        from pipeline.etapas.embeddings import indexar_en_chroma

        df = _df_fixture(5)
        indexar_en_chroma(df, chroma_path=chroma_dir, collection_name="test_idemp")
        indexar_en_chroma(df, chroma_path=chroma_dir, collection_name="test_idemp")

        import chromadb
        client = chromadb.PersistentClient(path=str(chroma_dir))
        col = client.get_collection("test_idemp")
        assert col.count() == 5


class TestBuscar:
    """Tests de búsqueda semántica."""

    @pytest.mark.slow
    def test_busqueda_top1_relevante(self, chroma_dir: Path) -> None:
        from pipeline.etapas.embeddings import buscar_en_chroma, indexar_en_chroma

        df = _df_fixture(10)
        indexar_en_chroma(df, chroma_path=chroma_dir, collection_name="test_search")

        resultados = buscar_en_chroma(
            query="reunión planificación proyecto",
            top_k=3,
            chroma_path=chroma_dir,
            collection_name="test_search",
        )
        assert len(resultados) > 0
        assert "reunión" in resultados[0]["content_text"].lower() or \
               "planificación" in resultados[0]["content_text"].lower()

    @pytest.mark.slow
    def test_busqueda_factura(self, chroma_dir: Path) -> None:
        from pipeline.etapas.embeddings import buscar_en_chroma, indexar_en_chroma

        df = _df_fixture(10)
        indexar_en_chroma(df, chroma_path=chroma_dir, collection_name="test_factura")

        resultados = buscar_en_chroma(
            query="factura proveedor servidores",
            top_k=1,
            chroma_path=chroma_dir,
            collection_name="test_factura",
        )
        assert len(resultados) == 1
        assert "factura" in resultados[0]["content_text"].lower()

    @pytest.mark.slow
    def test_busqueda_seguridad(self, chroma_dir: Path) -> None:
        from pipeline.etapas.embeddings import buscar_en_chroma, indexar_en_chroma

        df = _df_fixture(10)
        indexar_en_chroma(df, chroma_path=chroma_dir, collection_name="test_seg")

        resultados = buscar_en_chroma(
            query="actualización seguridad servidor",
            top_k=1,
            chroma_path=chroma_dir,
            collection_name="test_seg",
        )
        assert len(resultados) == 1
        assert "seguridad" in resultados[0]["content_text"].lower()
