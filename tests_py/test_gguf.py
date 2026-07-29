"""GGUF header parsing and model classification, including malformed input.

Guards the model picker: vision projectors and embedding models are valid GGUF
files that cannot answer a prompt, and selecting one used to produce an empty
report with no error at all.
"""

from __future__ import annotations

import struct
import tempfile
from pathlib import Path

from _harness import Results, bootstrap

bootstrap()
from gguf import (  # noqa: E402
    EMBEDDING, GENERATIVE, MAGIC, PROJECTOR, UNKNOWN,
    architecture, classify, read_metadata,
)

r = Results("GGUF parsing and classification")


def synth(pairs, tmp: str, magic: int = MAGIC) -> Path:
    """Write a minimal GGUF file with the given (key, type, value) triples."""
    out = bytearray(struct.pack("<IIQQ", magic, 3, 0, len(pairs)))
    for key, vtype, value in pairs:
        kb = key.encode()
        out += struct.pack("<Q", len(kb)) + kb + struct.pack("<I", vtype)
        if vtype == 8:                                  # string
            vb = value.encode()
            out += struct.pack("<Q", len(vb)) + vb
        elif vtype == 4:                                # uint32
            out += struct.pack("<I", value)
        elif vtype == 9:                                # array of uint32
            out += struct.pack("<IQ", 4, len(value))
            for item in value:
                out += struct.pack("<I", item)
    path = Path(tmp) / f"{abs(hash(str(pairs))) % 10**8}.gguf"
    path.write_bytes(bytes(out))
    return path


with tempfile.TemporaryDirectory() as tmp:
    r.section("classification from metadata, not filename")
    generative = synth([("general.architecture", 8, "llama"),
                        ("llama.block_count", 4, 32)], tmp)
    r.equal("generative model", classify(generative), GENERATIVE)

    embedding = synth([("general.architecture", 8, "bert"),
                       ("bert.block_count", 4, 12),
                       ("bert.pooling_type", 4, 1)], tmp)
    r.equal("embedding model, detected by pooling_type", classify(embedding), EMBEDDING)

    projector = synth([("general.architecture", 8, "clip")], tmp)
    r.equal("vision projector, detected by clip architecture", classify(projector), PROJECTOR)

    r.section("value skipping")
    with_array = synth([("general.architecture", 8, "llama"),
                        ("llama.some_list", 9, [1, 2, 3, 4, 5]),
                        ("llama.block_count", 4, 32)], tmp)
    r.equal("a key after an array is still reachable",
            read_metadata(with_array, ("llama.block_count",)).get("llama.block_count"), 32)

    r.section("malformed input degrades, never raises")
    r.equal("wrong magic", classify(synth([("general.architecture", 8, "llama")], tmp,
                                          magic=0xDEADBEEF)), UNKNOWN)

    truncated = Path(tmp) / "truncated.gguf"
    truncated.write_bytes(struct.pack("<IIQQ", MAGIC, 3, 0, 99) + b"\x05\x00")
    r.equal("truncated mid-header", classify(truncated), UNKNOWN)

    empty = Path(tmp) / "empty.gguf"
    empty.write_bytes(b"")
    r.equal("empty file", classify(empty), UNKNOWN)
    r.equal("missing file", classify(Path(tmp) / "absent.gguf"), UNKNOWN)
    r.equal("non-GGUF file", classify(Path(__file__)), UNKNOWN)

r.section("real models, if any are installed")
real = sorted(Path.home().joinpath(".lmstudio/models").rglob("*.gguf"))
if not real:
    print("  SKIP  no local models found under ~/.lmstudio/models")
else:
    kinds = {path.name: classify(path) for path in real}
    projectors = [n for n, k in kinds.items() if k == PROJECTOR]
    generatives = [n for n, k in kinds.items() if k == GENERATIVE]
    r.check("every mmproj-* file classifies as a projector",
            projectors and all(n.startswith("mmproj-") for n in projectors), projectors)
    r.check("no generative model is an mmproj-*",
            not any(n.startswith("mmproj-") for n in generatives), generatives)
    r.check("architecture readable for every real file",
            all(architecture(path) for path in real))

raise SystemExit(r.finish())
