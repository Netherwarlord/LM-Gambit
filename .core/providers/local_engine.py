from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Dict, List, Optional

from config import MODELS_DIR
from engine_loader import EngineLoadError, load_engine_class
from .base import ModelInfo, Provider, ProviderError


class LocalEngineProvider(Provider):
    name = "Local Engine"

    def __init__(self, search_paths: Optional[List[Path]] = None) -> None:
        try:
            runtime_cls = load_engine_class()
            self.runtime = runtime_cls()
            self.runtime.setup()
        except EngineLoadError as exc:
            raise ProviderError(str(exc)) from exc
        except RuntimeError as exc:
            raise ProviderError(str(exc)) from exc

        paths: List[Path] = [MODELS_DIR]
        env_override = os.getenv("LOCAL_LLM_PATHS")
        if env_override:
            for entry in env_override.split(os.pathsep):
                entry_clean = entry.strip()
                if not entry_clean:
                    continue
                entry_path = Path(entry_clean).expanduser()
                if entry_path not in paths:
                    paths.append(entry_path)
        if search_paths:
            for candidate in search_paths:
                if candidate not in paths:
                    paths.append(candidate)

        self.search_paths = paths
        self._model_index: Dict[str, Path] = {}

    def list_models(self) -> List[ModelInfo]:
        discovered = self.runtime.discover_gguf_models(self.search_paths)
        self._model_index.clear()
        models: List[ModelInfo] = []
        for path in discovered:
            model_id = self._register_model(path)
            models.append(ModelInfo(id=model_id, display_name=path.stem))
        if not models:
            raise ProviderError(
                "No GGUF models were found. Place models inside the 'models' directory or set LOCAL_LLM_PATHS."
            )
        return models

    def run_prompt(self, model_id: str, prompt: str, *, temperature: float) -> Dict[str, object]:
        try:
            model_path = self._model_index[model_id]
        except KeyError as exc:
            raise ProviderError(f"Model '{model_id}' is not registered. Refresh the model list and try again.") from exc

        self.runtime.load_model(model_path)
        return self.runtime.generate(prompt, temperature=temperature)

    def _register_model(self, path: Path) -> str:
        for existing_id, existing_path in self._model_index.items():
            if path == existing_path:
                return existing_id

        base_id = path.stem
        candidate = base_id
        counter = 1
        while candidate in self._model_index:
            digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:6]
            candidate = f"{base_id}-{digest}-{counter}"
            counter += 1

        self._model_index[candidate] = path
        return candidate
