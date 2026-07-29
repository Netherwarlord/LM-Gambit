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
  /** Owning suite slug. */
  suite: string
  /** Globally unique "<suite>/<file>". `filename` repeats across suites. */
  id: string
}

export interface SuiteSummary {
  slug: string
  name: string
  description: string
  order: number
  builtin: boolean
  count: number
}

export interface SuiteDetail extends SuiteSummary {
  tests: TestPrompt[]
}

/** One suite's contribution to a run; omit `filenames` to take all of it. */
export interface RunSelection {
  suite: string
  filenames?: string[]
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

/* -------------------------------------------------------- plugin-declared UI */
/* Plugins describe interface as data; this app renders it. Nothing here is
 * plugin-supplied code — see /docs for the contribution vocabulary. */

export interface PluginStat {
  label: string
  value: string | number
  hint: string
  tone: 'default' | 'good' | 'warn' | 'bad'
}

export interface StatRowBlock {
  kind: 'stat_row'
  stats: PluginStat[]
  source: string | null
}

export interface TableBlock {
  kind: 'table'
  columns: string[]
  rows: (string | number)[][]
  source: string | null
  empty: string
}

export interface MarkdownBlock {
  kind: 'markdown'
  text: string
  source: string | null
}

export interface ActionBlock {
  kind: 'action'
  label: string
  post: string
  confirm: string | null
  style: 'primary' | 'ghost' | 'danger'
  icon: string | null
}

export interface PanelBlock {
  kind: 'panel'
  title: string
  subtitle: string
  blocks: PluginBlock[]
}

export type PluginBlock = StatRowBlock | TableBlock | MarkdownBlock | ActionBlock | PanelBlock

export interface PluginNavItem {
  slug: string
  label: string
  path: string
  icon: string
  hint: string
  order: number
}

export interface PluginPageSpec {
  slug: string
  plugin: string
  path: string
  title: string
  subtitle: string
  blocks: PluginBlock[]
}

export interface PluginSlotPanel {
  slug: string
  plugin: string
  order: number
  panel: PanelBlock
}

export interface PluginUIManifest {
  nav: PluginNavItem[]
  pages: PluginPageSpec[]
  slots: Record<string, PluginSlotPanel[]>
}

/** Plugin data URLs are confined to this app's own plugin namespace. */
function assertPluginUrl(url: string): string {
  if (!url.startsWith('/api/plugins/')) {
    throw new ApiError(`Refusing to call ${url} — plugin URLs must start with /api/plugins/.`, 0)
  }
  return url
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
  /** Which suites the run covered. Empty for reports predating the scheme. */
  suite_scope: string
  /** How many questions it actually ran. Null for legacy reports. */
  question_count: number | null
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
  /** Whether the installed llama-cpp-python was built with GPU offload.
   *  null when llama-cpp-python is missing or too old to report it — which is
   *  distinct from a confirmed false. */
  engine_gpu_offload: boolean | null
  /** Set when detected hardware and the installed build disagree. */
  engine_warning: string | null
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

  suites: () => request<SuiteSummary[]>('/suites'),
  suite: (slug: string) => request<SuiteDetail>(`/suites/${encodeURIComponent(slug)}`),
  createSuite: (body: { name: string; description?: string; slug?: string }) =>
    request<SuiteDetail>('/suites', { method: 'POST', body: JSON.stringify(body) }),
  updateSuite: (slug: string, body: { name?: string; description?: string }) =>
    request<SuiteDetail>(`/suites/${encodeURIComponent(slug)}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  deleteSuite: (slug: string) =>
    request<void>(`/suites/${encodeURIComponent(slug)}`, { method: 'DELETE' }),
  saveSuiteTests: (slug: string, prompts: string[]) =>
    request<SuiteDetail>(`/suites/${encodeURIComponent(slug)}/tests`, {
      method: 'PUT',
      body: JSON.stringify({ tests: prompts.map((prompt) => ({ prompt })) }),
    }),
  duplicateSuite: (slug: string, name?: string) =>
    request<SuiteDetail>(`/suites/${encodeURIComponent(slug)}/duplicate`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),

  startRun: (body: {
    provider: string
    model_id: string
    temperature: number
    /** Suites to run, each optionally narrowed to some of its questions. */
    selections?: RunSelection[]
    /** Deprecated: flat qualified "<suite>/<file>" IDs. Prefer `selections`. */
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
  pluginUI: () => request<PluginUIManifest>('/plugins/ui'),

  /** Read a block's `source`. The URL comes from a plugin, so it is checked. */
  pluginData: <T>(url: string) => request<T>(assertPluginUrl(url).replace(/^\/api/, '')),
  /** Fire an Action button. May return a message to toast and a refresh flag. */
  pluginAction: (url: string) =>
    request<{ message?: string; refresh?: boolean }>(assertPluginUrl(url).replace(/^\/api/, ''), {
      method: 'POST',
      body: '{}',
    }),

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
