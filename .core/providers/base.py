from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class ModelInfo:
    id: str
    display_name: str


class ProviderError(Exception):
    """Base exception for provider-related errors."""


class Provider(ABC):
    """Abstract interface for model providers."""

    name: str

    @abstractmethod
    def list_models(self) -> List[ModelInfo]:
        """Return the models available from this provider."""

    @abstractmethod
    def run_prompt(self, model_id: str, prompt: str, *, temperature: float) -> Dict[str, object]:
        """Execute a prompt against a model and return the response payload."""
