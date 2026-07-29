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
    LLAMA_ONLY_GPU_ARCHITECTURES,
    EngineDescriptor,
    detect_architecture,
    effective_descriptor,
    engine_warning,
    gpu_offload_supported,
)

r = Results("Engine capability reporting")


# ---------------------------------------------------------------- the mismatch

for arch in ("cuda", "rocm", "apple_silicon"):
    warning = engine_warning(EngineDescriptor(arch), offload=False)
    r.check(
        f"{arch} + CPU-only build warns",
        warning is not None,
    )
    r.check(
        f"{arch} warning names the fix",
        warning is not None and "GPU-ACCELERATION.md" in warning,
    )

for arch in ("cuda", "rocm"):
    warning = engine_warning(EngineDescriptor(arch), offload=False)
    r.check(
        f"{arch} warning names the architecture",
        warning is not None and arch in warning,
    )
    r.check(
        f"{arch} warning says the GPU is idle",
        warning is not None and "idle" in warning.lower(),
    )


# ------------------------------------------------- apple silicon is not "idle"

# MLX models reach the GPU through mlx-lm, which does not care how
# llama-cpp-python was compiled. Telling a Mac user their GPU is idle would be
# false for anyone running MLX, so the wording has to stay scoped to GGUF.
mac_warning = engine_warning(EngineDescriptor("apple_silicon"), offload=False)
r.check("apple_silicon warning scopes itself to GGUF", "GGUF" in (mac_warning or ""))
r.check("apple_silicon warning says MLX is unaffected", "MLX" in (mac_warning or ""))
r.check(
    "apple_silicon warning avoids the false 'idle' claim",
    "idle" not in (mac_warning or "").lower(),
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


# --------------------------------------------------- the runtime substitution

# The whole point: on a CPU-only build, a GPU architecture must resolve to the
# CPU runtime, so the reported runtime name matches what actually executes.
for arch in ("cuda", "rocm"):
    r.equal(
        f"{arch} + CPU-only build resolves to the cpu runtime",
        effective_descriptor(EngineDescriptor(arch), offload=False).architecture,
        "cpu",
    )
    r.equal(
        f"{arch} + GPU build keeps its own runtime",
        effective_descriptor(EngineDescriptor(arch), offload=True).architecture,
        arch,
    )
    # None means "cannot tell". Substituting on a guess would silently strip
    # GPU support from anyone whose llama_cpp predates the probe.
    r.equal(
        f"{arch} with unknowable offload is left alone",
        effective_descriptor(EngineDescriptor(arch), offload=None).architecture,
        arch,
    )

# apple_silicon must survive untouched even on a CPU-only build: its runtime
# also serves MLX models, which do not go through llama.cpp at all, and it
# overrides discover_gguf_models() to find them. Swapping in the cpu runtime
# would break MLX discovery and loading outright.
for offload in (False, True, None):
    r.equal(
        f"apple_silicon is never substituted (offload={offload})",
        effective_descriptor(EngineDescriptor("apple_silicon"), offload=offload).architecture,
        "apple_silicon",
    )

r.check(
    "apple_silicon is excluded from the substitutable set",
    "apple_silicon" not in LLAMA_ONLY_GPU_ARCHITECTURES,
)
r.check(
    "substitutable set is a subset of GPU architectures",
    LLAMA_ONLY_GPU_ARCHITECTURES <= GPU_ARCHITECTURES,
)

# The substitution preserves the engine version, or it would silently jump
# runtime versions along with architecture.
r.equal(
    "substitution preserves the engine version",
    effective_descriptor(EngineDescriptor("cuda", "v1"), offload=False).version,
    "v1",
)

# cpu in, cpu out — no architecture should be rewritten to something else.
for offload in (False, True, None):
    r.equal(
        f"cpu architecture is never rewritten (offload={offload})",
        effective_descriptor(EngineDescriptor("cpu"), offload=offload).architecture,
        "cpu",
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
