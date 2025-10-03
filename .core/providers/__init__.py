from __future__ import annotations

from typing import Dict, List, Type

from .base import ModelInfo, Provider, ProviderError
from .lmstudio import LMStudioProvider
from .local_engine import LocalEngineProvider

_PROVIDER_REGISTRY: Dict[str, Type[Provider]] = {
    LMStudioProvider.name: LMStudioProvider,
    LocalEngineProvider.name: LocalEngineProvider,
}


def list_provider_names() -> List[str]:
    return sorted(_PROVIDER_REGISTRY.keys())


def get_provider(provider_name: str, **kwargs) -> Provider:
    try:
        provider_cls = _PROVIDER_REGISTRY[provider_name]
    except KeyError as exc:
        raise ProviderError(f"Unknown provider '{provider_name}'") from exc
    return provider_cls(**kwargs)


__all__ = [
    "ModelInfo",
    "Provider",
    "ProviderError",
    "list_provider_names",
    "get_provider",
    "LocalEngineProvider",
]
