"""Minimal GGUF header reader.

Only enough of the format to answer "what kind of model is this file?" without
loading it. GGUF stores metadata as key/value pairs immediately after a 24-byte
header, and ``general.architecture`` is conventionally the first key, so the
answer usually arrives within the first few hundred bytes.

This exists to replace a filename heuristic. Filtering the model picker by name
would hide any legitimate model whose filename happened to contain "embed" —
worse than showing one that does not work, because the user cannot see why it
vanished. The architecture field states what the file actually is.

Spec: https://github.com/ggml-org/ggml/blob/master/docs/gguf.md
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

MAGIC = 0x46554747  # "GGUF" little-endian

# Value type tags, and the byte width of the fixed-size ones.
_UINT8, _INT8, _UINT16, _INT16, _UINT32, _INT32, _FLOAT32 = range(7)
_BOOL, _STRING, _ARRAY, _UINT64, _INT64, _FLOAT64 = range(7, 13)

_FIXED = {
    _UINT8: ("<B", 1), _INT8: ("<b", 1), _BOOL: ("<?", 1),
    _UINT16: ("<H", 2), _INT16: ("<h", 2),
    _UINT32: ("<I", 4), _INT32: ("<i", 4), _FLOAT32: ("<f", 4),
    _UINT64: ("<Q", 8), _INT64: ("<q", 8), _FLOAT64: ("<d", 8),
}

#: Give up rather than walk a pathological file. Architecture is key one.
_MAX_PAIRS = 512


class GGUFError(Exception):
    """The file is not readable as GGUF."""


class _Reader:
    """Buffered forward reader. Refills as needed so we never slurp the file."""

    def __init__(self, handle, chunk: int = 1 << 16) -> None:
        self._handle = handle
        self._chunk = chunk
        self._buf = b""
        self._pos = 0

    def _need(self, count: int) -> None:
        while len(self._buf) - self._pos < count:
            more = self._handle.read(max(self._chunk, count))
            if not more:
                raise GGUFError("unexpected end of file")
            self._buf = self._buf[self._pos :] + more
            self._pos = 0

    def take(self, count: int) -> bytes:
        self._need(count)
        out = self._buf[self._pos : self._pos + count]
        self._pos += count
        return out

    def scalar(self, fmt: str, size: int) -> Any:
        return struct.unpack(fmt, self.take(size))[0]

    def string(self) -> str:
        length = self.scalar("<Q", 8)
        if length > 1 << 20:
            raise GGUFError("implausible string length")
        return self.take(length).decode("utf-8", "replace")


def _read_value(reader: _Reader, value_type: int) -> Any:
    if value_type in _FIXED:
        fmt, size = _FIXED[value_type]
        return reader.scalar(fmt, size)
    if value_type == _STRING:
        return reader.string()
    if value_type == _ARRAY:
        item_type = reader.scalar("<I", 4)
        count = reader.scalar("<Q", 8)
        if item_type in _FIXED:
            # Skip wholesale; array contents are never needed here.
            _, size = _FIXED[item_type]
            reader.take(size * count)
            return []
        if item_type == _STRING:
            for _ in range(count):
                reader.string()
            return []
        raise GGUFError(f"unsupported array element type {item_type}")
    raise GGUFError(f"unsupported value type {value_type}")


def read_metadata(path: Path, wanted: Sequence[str] = ("general.architecture",)) -> Dict[str, Any]:
    """Return the requested metadata keys, stopping as soon as all are found.

    Never raises for an unreadable or non-GGUF file — returns ``{}`` instead, so
    a caller can fall back rather than break model discovery over one odd file.
    """
    remaining = set(wanted)
    found: Dict[str, Any] = {}

    try:
        with open(path, "rb") as handle:
            reader = _Reader(handle)
            if reader.scalar("<I", 4) != MAGIC:
                return {}
            reader.scalar("<I", 4)  # format version
            reader.scalar("<Q", 8)  # tensor count
            pair_count = reader.scalar("<Q", 8)

            for _ in range(min(pair_count, _MAX_PAIRS)):
                key = reader.string()
                value = _read_value(reader, reader.scalar("<I", 4))
                if key in remaining:
                    found[key] = value
                    remaining.discard(key)
                    if not remaining:
                        break
    except (OSError, struct.error, GGUFError, ValueError, MemoryError):
        return found

    return found


def architecture(path: Path) -> Optional[str]:
    """``general.architecture`` for a GGUF file, or None if unreadable."""
    value = read_metadata(path).get("general.architecture")
    return str(value).lower() if isinstance(value, str) else None


#: llama.cpp writes vision projectors with this architecture. They are a
#: companion to a multimodal model, never something to run on their own.
PROJECTOR_ARCHITECTURES = frozenset({"clip"})

GENERATIVE = "generative"
EMBEDDING = "embedding"
PROJECTOR = "projector"
UNKNOWN = "unknown"


def classify(path: Path) -> str:
    """What kind of model a GGUF file holds.

    Decided from metadata rather than the filename. A name-based rule would
    hide any legitimate model whose filename happened to contain "embed", and a
    model silently missing from the picker is harder to diagnose than one that
    fails when run.

    ``UNKNOWN`` is returned when the header cannot be read, and callers should
    treat that as runnable — only positive evidence should exclude a model.
    """
    arch = architecture(path)
    if arch is None:
        return UNKNOWN
    if arch in PROJECTOR_ARCHITECTURES:
        return PROJECTOR

    # Embedding models declare a pooling strategy; generative ones do not.
    # Checked in preference to an architecture blocklist, which would need
    # updating for every new BERT variant.
    if f"{arch}.pooling_type" in read_metadata(path, (f"{arch}.pooling_type",)):
        return EMBEDDING

    return GENERATIVE
