"""Pydantic request/response models for the LM-Gambit API."""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ProviderSummary(BaseModel):
    name: str
    is_default: bool = False


class ModelSummary(BaseModel):
    id: str
    display_name: str


class ModelListResponse(BaseModel):
    provider: str
    models: List[ModelSummary]


class TestPrompt(BaseModel):
    """A single question in the suite.

    ``title`` is derived from the first non-empty line of ``prompt`` by the
    engine, so it is read-only here and returned for display purposes only.
    """

    filename: str
    title: str
    prompt: str
    #: Owning suite slug, and the globally unique "<suite>/<file>" ID.
    #: ``filename`` repeats across suites; ``id`` never does.
    suite: str = ""
    id: str = ""


class TestDraft(BaseModel):
    """One question as submitted by the suite builder form."""

    prompt: str = Field(min_length=1)


class SaveSuiteRequest(BaseModel):
    tests: List[TestDraft]


# ------------------------------------------------------------------- suites


class SuiteSummary(BaseModel):
    slug: str
    name: str
    description: str = ""
    order: int = 100
    builtin: bool = False
    count: int = 0


class SuiteDetail(SuiteSummary):
    tests: List[TestPrompt] = Field(default_factory=list)


class SuiteCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = ""
    slug: Optional[str] = None


class SuiteUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    description: Optional[str] = None


class SuiteDuplicateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)


class RunSelection(BaseModel):
    """Questions to draw from one suite. Empty ``filenames`` means all of it."""

    suite: str
    filenames: Optional[List[str]] = None


class RunMetrics(BaseModel):
    tokens_per_second: float = 0.0
    total_tokens: int = 0
    time_to_first_token: float = 0.0
    stop_reason: str = "N/A"


class RunRequest(BaseModel):
    provider: str
    model_id: str
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    selections: Optional[List[RunSelection]] = Field(
        default=None,
        description=(
            "Suites to run, in order, each optionally narrowed to a subset of "
            "its questions. Omit to run every built-in suite."
        ),
    )
    filenames: Optional[List[str]] = Field(
        default=None,
        description=(
            "Deprecated. Qualified '<suite>/<file>' IDs. Bare filenames are "
            "rejected because they are ambiguous across suites. Prefer 'selections'."
        ),
    )


class RunSummary(BaseModel):
    average_tokens_per_second: float = 0.0
    average_time_to_first_token: float = 0.0
    total_tokens: int = 0
    passed: int = 0
    failed: int = 0
    overall_score: Optional[float] = None
    graded: int = 0


class PluginSummary(BaseModel):
    name: str
    slug: str
    version: str
    description: str
    path: str
    enabled: bool
    hooks: List[str] = []
    error: Optional[str] = None


class RunResponse(BaseModel):
    id: str
    status: str
    provider: str
    model_id: str
    model_label: str
    temperature: float
    total: int
    completed: int
    started_at: float
    finished_at: Optional[float] = None
    report_name: Optional[str] = None
    error: Optional[str] = None
    summary: RunSummary = RunSummary()


class PlaygroundRequest(BaseModel):
    provider: str
    model_id: str
    prompt: str = Field(min_length=1)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)


class PlaygroundResponse(BaseModel):
    response: Optional[str] = None
    error: Optional[str] = None
    metrics: Optional[RunMetrics] = None
    elapsed: float = 0.0


class ReportSummary(BaseModel):
    name: str
    model_label: str
    size_bytes: int
    modified_at: float


class ReportDetail(ReportSummary):
    content: str


class ModelPathEntry(BaseModel):
    nickname: str = ""
    path: str


class SettingsResponse(BaseModel):
    default_provider: str
    default_temperature: float
    local_model_paths: List[ModelPathEntry]
    tests_dir: str
    results_dir: str
    models_dir: str


class SettingsUpdate(BaseModel):
    default_provider: Optional[str] = None
    default_temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    local_model_paths: Optional[List[ModelPathEntry]] = None


class SystemInfo(BaseModel):
    version: str
    engine_architecture: str
    engine_runtime: str
    template_ok: bool
    python_version: str
    metrics: Dict[str, str] = {}
