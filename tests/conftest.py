"""Fixtures compartidas para tests."""

from __future__ import annotations

import email.utils
import mailbox
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import polars as pl
import pytest


def _crear_mensaje(
    from_addr: str = "test@example.com",
    subject: str = "Test Subject",
    body: str = "Este es un correo de prueba con suficiente contenido.",
    date: datetime | None = None,
    message_id: str | None = None,
    charset: str = "utf-8",
) -> email.message.Message:
    """Crea un mensaje de email para fixtures."""
    msg = email.message.Message()
    msg["From"] = from_addr
    msg["To"] = "dest@example.com"
    msg["Subject"] = subject
    msg["Message-ID"] = message_id or f"<{uuid4()}@test.local>"
    dt = date or datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
    msg["Date"] = email.utils.format_datetime(dt)
    msg.set_payload(body, charset=charset)
    return msg


@pytest.fixture
def mbox_limpio(tmp_path: Path) -> Path:
    """Fixture: mbox con 5 mensajes limpios."""
    ruta = tmp_path / "limpio.mbox"
    mbox = mailbox.mbox(str(ruta))
    for i in range(5):
        msg = _crear_mensaje(
            from_addr=f"usuario{i}@example.com",
            subject=f"Asunto número {i}",
            body=f"Contenido del mensaje número {i} con texto suficientemente largo.",
            message_id=f"<limpio-{i}@test.local>",
        )
        mbox.add(msg)
    mbox.close()
    return ruta


@pytest.fixture
def mbox_encoding_mixto(tmp_path: Path) -> Path:
    """Fixture: mbox con codificaciones mixtas."""
    ruta = tmp_path / "encoding_mixto.mbox"
    mbox = mailbox.mbox(str(ruta))

    msg_utf8 = _crear_mensaje(
        from_addr="utf8@example.com",
        body="Mensaje en UTF-8 con acentos: áéíóú ñ.",
        message_id="<enc-utf8@test.local>",
        charset="utf-8",
    )
    mbox.add(msg_utf8)

    msg_latin = _crear_mensaje(
        from_addr="latin@example.com",
        body="Mensaje en ISO-8859-1 con acentos: áéíóú.",
        message_id="<enc-latin@test.local>",
        charset="iso-8859-1",
    )
    mbox.add(msg_latin)

    msg_win = _crear_mensaje(
        from_addr="win@example.com",
        body="Mensaje en Windows-1252 con comillas especiales.",
        message_id="<enc-win@test.local>",
        charset="windows-1252",
    )
    mbox.add(msg_win)

    mbox.close()
    return ruta


@pytest.fixture
def mbox_html(tmp_path: Path) -> Path:
    """Fixture: mbox con cuerpos HTML."""
    ruta = tmp_path / "html.mbox"
    mbox = mailbox.mbox(str(ruta))

    msg = email.message.Message()
    msg["From"] = "html@example.com"
    msg["To"] = "dest@example.com"
    msg["Subject"] = "Email HTML"
    msg["Message-ID"] = "<html-1@test.local>"
    msg["Date"] = email.utils.format_datetime(
        datetime(2024, 3, 10, 8, 0, 0, tzinfo=timezone.utc)
    )
    msg["Content-Type"] = "text/html; charset=utf-8"
    msg.set_payload(
        "<html><body><p>Párrafo uno</p><p>Párrafo dos con <b>negrita</b></p></body></html>",
        charset="utf-8",
    )
    mbox.add(msg)
    mbox.close()
    return ruta


@pytest.fixture
def df_silver_valido() -> pl.DataFrame:
    """Fixture: DataFrame Silver con datos válidos."""
    import uuid

    NAMESPACE = uuid.NAMESPACE_URL
    registros = []
    for i in range(10):
        raw_id = f"<valid-{i}@test.local>"
        signal_id = str(uuid.uuid5(NAMESPACE, "mail" + raw_id))
        registros.append({
            "signal_id": signal_id,
            "timestamp": datetime(2024, 6, 15, 10 + i, 0, 0, tzinfo=timezone.utc),
            "source": "mail",
            "actor": f"user{i}@example.com",
            "channel": None,
            "content_text": f"Contenido del mensaje {i} con suficiente texto para pasar la validación de longitud mínima.",
            "content_meta": None,
            "entities": None,
            "raw_id": raw_id,
            "ingest_run_id": str(uuid4()),
        })

    df = pl.DataFrame(registros)
    return df.with_columns(
        pl.col("timestamp").cast(pl.Datetime("us", "UTC")),
    )
