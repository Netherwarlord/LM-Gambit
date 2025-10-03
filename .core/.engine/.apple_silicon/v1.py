from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

try:  # Optional dependency for GGUF execution
    from llama_cpp import Llama
except ImportError:  # pragma: no cover
    Llama = None  # type: ignore

if TYPE_CHECKING:
    from llama_cpp import Llama as LlamaType
else:  # pragma: no cover
    class LlamaType:  # type: ignore
        ...

from engine_loader import BaseRuntime


class EngineRuntime(BaseRuntime):
    name = "mlx_apple_silicon"

    def __init__(self, *, max_tokens: int = 1024, context_window: int = 4096) -> None:
        super().__init__()
        self.max_tokens = max_tokens
        self.context_window = context_window
        self.threads = max(os.cpu_count() or 1, 1)

        self._mode: Optional[str] = None  # "mlx" or "llama_cpp"
        self._model = None
        self._tokenizer = None
        self._llm: Optional[LlamaType] = None
        self._model_path: Path | None = None

    def discover_gguf_models(self, search_paths: list[Path]) -> list[Path]:
        candidates: list[Path] = []
        seen: set[Path] = set()
        for root in search_paths:
            if not root.exists():
                continue
            for path in root.rglob("*.gguf"):
                if path.is_file():
                    resolved = path.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        candidates.append(resolved)
            for path in root.iterdir():
                if path.is_dir() and (path / "config.json").exists():
                    resolved = path.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        candidates.append(resolved)
        return candidates

    def load_model(self, model_path: Path) -> None:
        if self._model_path == model_path:
            if self._mode == "mlx" and self._model is not None:
                return
            if self._mode == "llama_cpp" and self._llm is not None:
                return

        self.unload()
        resolved_path = model_path.resolve()

        if resolved_path.is_file() and resolved_path.suffix.lower() == ".gguf":
            if Llama is None:
                raise RuntimeError(
                    "llama-cpp-python is required to run GGUF models on Apple Silicon. Install it with 'pip install llama-cpp-python'."
                )
            self._llm = Llama(
                model_path=str(resolved_path),
                n_ctx=self.context_window,
                n_gpu_layers=-1,
                n_threads=self.threads,
                use_gpu=True,
                verbose=False,
            )
            self._mode = "llama_cpp"
        else:
            try:
                from mlx_lm import load  # type: ignore import-not-found
            except ImportError as exc:  # pragma: no cover - environment validation
                raise RuntimeError(
                    "mlx-lm is required for MLX models. Install it with 'pip install mlx-lm'."
                ) from exc

            self._model, self._tokenizer = load(str(resolved_path))
            self._mode = "mlx"

        self._model_path = resolved_path

    def generate(self, prompt: str, *, temperature: float) -> dict:
        if self._mode == "llama_cpp":
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

        if self._mode == "mlx":
            if self._model is None or self._tokenizer is None:
                raise RuntimeError("Model must be loaded before calling generate().")

            start_time = time.time()
            try:
                from mlx_lm import generate  # type: ignore import-not-found
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "mlx-lm is required for MLX models. Install it with 'pip install mlx-lm'."
                ) from exc

            completion = generate(
                self._model,
                self._tokenizer,
                prompt,
                max_tokens=self.max_tokens,
                temperature=temperature,
            )
            elapsed = max(time.time() - start_time, 1e-5)

            if isinstance(completion, str):
                text = completion
            else:
                text = str(completion)

            prompt_tokens = len(self._tokenizer.encode(prompt))
            completion_tokens = max(len(self._tokenizer.encode(text)) - prompt_tokens, 0)
            total_tokens = prompt_tokens + completion_tokens

            return {
                "response": text,
                "metrics": {
                    "tokens_per_second": round(completion_tokens / elapsed, 2) if completion_tokens else 0,
                    "total_tokens": total_tokens,
                    "time_to_first_token": 0,
                    "stop_reason": "stop",
                },
            }

        raise RuntimeError("No model is currently loaded. Call load_model() first.")

    def unload(self) -> None:
        self._model = None
        self._tokenizer = None
        self._llm = None
        self._model_path = None
        self._mode = None
