"""Hardware detection vs. build capability — the two must not be conflated.

detect_architecture() looks at drivers: nvidia-smi present means "cuda". That
says nothing about the llama-cpp-python actually installed, and the default
wheel is CPU-only. The pairing produced a silent failure worth guarding
against: an RTX 4060 machine reported "cuda", loaded the CUDA runtime, set
n_gpu_layers=-1, and generated every token on the CPU with the card at 0%
utilisation. Nothing raised, and the interface said "cuda" throughout.

These tests pin the behaviour that surfaces that mismatch instead of hiding it.
"""

from __future__ import annotations

from _harness import Results, bootstrap

bootstrap()
from engine_loader import (  # noqa: E402
    GPU_ARCHITECTURES,
    EngineDescriptor,
    detect_architecture,
    engine_warning,
    gpu_offload_supported,
)

r = Results("Engine capability reporting")


# ---------------------------------------------------------------- the mismatch

for arch in ("cuda", "rocm", "apple_silicon"):
    warning = engine_warning(EngineDescriptor(arch), offload=False)
    r.check(
        f"{arch} + CPU-only build warns",
        warning is not None and arch in warning,
    )
    r.check(
        f"{arch} warning names the fix",
        warning is not None and "GPU-ACCELERATION.md" in warning,
    )
    r.check(
        f"{arch} warning says the GPU is idle",
        warning is not None and "idle" in warning.lower(),
    )

r.check(
    "GPU-capable build produces no warning",
    engine_warning(EngineDescriptor("cuda"), offload=True) is None,
)


# ------------------------------------------------------- cpu never false-alarms

# A CPU machine running a CPU build is correct, not a misconfiguration. Warning
# there would train users to ignore the warning that matters.
for offload in (False, True, None):
    r.check(
        f"cpu architecture stays quiet (offload={offload})",
        engine_warning(EngineDescriptor("cpu"), offload=offload) is None,
    )


# --------------------------------------------------- unknown is not a negative

# None means "cannot tell" — llama_cpp missing, or too old to expose the
# symbol. Treating that as False would warn every user whose build predates the
# probe, which is worse than staying silent.
for arch in ("cuda", "rocm", "apple_silicon", "cpu"):
    r.check(
        f"{arch} with unknowable offload stays quiet",
        engine_warning(EngineDescriptor(arch), offload=None) is None,
    )


# ------------------------------------------------------------------ the probe

offload = gpu_offload_supported()
r.check(
    "gpu_offload_supported returns bool or None",
    offload is None or isinstance(offload, bool),
)

# Guards against someone "simplifying" the tri-state into a plain bool later:
# the distinction between False and None is load-bearing above.
r.check(
    "probe never returns a truthy non-bool",
    offload is None or offload is True or offload is False,
)


# ------------------------------------------------------------- wiring sanity

descriptor = detect_architecture()
r.check(
    "detect_architecture returns a known architecture",
    descriptor.architecture in GPU_ARCHITECTURES | {"cpu"},
)
r.check(
    "GPU_ARCHITECTURES excludes cpu",
    "cpu" not in GPU_ARCHITECTURES,
)
r.check(
    "every GPU architecture has a runtime module",
    all((EngineDescriptor(a).module_path).exists() for a in GPU_ARCHITECTURES),
)

# engine_warning() must work with no arguments at all, since api.py may call it
# that way if the descriptor is not already to hand.
r.check(
    "engine_warning is callable with no arguments",
    engine_warning() is None or isinstance(engine_warning(), str),
)

raise SystemExit(r.finish())
