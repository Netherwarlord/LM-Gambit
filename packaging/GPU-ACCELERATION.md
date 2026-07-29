# GPU acceleration

The first run installs `llama-cpp-python` from PyPI, which is a **CPU build**.
It works everywhere and needs no setup, but it is many times slower than your
GPU.

This is not something the download could have decided for you. `llama-cpp-python`
compiles its backend in, so a CPU wheel stays CPU-only no matter what hardware
it later finds — there is no runtime switch. Getting GPU speed means installing
a different wheel, once.

Run the matching command from **inside this folder**, after the first launch has
created `.venv`.

## NVIDIA (CUDA)

Check your driver's CUDA version with `nvidia-smi`, then match it:

```bash
# Windows
.venv\Scripts\python -m pip install --force-reinstall --no-cache-dir \
  llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124

# macOS / Linux
.venv/bin/python -m pip install --force-reinstall --no-cache-dir \
  llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
```

Swap `cu124` for `cu121` or `cu122` if your driver is older.

## Apple Silicon (Metal)

The PyPI wheel already includes Metal support on arm64 Macs, so there is
usually nothing to do. To force a rebuild against the local SDK:

```bash
CMAKE_ARGS="-DGGML_METAL=on" .venv/bin/python -m pip install \
  --force-reinstall --no-cache-dir llama-cpp-python
```

MLX is used automatically for MLX-format models if `mlx-lm` is installed; the
requirements file pulls it in on Apple Silicon.

## AMD (ROCm)

No prebuilt wheels are published, so this compiles from source and needs the
ROCm toolkit installed:

```bash
CMAKE_ARGS="-DGGML_HIPBLAS=on" .venv/bin/python -m pip install \
  --force-reinstall --no-cache-dir llama-cpp-python
```

## Confirming it worked

Start LM-Gambit and look at the **Engine** panel in the bottom-left. It reports
the detected architecture. Then run one question and compare tokens/second
against what you saw before — that number is the real test.

A caveat worth knowing: the engine detects your *hardware*, not what
`llama-cpp-python` was built with. On an NVIDIA machine it will report `cuda`
even with a CPU wheel installed. If the architecture says `cuda` but throughput
is unchanged, the wheel is still the CPU one.
