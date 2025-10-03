from __future__ import annotations

import importlib.abc
import importlib.util
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Type

from config import CORE_DIR

ENGINE_ROOT = CORE_DIR / ".engine"
DEFAULT_ENGINE_VERSION = "v1"


class EngineLoadError(RuntimeError):
    """Raised when no suitable engine runtime can be loaded."""


class BaseRuntime:
    """Base class for local engine runtimes."""

    name: str = "base"

    def discover_gguf_models(self, search_paths: list[Path]) -> list[Path]:
        gguf_paths: list[Path] = []
        seen: set[Path] = set()
        for root in search_paths:
            if not root.exists():
                continue
            for path in root.rglob("*.gguf"):
                if path.is_file():
                    resolved = path.resolve()
                    if resolved not in seen:
                        seen.add(resolved)
                        gguf_paths.append(resolved)
        return gguf_paths

    def setup(self) -> None:
        """Perform any runtime initialization before loading models."""

    def load_model(self, model_path: Path) -> None:
        """Load model into memory. Implementations may cache the loaded model."""

    def generate(self, prompt: str, *, temperature: float) -> dict:
        """Run inference against the currently loaded model and return a structured response."""
        raise NotImplementedError

    def unload(self) -> None:
        """Optional hook to release resources."""


@dataclass(frozen=True)
class EngineDescriptor:
    architecture: str
    version: str = DEFAULT_ENGINE_VERSION

    @property
    def module_path(self) -> Path:
        return ENGINE_ROOT / f".{self.architecture}" / f"{self.version}.py"

    @property
    def module_name(self) -> str:
        return f"engine_{self.architecture}_{self.version}"


def detect_architecture() -> EngineDescriptor:
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin" and machine.startswith("arm"):
        return EngineDescriptor("apple_silicon")

    if shutil.which("nvidia-smi"):
        return EngineDescriptor("cuda")

    if shutil.which("rocm-smi") or shutil.which("rocminfo"):
        return EngineDescriptor("rocm")

    return EngineDescriptor("cpu")


def load_engine_class(descriptor: Optional[EngineDescriptor] = None) -> Type["BaseRuntime"]:
    descriptor = descriptor or detect_architecture()
    module_path = descriptor.module_path
    if not module_path.exists():
        raise EngineLoadError(f"Engine runtime not found for architecture '{descriptor.architecture}' at {module_path}")

    spec = importlib.util.spec_from_file_location(descriptor.module_name, module_path)
    if spec is None or spec.loader is None:
        raise EngineLoadError(f"Unable to load engine module from {module_path}")

    module = importlib.util.module_from_spec(spec)
    loader = spec.loader
    assert isinstance(loader, importlib.abc.Loader)
    try:
        loader.exec_module(module)  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover - import-time validation
        raise EngineLoadError(f"Failed to initialize engine runtime for '{descriptor.architecture}': {exc}") from exc

    if not hasattr(module, "EngineRuntime"):
        raise EngineLoadError(f"Engine module {module_path} does not define 'EngineRuntime'")

    runtime_cls = getattr(module, "EngineRuntime")
    if not issubclass(runtime_cls, BaseRuntime):
        raise EngineLoadError(f"Engine runtime from {module_path} must inherit from BaseRuntime")
    return runtime_cls
