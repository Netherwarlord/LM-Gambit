from __future__ import annotations

import json
import time
from typing import Dict, List, Optional

import requests

from config import get_env_setting
from .base import ModelInfo, Provider, ProviderError

DEFAULT_BASE_URL = "http://localhost:1234"

#: LM Studio's native endpoint labels each model. ``llm`` and ``vlm`` can both
#: answer a prompt; ``embeddings`` cannot, and offering one produces an empty
#: report with no error. The OpenAI-compatible ``/v1/models`` carries no such
#: field, which is why the native endpoint is tried first.
NON_GENERATIVE_TYPES = frozenset({"embeddings"})


class LMStudioProvider(Provider):
    name = "LM Studio"

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = base_url or get_env_setting("LM_STUDIO_BASE_URL", DEFAULT_BASE_URL)
        self._models_url = f"{self.base_url}/v1/models"
        self._native_models_url = f"{self.base_url}/api/v0/models"
        self._chat_url = f"{self.base_url}/v1/chat/completions"

    # ------------------------------------------------------------- listing

    def list_models(self) -> List[ModelInfo]:
        """Models that can actually answer a prompt.

        Prefers LM Studio's native endpoint, which states each model's type.
        Falls back to the OpenAI-compatible list unfiltered when that is
        unavailable — an older LM Studio, say. Only positive evidence hides a
        model: a name-based guess would conceal any legitimate model whose id
        happened to contain "embed", and a model missing from the picker is
        harder to diagnose than one that fails when run.
        """
        native = self._native_models()
        if native is not None:
            return native
        return self._openai_models()

    def _native_models(self) -> Optional[List[ModelInfo]]:
        """Parse ``/api/v0/models``, or None if it is not usable."""
        try:
            response = requests.get(self._native_models_url, timeout=10)
            response.raise_for_status()
            data = response.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError, ValueError):
            return None

        entries = data.get("data") if isinstance(data, dict) else None
        if not isinstance(entries, list) or not entries:
            return None

        result: List[ModelInfo] = []
        skipped = 0
        for item in entries:
            if not isinstance(item, dict):
                return None  # not the shape we expected; fall back
            model_id = str(item.get("id") or "")
            if not model_id:
                continue
            if str(item.get("type", "")).lower() in NON_GENERATIVE_TYPES:
                skipped += 1
                continue
            result.append(ModelInfo(id=model_id, display_name=model_id))

        if not result:
            if skipped:
                raise ProviderError(
                    f"LM Studio has {skipped} model(s) loaded, but all of them are "
                    "embedding models, which cannot generate text. Load a chat or "
                    "instruct model."
                )
            return None
        return result

    def _openai_models(self) -> List[ModelInfo]:
        """The OpenAI-compatible list. No type information, so no filtering."""
        try:
            response = requests.get(self._models_url, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise ProviderError(f"Failed to fetch models from LM Studio: {exc}") from exc

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise ProviderError(f"Failed to decode model list: {exc}") from exc

        models = data.get("data", [])
        result: List[ModelInfo] = []
        if isinstance(models, list):
            for item in models:
                if isinstance(item, dict):
                    model_id = str(item.get("id") or item.get("name") or "")
                else:
                    model_id = str(item)
                if not model_id:
                    continue
                result.append(ModelInfo(id=model_id, display_name=model_id))

        default_model = data.get("default_model") or data.get("model") or data.get("id")
        if default_model and all(m.id != default_model for m in result):
            result.insert(0, ModelInfo(id=str(default_model), display_name=str(default_model)))

        if not result:
            raise ProviderError("LM Studio returned no models.")

        return result

    def run_prompt(self, model_id: str, prompt: str, *, temperature: float) -> Dict[str, object]:
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }

        start_time = time.time()
        try:
            response = requests.post(
                self._chat_url,
                headers=headers,
                data=json.dumps(payload),
                timeout=180,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            return {"error": f"API request failed: {exc}"}

        end_time = time.time()

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            return {"error": f"Failed to parse response JSON: {exc}\nRaw: {response.text}"}

        response_time = end_time - start_time
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "Error: No content found.")
        usage = data.get("usage", {})
        total_tokens = usage.get("completion_tokens", 0)
        time_to_first_token = usage.get("prompt_eval_duration", 0) / 1_000_000_000
        stop_reason = data.get("choices", [{}])[0].get("finish_reason", "N/A")

        tokens_per_second = total_tokens / response_time if response_time > 0 else 0

        return {
            "response": content,
            "metrics": {
                "tokens_per_second": round(tokens_per_second, 2),
                "total_tokens": total_tokens,
                "time_to_first_token": round(time_to_first_token, 2),
                "stop_reason": stop_reason,
            },
        }
