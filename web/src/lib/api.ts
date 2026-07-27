/** Typed client for the LM-Gambit Python API. */

export interface ProviderSummary {
  name: string
  is_default: boolean
}

export interface ModelSummary {
  id: string
  display_name: string
}

export interface TestPrompt {
  filename: string
  title: string
  prompt: string
}

export interface TestSuite {
  tests: TestPrompt[]
  directory: string
}

export interface RunMetrics {
  tokens_per_second: number
  total_tokens: number
  time_to_first_token: number
  stop_reason: string
}

export interface RunSummary {
  average_tokens_per_second: number
  average_time_to_first_token: number
  total_tokens: number
  passed: number
  failed: number
  overall_score: number | null
  graded: number
}

/** One plugin's verdict on one answer. */
export interface GradeResult {
  grader: string
  score: number
  label: string
  notes: string
}

export interface PluginSummary {
  name: string
  slug: string
  version: string
  description: string
  path: string
  enabled: boolean
  hooks: string[]
  error: string | null
}

export type RunStatus = 'running' | 'completed' | 'failed' | 'cancelled'

export interface Run {
  id: string
  status: RunStatus
  provider: string
  model_id: string
  model_label: string
  temperature: number
  total: number
  completed: number
  started_at: number
  finished_at: number | null
  report_name: string | null
  error: string | null
  summary: RunSummary
}

export interface ReportSummary {
  name: string
  model_label: string
  size_bytes: number
  modified_at: number
}

export interface ReportDetail extends ReportSummary {
  content: string
}

export interface ModelPathEntry {
  nickname: string
  path: string
}

export interface Settings {
  default_provider: string
  default_temperature: number
  local_model_paths: ModelPathEntry[]
  tests_dir: string
  results_dir: string
  models_dir: string
}

export interface SystemInfo {
  version: string
  engine_architecture: string
  engine_runtime: string
  template_ok: boolean
  python_version: string
  metrics: Record<string, string>
}

export interface PlaygroundResult {
  response: string | null
  error: string | null
  metrics: RunMetrics | null
  elapsed: number
}

/* ------------------------------------------------------------------ events */

export interface TestCompletedEvent {
  type: 'test.completed'
  index: number
  total: number
  title: string
  filename: string
  status: 'ok' | 'error'
  elapsed: number
  response: string | null
  error: string | null
  metrics: RunMetrics | null
  grades: GradeResult[]
  score: number | null
}

export interface RunStartedEvent {
  type: 'run.started'
  run: Run
  tests: { index: number; title: string; filename: string }[]
}

export interface RunTerminalEvent {
  type: 'run.completed' | 'run.failed' | 'run.cancelled'
  run: Run
  message?: string
}

export type RunEvent = RunStartedEvent | TestCompletedEvent | RunTerminalEvent

/* ------------------------------------------------------------------ client */

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
      ...init,
    })
  } catch {
    throw new ApiError('Cannot reach the LM-Gambit server. Is it still running?', 0)
  }

  if (response.status === 204) return undefined as T

  const raw = await response.text()
  let payload: unknown = null
  if (raw) {
    try {
      payload = JSON.parse(raw)
    } catch {
      payload = raw
    }
  }

  if (!response.ok) {
    const detail =
      payload && typeof payload === 'object' && 'detail' in payload
        ? (payload as { detail: unknown }).detail
        : payload
    throw new ApiError(
      typeof detail === 'string' ? detail : `Request failed (${response.status})`,
      response.status,
    )
  }

  return payload as T
}

export const api = {
  system: () => request<SystemInfo>('/system'),

  providers: () => request<ProviderSummary[]>('/providers'),
  models: (provider: string) =>
    request<{ provider: string; models: ModelSummary[] }>(
      `/providers/${encodeURIComponent(provider)}/models`,
    ),

  tests: () => request<TestSuite>('/tests'),
  saveTests: (prompts: string[]) =>
    request<TestSuite>('/tests', {
      method: 'PUT',
      body: JSON.stringify({ tests: prompts.map((prompt) => ({ prompt })) }),
    }),

  startRun: (body: {
    provider: string
    model_id: string
    temperature: number
    filenames?: string[]
  }) => request<Run>('/runs', { method: 'POST', body: JSON.stringify(body) }),
  runs: () => request<Run[]>('/runs'),
  activeRun: () => request<Run | null>('/runs/active'),
  cancelRun: (id: string) => request<Run>(`/runs/${id}/cancel`, { method: 'POST' }),

  reports: () => request<ReportSummary[]>('/reports'),
  report: (name: string) => request<ReportDetail>(`/reports/${encodeURIComponent(name)}`),
  deleteReport: (name: string) =>
    request<void>(`/reports/${encodeURIComponent(name)}`, { method: 'DELETE' }),

  playground: (body: {
    provider: string
    model_id: string
    prompt: string
    temperature: number
  }) => request<PlaygroundResult>('/playground', { method: 'POST', body: JSON.stringify(body) }),

  plugins: () => request<PluginSummary[]>('/plugins'),
  reloadPlugins: () => request<PluginSummary[]>('/plugins/reload', { method: 'POST' }),

  settings: () => request<Settings>('/settings'),
  saveSettings: (body: {
    default_provider?: string
    default_temperature?: number
    local_model_paths?: ModelPathEntry[]
  }) => request<Settings>('/settings', { method: 'PUT', body: JSON.stringify(body) }),
}

/** Subscribe to a run's server-sent event feed. Returns an unsubscribe fn. */
export function subscribeToRun(
  runId: string,
  onEvent: (event: RunEvent) => void,
  onError?: () => void,
): () => void {
  const source = new EventSource(`/api/runs/${runId}/events`)

  const handle = (raw: MessageEvent) => {
    try {
      onEvent(JSON.parse(raw.data) as RunEvent)
    } catch {
      /* ignore malformed frames */
    }
  }

  for (const name of [
    'run.started',
    'test.completed',
    'run.completed',
    'run.failed',
    'run.cancelled',
  ]) {
    source.addEventListener(name, handle as EventListener)
  }

  source.onerror = () => {
    // The server closes the stream once a run reaches a terminal state, which
    // EventSource reports as an error. Only surface it while still connecting.
    if (source.readyState === EventSource.CLOSED) onError?.()
  }

  return () => source.close()
}
