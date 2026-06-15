"""Configuración centralizada de logging JSON estructurado a stdout."""

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Emite cada registro de log como una línea JSON."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra_data"):
            entry["data"] = record.extra_data
        return json.dumps(entry, ensure_ascii=False, default=str)


def configurar_logging(nivel: str = "INFO") -> logging.Logger:
    """Configura el logger raíz del pipeline con formato JSON a stdout.

    Args:
        nivel: Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Returns:
        Logger raíz configurado.
    """
    logger = logging.getLogger("pipeline")
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, nivel.upper(), logging.INFO))
    logger.propagate = False
    return logger


def get_logger(nombre: str) -> logging.Logger:
    """Obtiene un sub-logger del pipeline.

    Args:
        nombre: Sufijo del logger (e.g. ``ingesta`` → ``pipeline.ingesta``).

    Returns:
        Logger hijo configurado.
    """
    configurar_logging()
    return logging.getLogger(f"pipeline.{nombre}")
