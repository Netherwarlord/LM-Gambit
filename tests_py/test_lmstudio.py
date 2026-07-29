"""LM Studio model listing: filter what cannot generate, keep the rest.

Stubbed HTTP, so the suite runs without LM Studio. The shapes were confirmed
against a live server (LM Studio 0.3.x): ``/api/v0/models`` reports
``type`` as ``llm``, ``vlm`` or ``embeddings``, while ``/v1/models`` returns
the same models with no ``type`` field at all — which is precisely why an
embedding model used to be selectable.

The rule mirrors the local-engine filter: exclude only on positive evidence.
The OpenAI-compatible endpoint carries no type information, so nothing is
filtered there — guessing from the model id would hide legitimate models.
"""

from __future__ import annotations

import json
from typing import Any

from _harness import Results, bootstrap

bootstrap()
import providers.lmstudio as lmstudio  # noqa: E402
from providers.base import ProviderError  # noqa: E402

r = Results("LM Studio model listing")


class FakeResponse:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise lmstudio.requests.exceptions.HTTPError(f"status {self.status_code}")

    def json(self) -> Any:
        if isinstance(self._payload, str):
            raise json.JSONDecodeError("bad", self._payload, 0)
        return self._payload


def with_routes(routes: dict):
    """Stub requests.get so each URL returns a canned response or raises."""
    def fake_get(url: str, **_kw):
        for fragment, outcome in routes.items():
            if fragment in url:
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        raise lmstudio.requests.exceptions.ConnectionError(f"no route for {url}")
    return fake_get


NATIVE = "/api/v0/models"
OPENAI = "/v1/models"
MISSING = lmstudio.requests.exceptions.HTTPError("404")

original_get = lmstudio.requests.get
provider = lmstudio.LMStudioProvider()

try:
    r.section("native endpoint states each model's type")
    lmstudio.requests.get = with_routes({
        NATIVE: FakeResponse({"data": [
            {"id": "qwen3-8b", "type": "llm"},
            {"id": "gemma-vision", "type": "vlm"},
            {"id": "text-embedding-nomic-embed-text-v1.5", "type": "embeddings"},
        ]}),
    })
    ids = [m.id for m in provider.list_models()]
    r.equal("embedding model excluded", ids, ["qwen3-8b", "gemma-vision"])
    r.check("vision-language models are kept — they can answer prompts",
            "gemma-vision" in ids)

    r.section("unknown or missing type is kept, not guessed at")
    lmstudio.requests.get = with_routes({
        NATIVE: FakeResponse({"data": [
            {"id": "mystery-model"},
            {"id": "future-type", "type": "something-new"},
            {"id": "embedder", "type": "embeddings"},
        ]}),
    })
    ids = [m.id for m in provider.list_models()]
    r.equal("only the known non-generative type is dropped",
            ids, ["mystery-model", "future-type"])

    r.section("a model id containing 'embed' is not itself evidence")
    lmstudio.requests.get = with_routes({
        NATIVE: FakeResponse({"data": [{"id": "embedded-reasoning-7b", "type": "llm"}]}),
    })
    r.equal("kept, because its declared type says it generates",
            [m.id for m in provider.list_models()], ["embedded-reasoning-7b"])

    r.section("falls back when the native endpoint is unavailable")
    lmstudio.requests.get = with_routes({
        NATIVE: MISSING,
        OPENAI: FakeResponse({"data": [{"id": "some-model"}, {"id": "another"}]}),
    })
    r.equal("uses the OpenAI-compatible list",
            [m.id for m in provider.list_models()], ["some-model", "another"])

    lmstudio.requests.get = with_routes({
        NATIVE: FakeResponse({"data": []}),
        OPENAI: FakeResponse({"data": [{"id": "only-here"}]}),
    })
    r.equal("an empty native list also falls back",
            [m.id for m in provider.list_models()], ["only-here"])

    lmstudio.requests.get = with_routes({
        NATIVE: FakeResponse("not json"),
        OPENAI: FakeResponse({"data": [{"id": "recovered"}]}),
    })
    r.equal("unparseable native response falls back",
            [m.id for m in provider.list_models()], ["recovered"])

    r.section("errors say something useful")
    lmstudio.requests.get = with_routes({
        NATIVE: FakeResponse({"data": [{"id": "only-an-embedder", "type": "embeddings"}]}),
    })
    try:
        provider.list_models()
        r.check("all-embeddings raises", False, "no error raised")
    except ProviderError as exc:
        r.check("all-embeddings explains why the list is empty",
                "embedding" in str(exc).lower(), str(exc))

    lmstudio.requests.get = with_routes({NATIVE: MISSING, OPENAI: MISSING})
    try:
        provider.list_models()
        r.check("unreachable server raises", False, "no error raised")
    except ProviderError as exc:
        r.check("unreachable server names LM Studio", "LM Studio" in str(exc), str(exc))

    r.section("existing behaviour preserved")
    lmstudio.requests.get = with_routes({
        NATIVE: MISSING,
        OPENAI: FakeResponse({"data": [{"id": "listed"}], "default_model": "the-default"}),
    })
    ids = [m.id for m in provider.list_models()]
    r.equal("a default model not in the list is still prepended",
            ids, ["the-default", "listed"])

finally:
    lmstudio.requests.get = original_get

raise SystemExit(r.finish())
