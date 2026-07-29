"""HTTP surface for the LM-Gambit frontend."""

from __future__ import annotations

import asyncio
import platform
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from . import __version__
from .core_bridge import (
    DEFAULT_PROVIDER_NAME,
    DEFAULT_TEMPERATURE,
    MODELS_DIR,
    RESULTS_DIR,
    TEMPLATE_PATH,
    TESTS_DIR,
    EngineLoadError,
    ProviderError,
    build_provider,
    detect_architecture,
    engine_warning,
    gpu_offload_supported,
    list_provider_names,
    load_engine_class,
    load_settings,
    save_settings,
)
from .plugins import get_plugin_manager
from .run_manager import run_manager
from .schemas import (
    PluginSummary,
    ModelListResponse,
    ModelPathEntry,
    ModelSummary,
    PlaygroundRequest,
    PlaygroundResponse,
    ProviderSummary,
    ReportDetail,
    ReportSummary,
    RunRequest,
    RunResponse,
    SaveSuiteRequest,
    SettingsResponse,
    SettingsUpdate,
    SuiteCreateRequest,
    SuiteDetail,
    SuiteDuplicateRequest,
    SuiteSummary,
    SuiteUpdateRequest,
    SystemInfo,
    TestPrompt,
)
from .suite import (
    ReadOnlySuiteError,
    SuiteError,
    create_suite,
    delete_suite,
    duplicate_suite,
    get_suite,
    list_suites,
    load_suite_prompts,
    resolve_selections,
    save_suite_tests,
    update_suite,
)

router = APIRouter(prefix="/api")

_REPORT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.md$")
_REPORT_TITLE_RE = re.compile(r"^#\s*Automated Diagnostic Report:\s*(.+)$", re.MULTILINE)


# --------------------------------------------------------------------- system


@router.get("/system", response_model=SystemInfo)
async def get_system() -> SystemInfo:
    descriptor = detect_architecture()
    runtime_name = "unavailable"
    try:
        runtime_cls = load_engine_class(descriptor)
        runtime_name = getattr(runtime_cls, "name", runtime_cls.__name__)
    except EngineLoadError as exc:
        runtime_name = f"unavailable ({exc})"

    # Computed after load_engine_class above, which already imports llama_cpp,
    # so the probe costs nothing extra here.
    offload = gpu_offload_supported()

    return SystemInfo(
        version=__version__,
        engine_architecture=descriptor.architecture,
        engine_runtime=runtime_name,
        engine_gpu_offload=offload,
        engine_warning=engine_warning(descriptor, offload=offload),
        template_ok=TEMPLATE_PATH.exists(),
        python_version=platform.python_version(),
        metrics={
            "platform": f"{platform.system()} {platform.machine()}",
            "models_dir": str(MODELS_DIR),
        },
    )


# -------------------------------------------------------------------- plugins


@router.get("/plugins", response_model=List[PluginSummary])
async def get_plugins() -> List[PluginSummary]:
    """Everything discovered in plugins/, including files that failed to load."""
    return [PluginSummary(**vars(info)) for info in get_plugin_manager().info()]


@router.get("/plugins/ui")
async def get_plugin_ui() -> dict:
    """The interface plugins declare: nav entries, pages and slot panels.

    The frontend renders straight from this, which is why installing a plugin
    never requires rebuilding the UI.
    """
    return get_plugin_manager().ui_manifest()


@router.post("/plugins/reload", response_model=List[PluginSummary])
async def reload_plugins_endpoint() -> List[PluginSummary]:
    """Re-scan plugins/. Newly added HTTP routes still need a server restart."""
    if run_manager.active() is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="A run is in progress. Reload plugins once it finishes.",
        )
    manager = get_plugin_manager()
    manager.load()
    return [PluginSummary(**vars(info)) for info in manager.info()]


# ------------------------------------------------------------------ providers


@router.get("/providers", response_model=List[ProviderSummary])
async def get_providers() -> List[ProviderSummary]:
    settings = load_settings()
    preferred = str(settings.get("default_provider") or DEFAULT_PROVIDER_NAME)
    return [
        ProviderSummary(name=name, is_default=name == preferred)
        for name in list_provider_names()
    ]


@router.get("/providers/{provider_name}/models", response_model=ModelListResponse)
async def get_models(provider_name: str) -> ModelListResponse:
    def _load() -> List[ModelSummary]:
        provider = build_provider(provider_name)
        return [
            ModelSummary(id=model.id, display_name=model.display_name)
            for model in provider.list_models()
        ]

    try:
        models = await asyncio.to_thread(_load)
    except ProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - engine/hardware faults reach the UI
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc

    return ModelListResponse(provider=provider_name, models=models)


# ---------------------------------------------------------------- test suite


def _as_prompt(entry: Dict[str, str]) -> TestPrompt:
    return TestPrompt(
        filename=entry["filename"],
        title=entry["title"],
        prompt=entry["prompt"],
        suite=entry.get("suite", ""),
        id=entry.get("id", ""),
    )


def _summary(suite) -> SuiteSummary:
    return SuiteSummary(
        slug=suite.slug,
        name=suite.name,
        description=suite.description,
        order=suite.order,
        builtin=suite.builtin,
        count=suite.count,
    )


def _guard_active_run(action: str) -> None:
    if run_manager.active() is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"A run is in progress. Wait for it to finish before {action}.",
        )


@router.get("/suites", response_model=List[SuiteSummary])
async def get_suites() -> List[SuiteSummary]:
    """Every suite, built-ins first."""
    return [_summary(suite) for suite in list_suites()]


@router.get("/suites/{slug}", response_model=SuiteDetail)
async def get_suite_detail(slug: str) -> SuiteDetail:
    try:
        suite = get_suite(slug)
        tests = load_suite_prompts(slug)
    except SuiteError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return SuiteDetail(**_summary(suite).model_dump(), tests=[_as_prompt(t) for t in tests])


@router.post("/suites", response_model=SuiteDetail, status_code=status.HTTP_201_CREATED)
async def post_suite(payload: SuiteCreateRequest) -> SuiteDetail:
    try:
        suite = create_suite(payload.name, payload.description, payload.slug)
    except SuiteError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return SuiteDetail(**_summary(suite).model_dump(), tests=[])


@router.put("/suites/{slug}", response_model=SuiteDetail)
async def put_suite(slug: str, payload: SuiteUpdateRequest) -> SuiteDetail:
    try:
        suite = update_suite(slug, name=payload.name, description=payload.description)
    except ReadOnlySuiteError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SuiteError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return SuiteDetail(
        **_summary(suite).model_dump(),
        tests=[_as_prompt(t) for t in load_suite_prompts(slug)],
    )


@router.delete("/suites/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_suite(slug: str) -> None:
    _guard_active_run("deleting a suite")
    try:
        delete_suite(slug)
    except ReadOnlySuiteError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SuiteError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/suites/{slug}/tests", response_model=SuiteDetail)
async def put_suite_tests(slug: str, payload: SaveSuiteRequest) -> SuiteDetail:
    _guard_active_run("editing questions")
    try:
        tests = save_suite_tests(slug, [draft.prompt for draft in payload.tests])
        suite = get_suite(slug)
    except ReadOnlySuiteError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SuiteError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return SuiteDetail(**_summary(suite).model_dump(), tests=[_as_prompt(t) for t in tests])


@router.post(
    "/suites/{slug}/duplicate",
    response_model=SuiteDetail,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate(slug: str, payload: SuiteDuplicateRequest) -> SuiteDetail:
    """Clone any suite, built-in included, into an editable custom one.

    This is what stops read-only from being a dead end.
    """
    try:
        suite = duplicate_suite(slug, payload.name)
    except SuiteError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return SuiteDetail(
        **_summary(suite).model_dump(),
        tests=[_as_prompt(t) for t in load_suite_prompts(suite.slug)],
    )


# ----------------------------------------------------------------------- runs


@router.post("/runs", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(payload: RunRequest) -> RunResponse:
    if not TEMPLATE_PATH.exists():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Report template missing at .core/templates/test-block.md.",
        )

    try:
        prompts = resolve_selections(payload.selections, payload.filenames)
    except SuiteError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not prompts:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="No questions selected. Pick at least one suite in Testing Suites.",
        )

    def _resolve_label() -> str:
        provider = build_provider(payload.provider)
        for model in provider.list_models():
            if model.id == payload.model_id:
                return model.display_name
        raise ProviderError(f"Model '{payload.model_id}' not found for {payload.provider}.")

    try:
        model_label = await asyncio.to_thread(_resolve_label)
    except ProviderError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        run = run_manager.start(
            provider_name=payload.provider,
            model_id=payload.model_id,
            model_label=model_label,
            temperature=payload.temperature,
            prompts=prompts,
            loop=asyncio.get_running_loop(),
        )
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return RunResponse(**run.as_dict())


@router.get("/runs", response_model=List[RunResponse])
async def get_runs() -> List[RunResponse]:
    return [RunResponse(**run.as_dict()) for run in run_manager.history()]


@router.get("/runs/active", response_model=Optional[RunResponse])
async def get_active_run() -> Optional[RunResponse]:
    run = run_manager.active()
    return RunResponse(**run.as_dict()) if run else None


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str) -> RunResponse:
    run = run_manager.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown run id.")
    return RunResponse(**run.as_dict())


@router.get("/runs/{run_id}/events")
async def stream_run(run_id: str) -> StreamingResponse:
    if run_manager.get(run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown run id.")
    return StreamingResponse(
        run_manager.stream(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/runs/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(run_id: str) -> RunResponse:
    run = run_manager.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown run id.")
    if not run_manager.cancel(run_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Run is already {run.status}.",
        )
    return RunResponse(**run.as_dict())


# -------------------------------------------------------------------- reports


def _report_path(name: str) -> Path:
    if not _REPORT_NAME_RE.match(name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid report name.")
    path = (RESULTS_DIR / name).resolve()
    if path.parent != RESULTS_DIR.resolve() or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Report not found.")
    return path


def _model_label_from(content: str, fallback: str) -> str:
    match = _REPORT_TITLE_RE.search(content)
    return match.group(1).strip() if match else fallback


def _parse_report_name(stem: str) -> tuple:
    """Pull ``(suite_scope, question_count)`` out of a report filename.

    Names look like ``<model>__<timestamp>__<scope>__<n>q``. Reports written
    before that scheme return ``("", None)`` rather than a guess — claiming a
    scope for a file that never recorded one is how the old flat names became
    misleading in the first place.
    """
    parts = stem.split("__")
    if len(parts) < 4:
        return "", None
    scope = parts[-2]
    match = re.fullmatch(r"(\d+)q", parts[-1])
    return scope, int(match.group(1)) if match else None


@router.get("/reports", response_model=List[ReportSummary])
async def get_reports() -> List[ReportSummary]:
    if not RESULTS_DIR.exists():
        return []

    summaries: List[ReportSummary] = []
    for path in RESULTS_DIR.glob("*.md"):
        try:
            stat = path.stat()
            head = path.read_text(encoding="utf-8", errors="replace")[:400]
        except OSError:
            continue
        scope, count = _parse_report_name(path.stem)
        summaries.append(
            ReportSummary(
                name=path.name,
                model_label=_model_label_from(head, path.stem),
                size_bytes=stat.st_size,
                modified_at=stat.st_mtime,
                suite_scope=scope,
                question_count=count,
            )
        )
    summaries.sort(key=lambda item: item.modified_at, reverse=True)
    return summaries


@router.get("/reports/{name}", response_model=ReportDetail)
async def get_report(name: str) -> ReportDetail:
    path = _report_path(name)
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        stat = path.stat()
    except OSError as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return ReportDetail(
        name=path.name,
        model_label=_model_label_from(content, path.stem),
        size_bytes=stat.st_size,
        modified_at=stat.st_mtime,
        content=content,
    )


@router.delete("/reports/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(name: str) -> None:
    path = _report_path(name)
    try:
        path.unlink()
    except OSError as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


# ----------------------------------------------------------------- playground


@router.post("/playground", response_model=PlaygroundResponse)
async def run_playground(payload: PlaygroundRequest) -> PlaygroundResponse:
    if run_manager.active() is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="A diagnostic run is in progress. The engine can only serve one at a time.",
        )

    def _execute() -> Dict[str, Any]:
        provider = build_provider(payload.provider)
        return provider.run_prompt(
            payload.model_id,
            payload.prompt,
            temperature=payload.temperature,
        )

    started = time.time()
    try:
        result = await asyncio.to_thread(_execute)
    except ProviderError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - engine faults are user-facing here
        return PlaygroundResponse(
            error=f"{type(exc).__name__}: {exc}",
            elapsed=round(time.time() - started, 2),
        )

    elapsed = round(time.time() - started, 2)
    if "error" in result:
        return PlaygroundResponse(error=str(result["error"]), elapsed=elapsed)

    return PlaygroundResponse(
        response=str(result.get("response", "")),
        metrics=result.get("metrics") or None,
        elapsed=elapsed,
    )


# ------------------------------------------------------------------- settings

_NICKNAME_KEY = "local_model_path_nicknames"


def _normalized_paths(settings: Dict[str, Any]) -> List[str]:
    """Read model paths tolerating the legacy list-of-dicts format."""
    raw = settings.get("local_model_paths", [])
    if not isinstance(raw, list):
        return []
    paths: List[str] = []
    for entry in raw:
        if isinstance(entry, str) and entry.strip():
            candidate = str(Path(entry).expanduser())
        elif isinstance(entry, dict) and str(entry.get("path", "")).strip():
            candidate = str(Path(str(entry["path"])).expanduser())
        else:
            continue
        if candidate not in paths:
            paths.append(candidate)
    return paths


def _nicknames(settings: Dict[str, Any]) -> Dict[str, str]:
    """Nicknames live in their own key so the engine's path list stays strings."""
    nicknames: Dict[str, str] = {}
    stored = settings.get(_NICKNAME_KEY)
    if isinstance(stored, dict):
        for key, value in stored.items():
            if isinstance(key, str) and isinstance(value, str):
                nicknames[str(Path(key).expanduser())] = value

    # Recover nicknames from the legacy list-of-dicts shape.
    raw = settings.get("local_model_paths", [])
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict) and entry.get("path"):
                key = str(Path(str(entry["path"])).expanduser())
                nicknames.setdefault(key, str(entry.get("nickname", "")))
    return nicknames


@router.get("/settings", response_model=SettingsResponse)
async def get_settings() -> SettingsResponse:
    settings = load_settings()
    nicknames = _nicknames(settings)
    return SettingsResponse(
        default_provider=str(settings.get("default_provider") or DEFAULT_PROVIDER_NAME),
        default_temperature=float(settings.get("default_temperature") or DEFAULT_TEMPERATURE),
        local_model_paths=[
            ModelPathEntry(nickname=nicknames.get(path, ""), path=path)
            for path in _normalized_paths(settings)
        ],
        tests_dir=str(TESTS_DIR),
        results_dir=str(RESULTS_DIR),
        models_dir=str(MODELS_DIR),
    )


@router.put("/settings", response_model=SettingsResponse)
async def put_settings(payload: SettingsUpdate) -> SettingsResponse:
    settings = load_settings()

    if payload.default_provider is not None:
        if payload.default_provider not in list_provider_names():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown provider '{payload.default_provider}'.",
            )
        settings["default_provider"] = payload.default_provider

    if payload.default_temperature is not None:
        settings["default_temperature"] = payload.default_temperature

    if payload.local_model_paths is not None:
        ordered: List[str] = []
        nicknames: Dict[str, str] = {}
        for entry in payload.local_model_paths:
            candidate = str(Path(entry.path).expanduser())
            if not candidate.strip() or candidate in ordered:
                continue
            ordered.append(candidate)
            if entry.nickname.strip():
                nicknames[candidate] = entry.nickname.strip()
        settings["local_model_paths"] = ordered
        settings[_NICKNAME_KEY] = nicknames

    save_settings(settings)
    return await get_settings()
