"""Tests para la normalización de mbox a esquema Silver."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import polars as pl
import pytest

from pipeline.etapas.normaliza import (
    _extraer_texto_plano,
    _generar_signal_id,
    normalizar_mbox_desde_archivo,
)

NAMESPACE = uuid.NAMESPACE_URL


class TestMboxLimpio:
    """Tests con mbox limpio (5 mensajes válidos)."""

    def test_cantidad_filas(self, mbox_limpio: Path) -> None:
        df = normalizar_mbox_desde_archivo(mbox_limpio, str(uuid4()))
        assert len(df) == 5

    def test_columnas_esquema(self, mbox_limpio: Path) -> None:
        df = normalizar_mbox_desde_archivo(mbox_limpio, str(uuid4()))
        esperadas = {
            "signal_id", "timestamp", "source", "actor", "channel",
            "content_text", "content_meta", "entities", "raw_id", "ingest_run_id",
        }
        assert set(df.columns) == esperadas

    def test_source_siempre_mail(self, mbox_limpio: Path) -> None:
        df = normalizar_mbox_desde_archivo(mbox_limpio, str(uuid4()))
        assert df["source"].unique().to_list() == ["mail"]

    def test_actor_normalizado_minusculas(self, mbox_limpio: Path) -> None:
        df = normalizar_mbox_desde_archivo(mbox_limpio, str(uuid4()))
        for actor in df["actor"].to_list():
            assert actor == actor.lower()

    def test_signal_id_deterministico(self, mbox_limpio: Path) -> None:
        rid = str(uuid4())
        df1 = normalizar_mbox_desde_archivo(mbox_limpio, rid)
        df2 = normalizar_mbox_desde_archivo(mbox_limpio, rid)
        assert df1["signal_id"].to_list() == df2["signal_id"].to_list()


class TestMboxEncodingMixto:
    """Tests con codificaciones mixtas."""

    def test_sin_excepcion(self, mbox_encoding_mixto: Path) -> None:
        df = normalizar_mbox_desde_archivo(mbox_encoding_mixto, str(uuid4()))
        assert len(df) == 3

    def test_contenido_no_vacio(self, mbox_encoding_mixto: Path) -> None:
        df = normalizar_mbox_desde_archivo(mbox_encoding_mixto, str(uuid4()))
        for text in df["content_text"].to_list():
            assert len(text) > 0


class TestMboxHtml:
    """Tests con cuerpos HTML."""

    def test_html_a_texto_plano(self, mbox_html: Path) -> None:
        df = normalizar_mbox_desde_archivo(mbox_html, str(uuid4()))
        assert len(df) == 1
        texto = df["content_text"][0]
        assert "<html>" not in texto
        assert "<p>" not in texto
        assert "Párrafo uno" in texto

    def test_sin_etiquetas_html(self, mbox_html: Path) -> None:
        df = normalizar_mbox_desde_archivo(mbox_html, str(uuid4()))
        texto = df["content_text"][0]
        assert "<b>" not in texto
        assert "</body>" not in texto


class TestHelpers:
    """Tests para funciones auxiliares."""

    def test_generar_signal_id_determinismo(self) -> None:
        id1 = _generar_signal_id("mail", "<abc@test>")
        id2 = _generar_signal_id("mail", "<abc@test>")
        assert id1 == id2

    def test_generar_signal_id_diferente_input(self) -> None:
        id1 = _generar_signal_id("mail", "<abc@test>")
        id2 = _generar_signal_id("mail", "<xyz@test>")
        assert id1 != id2

    def test_extraer_texto_plano_sin_html(self) -> None:
        assert _extraer_texto_plano("texto simple") == "texto simple"

    def test_extraer_texto_plano_con_html(self) -> None:
        html = "<html><body><p>Hola</p><p>Mundo</p></body></html>"
        texto = _extraer_texto_plano(html)
        assert "Hola" in texto
        assert "Mundo" in texto
        assert "<p>" not in texto
