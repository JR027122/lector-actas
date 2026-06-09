"""Compatibilidad: delega en document_processor."""

from src.core.document_processor import process_document, process_folder

__all__ = ["process_document", "process_folder"]
