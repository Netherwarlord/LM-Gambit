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


#: Architectures whose runtimes ask llama.cpp to offload layers to a GPU.
GPU_ARCHITECTURES = frozenset({"cuda", "rocm", "apple_silicon"})

#: The subset that runs *only* through llama.cpp, and can therefore be safely
#: swapped for the CPU runtime when the installed build cannot offload.
#:
#: apple_silicon is excluded on purpose. Its runtime is dual-mode: GGUF files go
#: through llama.cpp, but directories with a config.json go through mlx-lm,
#: which drives the GPU with no involvement from llama-cpp-python at all. It
#: also overrides discover_gguf_models() to find those directories. Falling back
#: to the CPU runtime there would break MLX discovery and loading outright, over
#: a limitation that does not apply to MLX in the first place.
LLAMA_ONLY_GPU_ARCHITECTURES = frozenset({"cuda", "rocm"})


def detect_architecture() -> EngineDescriptor:
    """Which engine runtime this *hardware* calls for.

    This looks at drivers and CPU family only. It deliberately says nothing
    about whether the installed llama-cpp-python can actually use that
    hardware — see gpu_offload_supported() for that half.
    """
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin" and machine.startswith("arm"):
        return EngineDescriptor("apple_silicon")

    if shutil.which("nvidia-smi"):
        return EngineDescriptor("cuda")

    if shutil.which("rocm-smi") or shutil.which("rocminfo"):
        return EngineDescriptor("rocm")

    return EngineDescriptor("cpu")


def gpu_offload_supported() -> Optional[bool]:
    """Whether the installed llama-cpp-python was *built* with GPU offload.

    Detection and capability are two different questions, and they routinely
    disagree. llama-cpp-python compiles its backend in at install time and the
    default wheel is CPU-only, so a machine with an RTX card is detected as
    "cuda", loads the CUDA runtime, sets n_gpu_layers=-1 — and then generates
    every token on the CPU, because the binary has no CUDA in it. Nothing
    errors. The card sits at 0% while the interface reports "cuda".

    llama_supports_gpu_offload() answers the question the detection cannot:
    it reports what the binary can do, not what the machine has.

    Returns None when the answer is unknowable — llama_cpp missing, or too old
    to expose the symbol — so callers can distinguish "no" from "cannot tell".
    """
    try:
        import llama_cpp
    except Exception:
        return None

    probe = getattr(llama_cpp, "llama_supports_gpu_offload", None)
    if probe is None:
        return None

    try:
        return bool(probe())
    except Exception:
        return None


def engine_warning(
    descriptor: Optional[EngineDescriptor] = None,
    *,
    offload: Optional[bool] = None,
) -> Optional[str]:
    """A human-readable warning when hardware and build disagree, else None."""
    descriptor = descriptor or detect_architecture()
    if descriptor.architecture not in GPU_ARCHITECTURES:
        return None

    offload = gpu_offload_supported() if offload is None else offload
    if offload is not False:
        return None

    if descriptor.architecture == "apple_silicon":
        # Scoped to GGUF deliberately. MLX models still get the GPU here — they
        # go through mlx-lm, which has nothing to do with how llama-cpp-python
        # was compiled. Claiming "the GPU will sit idle" would be false for
        # anyone running MLX.
        return (
            "The installed llama-cpp-python is a CPU-only build, so GGUF models "
            "will run on the CPU. MLX models are unaffected and still use the "
            "GPU. See GPU-ACCELERATION.md to rebuild with Metal support."
        )

    return (
        f"{descriptor.architecture} hardware was detected, but the installed "
        "llama-cpp-python is a CPU-only build, so the GPU will sit idle and "
        "generation will run on the CPU. See GPU-ACCELERATION.md to install "
        "a matching wheel."
    )


def effective_descriptor(
    descriptor: Optional[EngineDescriptor] = None,
    *,
    offload: Optional[bool] = None,
) -> EngineDescriptor:
    """The runtime that will actually execute, which the hardware alone cannot say.

    A CPU-only llama-cpp-python on an NVIDIA box cannot offload anything, but
    the CUDA runtime will still load, call itself "llama_cpp_cuda", and request
    n_gpu_layers=-1. llama.cpp quietly ignores the request and runs on the CPU,
    so every one of those signals is fiction. Selecting the CPU runtime instead
    makes the reported runtime match what actually happens.

    This hides nothing: detect_architecture() still reports the real hardware,
    and engine_warning() still explains why the two differ.
    """
    descriptor = descriptor or detect_architecture()
    if descriptor.architecture not in LLAMA_ONLY_GPU_ARCHITECTURES:
        return descriptor

    offload = gpu_offload_supported() if offload is None else offload
    if offload is False:
        return EngineDescriptor("cpu", descriptor.version)
    return descriptor


def load_engine_class(descriptor: Optional[EngineDescriptor] = None) -> Type["BaseRuntime"]:
    # Resolved through effective_descriptor so a GPU runtime is never loaded on
    # a build that cannot drive one. Callers still pass the hardware-detected
    # descriptor; the substitution happens here so every entry point gets it.
    descriptor = effective_descriptor(descriptor)
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
