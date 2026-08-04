"""Sistema de checkpoints para reanudación de procesamiento ante desconexiones."""

import json
import os
import threading
from datetime import datetime
from pathlib import Path


class ProgressTracker:
    """Maneja la persistencia de progreso durante el procesamiento de carpetas.

    Thread-safe: usa un RLock para que múltiples hilos puedan llamar
    register_processed_file / get_processed_files sin corrupción del JSON.
    """

    def __init__(self, folder_path: str):
        self.folder_path = folder_path
        self.progress_file = os.path.join(folder_path, ".progress.json")
        self._lock = threading.RLock()

    def save(self, data: dict) -> None:
        """Guarda el progreso en .progress.json."""
        with self._lock:
            data["timestamp"] = datetime.now().isoformat()
            with open(self.progress_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    def load(self) -> dict | None:
        """Carga el progreso anterior, o None si no existe."""
        with self._lock:
            if not os.path.exists(self.progress_file):
                return None
            try:
                with open(self.progress_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return None

    def delete(self) -> None:
        """Elimina el archivo de progreso (al terminar exitosamente)."""
        with self._lock:
            if os.path.exists(self.progress_file):
                os.remove(self.progress_file)

    def register_processed_file(self, filename: str) -> None:
        """Registra que un archivo ya fue procesado (thread-safe)."""
        with self._lock:
            data = self.load() or self._init_progress_data()
            if filename not in data["procesados"]:
                data["procesados"].append(filename)
            self.save(data)

    def get_processed_files(self) -> list:
        """Devuelve lista de archivos ya procesados (thread-safe)."""
        with self._lock:
            data = self.load()
            return data["procesados"] if data else []

    def _init_progress_data(self) -> dict:
        """Inicializa estructura vacía de progreso."""
        return {
            "folder": self.folder_path,
            "procesados": [],
            "timestamp": None,
        }

    def has_previous_progress(self) -> bool:
        """Detecta si hay un procesamiento anterior incompleto."""
        with self._lock:
            data = self.load()
            return data is not None and len(data.get("procesados", [])) > 0
