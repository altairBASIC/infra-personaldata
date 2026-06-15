"""Writer thread-safe del linaje de ejecución en JSON."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pipeline.utils.logging_cfg import get_logger

logger = get_logger("linaje")


class LinajeWriter:
    """Registra el linaje de un run del pipeline de forma thread-safe.

    Cada instancia representa un run completo. Las etapas se agregan
    secuencialmente con ``registrar_etapa``. Al finalizar, ``cerrar``
    escribe el JSON a disco.

    Args:
        ruta_salida: Ruta donde se escribe ``linaje.json``.
        run_id: UUID del run. Si es ``None``, se genera uno nuevo.
    """

    def __init__(self, ruta_salida: Path, run_id: str | None = None) -> None:
        self._lock = threading.Lock()
        self._ruta = ruta_salida
        self.run_id = run_id or str(uuid4())
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._etapas: list[dict[str, Any]] = []

    def registrar_etapa(
        self,
        etapa: str,
        input_path: str,
        output_path: str,
        filas_leidas: int,
        filas_escritas: int,
        duracion_s: float,
        descartadas_por_regla: dict[str, int] | None = None,
    ) -> None:
        """Registra una etapa completada del pipeline.

        Args:
            etapa: Nombre de la etapa (e.g. ``ingesta``, ``normaliza``).
            input_path: Ruta de entrada.
            output_path: Ruta de salida.
            filas_leidas: Cantidad de filas leídas.
            filas_escritas: Cantidad de filas escritas.
            duracion_s: Duración en segundos.
            descartadas_por_regla: Conteo de filas descartadas por regla.
        """
        registro: dict[str, Any] = {
            "etapa": etapa,
            "input": input_path,
            "output": output_path,
            "filas_leidas": filas_leidas,
            "filas_escritas": filas_escritas,
            "duracion_s": round(duracion_s, 2),
        }
        if descartadas_por_regla:
            registro["descartadas_por_regla"] = descartadas_por_regla

        with self._lock:
            self._etapas.append(registro)
            logger.info("Etapa '%s' registrada en linaje", etapa)

    def cerrar(self) -> dict[str, Any]:
        """Escribe el linaje completo a disco y retorna el dict.

        Returns:
            Diccionario con el linaje completo del run.
        """
        with self._lock:
            linaje: dict[str, Any] = {
                "ingest_run_id": self.run_id,
                "started_at": self._started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "etapas": list(self._etapas),
            }

        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(self._ruta, "w", encoding="utf-8") as f:
            json.dump(linaje, f, indent=2, ensure_ascii=False)

        logger.info("Linaje escrito en %s", self._ruta)
        return linaje
