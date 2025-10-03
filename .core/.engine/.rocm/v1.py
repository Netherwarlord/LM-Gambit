from __future__ import annotations

import os
import time
from pathlib import Path

try:
    from llama_cpp import Llama
except ImportError as exc:
    raise RuntimeError(
        "llama-cpp-python built with ROCm support is required for the ROCm engine runtime."
    ) from exc

from engine_loader import BaseRuntime


class EngineRuntime(BaseRuntime):
    name = "llama_cpp_rocm"

    def __init__(self, *, context_window: int = 4096, gpu_layers: int = -1) -> None:
        super().__init__()
        self.context_window = context_window
        self.gpu_layers = gpu_layers
        self.threads = max(os.cpu_count() or 1, 1)
        self._llm: Llama | None = None
        self._model_path: Path | None = None

    def load_model(self, model_path: Path) -> None:
        if self._model_path == model_path and self._llm is not None:
            return

        self.unload()
        self._llm = Llama(
            model_path=str(model_path),
            n_ctx=self.context_window,
            n_threads=self.threads,
            n_gpu_layers=self.gpu_layers,
            use_gpu=True,
            verbose=False,
        )
        self._model_path = model_path

    def generate(self, prompt: str, *, temperature: float) -> dict:
        if self._llm is None:
            raise RuntimeError("Model must be loaded before calling generate().")

        start_time = time.time()
        response = self._llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        elapsed = max(time.time() - start_time, 1e-5)

        content = response["choices"][0]["message"]["content"]
        usage = response.get("usage", {})
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", completion_tokens)

        return {
            "response": content,
            "metrics": {
                "tokens_per_second": round(completion_tokens / elapsed, 2) if completion_tokens else 0,
                "total_tokens": total_tokens,
                "time_to_first_token": round(usage.get("prompt_eval_duration", 0) / 1_000_000_000, 2)
                if "prompt_eval_duration" in usage
                else 0,
                "stop_reason": response["choices"][0].get("finish_reason", "unknown"),
            },
        }

    def unload(self) -> None:
        if self._llm is not None:
            self._llm = None
            self._model_path = None
