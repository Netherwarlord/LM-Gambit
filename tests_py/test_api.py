"""The suites HTTP API, including every read-only guard.

Needs a running server (``python app.py``) and the ``requests`` package, which
the LM Studio provider already depends on. Skips cleanly if the server is not
up rather than reporting a failure, so ``run_all.py`` stays useful offline.

Read-only enforcement is asserted at the API, not in the UI: a disabled button
is a courtesy, a 409 is the actual protection.
"""

from __future__ import annotations

import shutil
import sys

from _harness import ROOT, Results, server_available

BASE = "http://localhost:8765"

unavailable = server_available(BASE)
if unavailable:
    print(f"\nSKIP  suites API — {unavailable}")
    print("      start the server with 'python app.py' to run these.")
    raise SystemExit(0)

import requests  # noqa: E402  (guarded by server_available above)

r = Results("Suites API")


def get(path):
    return requests.get(BASE + path, timeout=20)


def post(path, **kw):
    return requests.post(BASE + path, timeout=20, **kw)


def put(path, **kw):
    return requests.put(BASE + path, timeout=20, **kw)


def delete(path):
    return requests.delete(BASE + path, timeout=20)


# Clear anything a previous interrupted run left behind.
for leftover in ("scratch-suite", "language-copy", "renamed-suite"):
    shutil.rmtree(ROOT / "tests" / leftover, ignore_errors=True)

r.section("listing")
listing = get("/api/suites")
suites = listing.json()
r.equal("GET /api/suites", listing.status_code, 200)
r.check("five built-in suites", len(suites) == 5 and all(s["builtin"] for s in suites),
        [s["slug"] for s in suites])
r.equal("question counts", [s["count"] for s in suites], [6, 6, 6, 4, 4])

detail = get("/api/suites/math-code")
r.equal("GET one suite", detail.status_code, 200)
r.check("question ids are qualified",
        all(t["id"].startswith("math-code/") for t in detail.json()["tests"]))
r.equal("unknown suite is 404", get("/api/suites/does-not-exist").status_code, 404)

r.section("built-ins are read-only, enforced by the API")
r.equal("rename", put("/api/suites/safety", json={"name": "X"}).status_code, 409)
r.equal("delete", delete("/api/suites/safety").status_code, 409)
r.equal("replace questions",
        put("/api/suites/safety/tests", json={"tests": [{"prompt": "hi"}]}).status_code, 409)

r.section("the legacy /api/tests alias is gone")
r.equal("GET", get("/api/tests").status_code, 404)
r.check("PUT", put("/api/tests", json={"tests": [{"prompt": "x"}]}).status_code in (404, 405))

r.section("custom suite lifecycle")
created = post("/api/suites", json={"name": "Scratch Suite", "description": "d"})
r.equal("create", created.status_code, 201)
slug = created.json()["slug"] if created.status_code == 201 else "scratch-suite"
r.equal("name is slugified", slug, "scratch-suite")
r.equal("a reserved slug is refused",
        post("/api/suites", json={"name": "Safety", "slug": "safety"}).status_code, 400)
r.equal("a duplicate name is refused",
        post("/api/suites", json={"name": "Scratch Suite"}).status_code, 400)

saved = put(f"/api/suites/{slug}/tests", json={"tests": [{"prompt": "Q one"}, {"prompt": "Q two"}]})
r.equal("save questions", saved.status_code, 200)
r.equal("two questions stored", len(saved.json()["tests"]), 2)
r.equal("a whitespace-only question is refused",
        put(f"/api/suites/{slug}/tests",
            json={"tests": [{"prompt": "a"}, {"prompt": "   "}]}).status_code, 400)
r.equal("an empty-string question is refused",
        put(f"/api/suites/{slug}/tests",
            json={"tests": [{"prompt": "a"}, {"prompt": ""}]}).status_code, 422)
r.equal("rename", put(f"/api/suites/{slug}", json={"name": "Renamed Suite"}).status_code, 200)

r.section("duplicate a built-in into an editable copy")
copy = post("/api/suites/language/duplicate", json={"name": "Language Copy"})
r.equal("duplicate", copy.status_code, 201)
copy_slug = copy.json()["slug"] if copy.status_code == 201 else "language-copy"
r.check("the copy is custom", copy.json().get("builtin") is False)
r.equal("all six questions copied", len(copy.json().get("tests", [])), 6)
r.equal("the copy is editable",
        put(f"/api/suites/{copy_slug}/tests", json={"tests": [{"prompt": "edited"}]}).status_code, 200)
r.check("the original is untouched", get("/api/suites/language").json()["count"] == 6)

r.section("run selection")
bare = post("/api/runs", json={"provider": "Local Engine", "model_id": "x",
                               "filenames": ["test1.txt"]})
r.check("a bare filename is refused as ambiguous",
        bare.status_code == 400 and "ambiguous" in bare.text, bare.text[:110])
r.equal("an unknown suite is refused",
        post("/api/runs", json={"provider": "Local Engine", "model_id": "x",
                                "selections": [{"suite": "nope"}]}).status_code, 400)

r.section("cleanup")
r.equal("delete the scratch suite", delete(f"/api/suites/{slug}").status_code, 204)
r.equal("delete the copy", delete(f"/api/suites/{copy_slug}").status_code, 204)
r.equal("back to five suites", len(get("/api/suites").json()), 5)

sys.exit(r.finish())
