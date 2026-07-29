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

```bash
# Windows
.venv\Scripts\python -m pip install --force-reinstall --no-cache-dir \
  llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124

# Linux
.venv/bin/python -m pip install --force-reinstall --no-cache-dir \
  llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124
```

Use `cu124` unless you have a reason not to. It and `cu125` carry current
builds; `cu121` through `cu123` stopped at 0.3.4 and are far behind. You do
**not** need to match your driver's CUDA version exactly — CUDA drivers are
backward compatible, so a 13.x driver runs a cu124 build without complaint.
Older than CUDA 12.4 is the only case where dropping back helps.

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

Start LM-Gambit and open **Settings → Engine**. The row that answers this is
**GPU offload**:

- *Supported by this build* — the installed binary can drive your GPU.
- *Not in this build (CPU only)* — it cannot, whatever the architecture says.

The **Architecture** row above it is detected from your *hardware* and will
happily read `cuda` on any machine with an NVIDIA driver, including one running
an entirely CPU-only build. It is not evidence of anything. When the two
disagree the sidebar also shows a warning, and the Engine chip appends
`· CPU build`.

Then run one question and watch the numbers. On CPU you should expect roughly
10–13 tok/s for a mid-size quantised model; a discrete GPU is several times
that. If throughput did not move after installing a GPU wheel, the install did
not take — check for an error in the pip output, since a failed
`--force-reinstall` leaves the previous build in place.

The blunt external check, run while a question is generating:

```bash
nvidia-smi
```

Your Python process should appear in the process list holding VRAM. If the list
shows only desktop software and utilisation sits at 0%, nothing is reaching the
card.
