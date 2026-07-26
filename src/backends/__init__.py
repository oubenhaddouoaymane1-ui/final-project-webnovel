"""Backend abstraction layer — all free, no paid APIs, no keys required."""
from .base import ImageBackend, TTSBackend, BackendResult
from .manager import BackendManager, build_default_manager

__all__ = [
    "ImageBackend", "TTSBackend", "BackendResult",
    "BackendManager", "build_default_manager",
]
