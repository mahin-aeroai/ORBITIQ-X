"""Re-export RawDocument from ingestion.loaders for chunker compatibility."""
from ..ingestion.loaders import RawDocument

__all__ = ["RawDocument"]
