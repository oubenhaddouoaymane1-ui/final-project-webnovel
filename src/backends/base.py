"""Abstract base classes for free GPU backends — no paid APIs, no keys."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import time


@dataclass
class BackendResult:
    success: bool
    data: Optional[bytes] = None
    output_path: Optional[str] = None
    error: Optional[str] = None
    backend_name: str = ""
    metadata: dict = field(default_factory=dict)
    duration: Optional[float] = None


class ImageBackend(ABC):
    """Abstract interface for image generation backends."""

    name: str = "base"
    priority: int = 99
    requires_gpu: bool = False
    requires_internet: bool = True
    requires_api_key: bool = False

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        seed: Optional[int] = None,
        output_path: Optional[str] = None,
    ) -> BackendResult:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} priority={self.priority}>"


class TTSBackend(ABC):
    """Abstract interface for text-to-speech backends."""

    name: str = "base"
    priority: int = 99
    requires_internet: bool = True
    requires_api_key: bool = False

    @abstractmethod
    async def generate(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
    ) -> BackendResult:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} priority={self.priority}>"
