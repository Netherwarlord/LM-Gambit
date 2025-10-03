from __future__ import annotations

import json
import time
from typing import Dict, List, Optional

import requests

from config import get_env_setting
from .base import ModelInfo, Provider, ProviderError

DEFAULT_BASE_URL = "http://localhost:1234"


class LMStudioProvider(Provider):
    name = "LM Studio"

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = base_url or get_env_setting("LM_STUDIO_BASE_URL", DEFAULT_BASE_URL)
        self._models_url = f"{self.base_url}/v1/models"
        self._chat_url = f"{self.base_url}/v1/chat/completions"

    def list_models(self) -> List[ModelInfo]:
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
