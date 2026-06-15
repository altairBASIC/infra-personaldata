"""Tests para las reglas de calidad — casos positivos y negativos por regla."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from pipeline.etapas.calidad import (
    aplica_todas,
    r01_actor_email_valido,
    r02_timestamp_valido,
    r03_content_no_vacio,
    r04_raw_id_unico,
    r05_encoding_valido,
    r06_signal_id_deterministico,
)

NAMESPACE = uuid.NAMESPACE_URL


def _df_base(**overrides) -> pl.DataFrame:
    """Crea un DataFrame de 1 fila con valores válidos por defecto."""
    raw_id = overrides.get("raw_id", "<test-1@test.local>")
    source = overrides.get("source", "mail")
    signal_id = overrides.get(
        "signal_id", str(uuid.uuid5(NAMESPACE, source + raw_id))
    )
    datos = {
        "signal_id": [signal_id],
        "timestamp": [datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)],
        "source": [source],
        "actor": ["user@example.com"],
        "channel": [None],
        "content_text": ["Contenido válido del correo con suficiente longitud."],
        "content_meta": [None],
        "entities": [None],
        "raw_id": [raw_id],
        "ingest_run_id": ["run-001"],
    }
    datos.update({k: [v] for k, v in overrides.items()})
    df = pl.DataFrame(datos)
    return df.with_columns(pl.col("timestamp").cast(pl.Datetime("us", "UTC")))


class TestR01ActorEmailValido:
    """r01: actor debe cumplir formato de email."""

    def test_email_valido(self) -> None:
        df = r01_actor_email_valido(_df_base(actor="user@example.com"))
        assert df["valida_r01_actor_email_valido"][0] is True

    def test_email_con_subdominio(self) -> None:
        df = r01_actor_email_valido(_df_base(actor="a.b@sub.domain.co"))
        assert df["valida_r01_actor_email_valido"][0] is True

    def test_email_invalido_sin_arroba(self) -> None:
        df = r01_actor_email_valido(_df_base(actor="noesunmail"))
        assert df["valida_r01_actor_email_valido"][0] is False

    def test_email_vacio(self) -> None:
        df = r01_actor_email_valido(_df_base(actor=""))
        assert df["valida_r01_actor_email_valido"][0] is False


class TestR02TimestampValido:
    """r02: timestamp no nulo, no futuro, no anterior a 2000."""

    def test_timestamp_valido(self) -> None:
        df = r02_timestamp_valido(_df_base())
        assert df["valida_r02_timestamp_valido"][0] is True

    def test_timestamp_futuro(self) -> None:
        futuro = datetime.now(timezone.utc) + timedelta(days=10)
        df = r02_timestamp_valido(_df_base(timestamp=futuro))
        assert df["valida_r02_timestamp_valido"][0] is False

    def test_timestamp_muy_antiguo(self) -> None:
        antiguo = datetime(1990, 1, 1, tzinfo=timezone.utc)
        df = r02_timestamp_valido(_df_base(timestamp=antiguo))
        assert df["valida_r02_timestamp_valido"][0] is False

    def test_timestamp_nulo(self) -> None:
        df = _df_base(timestamp=None)
        df = df.with_columns(pl.col("timestamp").cast(pl.Datetime("us", "UTC")))
        df = r02_timestamp_valido(df)
        assert df["valida_r02_timestamp_valido"][0] is False


class TestR03ContentNoVacio:
    """r03: content_text > 10 caracteres tras strip."""

    def test_contenido_suficiente(self) -> None:
        df = r03_content_no_vacio(_df_base(content_text="Más de diez caracteres aquí"))
        assert df["valida_r03_content_no_vacio"][0] is True

    def test_contenido_corto(self) -> None:
        df = r03_content_no_vacio(_df_base(content_text="corto"))
        assert df["valida_r03_content_no_vacio"][0] is False

    def test_contenido_solo_espacios(self) -> None:
        df = r03_content_no_vacio(_df_base(content_text="          "))
        assert df["valida_r03_content_no_vacio"][0] is False

    def test_contenido_vacio(self) -> None:
        df = r03_content_no_vacio(_df_base(content_text=""))
        assert df["valida_r03_content_no_vacio"][0] is False


class TestR04RawIdUnico:
    """r04: raw_id no debe repetirse en el mismo run."""

    def test_ids_unicos(self) -> None:
        df = pl.concat([
            _df_base(raw_id="<a@test>"),
            _df_base(raw_id="<b@test>"),
        ])
        df = r04_raw_id_unico(df)
        assert df["valida_r04_raw_id_unico"].to_list() == [True, True]

    def test_ids_duplicados(self) -> None:
        df = pl.concat([
            _df_base(raw_id="<dup@test>"),
            _df_base(raw_id="<dup@test>"),
        ])
        df = r04_raw_id_unico(df)
        assert df["valida_r04_raw_id_unico"].to_list() == [False, False]


class TestR05EncodingValido:
    """r05: content_text debe ser UTF-8 válido (no vacío)."""

    def test_utf8_valido(self) -> None:
        df = r05_encoding_valido(_df_base(content_text="Texto UTF-8 válido: áéíóú"))
        assert df["valida_r05_encoding_valido"][0] is True

    def test_contenido_vacio(self) -> None:
        df = r05_encoding_valido(_df_base(content_text=""))
        assert df["valida_r05_encoding_valido"][0] is False


class TestR06SignalIdDeterministico:
    """r06: signal_id == uuid5(NAMESPACE_URL, source + raw_id)."""

    def test_signal_id_correcto(self) -> None:
        raw_id = "<det@test>"
        signal_id = str(uuid.uuid5(NAMESPACE, "mail" + raw_id))
        df = r06_signal_id_deterministico(_df_base(raw_id=raw_id, signal_id=signal_id))
        assert df["valida_r06_signal_id_deterministico"][0] is True

    def test_signal_id_incorrecto(self) -> None:
        df = r06_signal_id_deterministico(
            _df_base(raw_id="<det@test>", signal_id="id-falso")
        )
        assert df["valida_r06_signal_id_deterministico"][0] is False


class TestAplicaTodas:
    """Tests de la función aplica_todas."""

    def test_todas_validas(self, df_silver_valido: pl.DataFrame) -> None:
        df_ok, descartadas = aplica_todas(df_silver_valido)
        assert len(df_ok) == 10
        assert len(descartadas) == 0

    def test_descarta_email_invalido(self) -> None:
        raw_id = "<bad-email@test>"
        signal_id = str(uuid.uuid5(NAMESPACE, "mail" + raw_id))
        df = _df_base(actor="invalido", raw_id=raw_id, signal_id=signal_id)
        df_ok, desc = aplica_todas(df)
        assert len(df_ok) == 0
        assert "r01_actor_email_valido" in desc
