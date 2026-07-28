import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Ban,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleSlash,
  Clock,
  FileText,
  ListChecks,
  Play,
  RefreshCw,
  Terminal,
  TriangleAlert,
  Zap,
} from 'lucide-react'
import {
  Card,
  CardHeader,
  EmptyState,
  ErrorNote,
  PageHeader,
  Spinner,
  StatTile,
  TemperatureSlider,
  useAsync,
  useToast,
} from '../components/ui'
import { Markdown } from '../components/Markdown'
import { ScoreBadge, scoreTone } from '../components/ScoreBadge'
import { PluginSlot } from '../components/PluginBlocks'
import {
  SuitePicker,
  countSelected,
  selectionsFrom,
  useDefaultPicks,
} from '../components/SuitePicker'
import { Link } from '../lib/router'
import { api, ApiError, type TestCompletedEvent } from '../lib/api'
import { clockTime, cx, formatDuration } from '../lib/format'
import { useRunFeed } from '../hooks/useRunFeed'

export function RunPage() {
  const toast = useToast()
  const { run, outcomes, logs, starting, isLive, start, cancel, clear } = useRunFeed()

  const providers = useAsync(() => api.providers(), [])
  const suites = useAsync(() => api.suites(), [])

  const [provider, setProvider] = useState('')
  const [modelId, setModelId] = useState('')
  const [temperature, setTemperature] = useState(0.1)
  const [pickerOpen, setPickerOpen] = useState(false)

  // Seed provider + temperature from saved settings, falling back to the
  // provider the server marks as default.
  useEffect(() => {
    if (!providers.data?.length || provider) return
    api
      .settings()
      .then((settings) => {
        const preferred = providers.data?.find((p) => p.name === settings.default_provider)
        setProvider(preferred?.name ?? providers.data?.find((p) => p.is_default)?.name ?? providers.data![0].name)
        setTemperature(settings.default_temperature)
      })
      .catch(() => {
        setProvider(providers.data?.find((p) => p.is_default)?.name ?? providers.data![0].name)
      })
  }, [providers.data, provider])

  const models = useAsync(
    () => (provider ? api.models(provider) : Promise.resolve(null)),
    [provider],
  )

  useEffect(() => {
    const list = models.data?.models ?? []
    setModelId((current) => (list.some((m) => m.id === current) ? current : (list[0]?.id ?? '')))
  }, [models.data])

  const suiteList = suites.data ?? []
  const [picks, setPicks] = useDefaultPicks(suiteList)

  const selectedCount = countSelected(picks, suiteList)
  const totalCount = suiteList.reduce((sum, s) => sum + s.count, 0)
  const pickedSuites = Object.keys(picks).length

  const launch = async () => {
    if (!provider || !modelId) return
    try {
      // Sent as `selections`, so "all of a suite" stays all of it even if that
      // suite gains a question between now and the next run.
      await start({
        provider,
        model_id: modelId,
        temperature,
        selections: selectionsFrom(picks),
      })
    } catch (cause) {
      toast(cause instanceof ApiError ? cause.message : String(cause), 'error')
    }
  }

  const doCancel = async () => {
    try {
      await cancel()
    } catch (cause) {
      toast(cause instanceof ApiError ? cause.message : String(cause), 'error')
    }
  }

  const canLaunch = !!provider && !!modelId && selectedCount > 0 && !isLive && !starting

  return (
    <>
      <PageHeader
        title="Diagnostic Run"
        subtitle="Every question is sent to the model one at a time. Results stream in as each one finishes."
        actions={
          run && !isLive ? (
            <button className="btn btn-ghost" onClick={clear}>
              <RefreshCw size={14} />
              New run
            </button>
          ) : null
        }
      />

      <div className="grid gap-5 xl:grid-cols-12">
        {/* ------------------------------------------------ launch controls */}
        <div className="space-y-5 xl:col-span-4">
          <Card raised>
            <CardHeader title="Target" icon={<Zap size={14} />} />
            <div className="space-y-4 p-4">
              {providers.error && <ErrorNote message={providers.error} onRetry={providers.reload} />}

              <div>
                <label className="label" htmlFor="provider">
                  Provider
                </label>
                <select
                  id="provider"
                  className="field"
                  value={provider}
                  disabled={isLive || providers.loading}
                  onChange={(event) => setProvider(event.target.value)}
                >
                  {(providers.data ?? []).map((item) => (
                    <option key={item.name} value={item.name}>
                      {item.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <label className="label" htmlFor="model">
                    Model
                  </label>
                  <button
                    className="mb-1.5 flex items-center gap-1 text-[0.6875rem] text-ink-500 transition-colors hover:text-ember-400 disabled:opacity-50"
                    onClick={models.reload}
                    disabled={isLive || models.loading}
                  >
                    {models.loading ? <Spinner className="h-3 w-3" /> : <RefreshCw size={11} />}
                    Refresh
                  </button>
                </div>
                {models.error ? (
                  <ErrorNote message={models.error} onRetry={models.reload} />
                ) : (
                  <select
                    id="model"
                    className="field"
                    value={modelId}
                    disabled={isLive || models.loading || !models.data?.models.length}
                    onChange={(event) => setModelId(event.target.value)}
                  >
                    {models.loading && <option>Discovering models…</option>}
                    {!models.loading && !models.data?.models.length && <option>No models found</option>}
                    {(models.data?.models ?? []).map((model) => (
                      <option key={model.id} value={model.id}>
                        {model.display_name}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <TemperatureSlider value={temperature} onChange={setTemperature} disabled={isLive} />
            </div>
          </Card>

          {/* suite + question selection */}
          <Card raised>
            <CardHeader
              title="Suites"
              icon={<ListChecks size={14} />}
              actions={
                <span className="chip chip-gold num">
                  {selectedCount}/{totalCount}
                </span>
              }
            />
            <div className="p-4">
              {suites.error && <ErrorNote message={suites.error} onRetry={suites.reload} />}

              {!suites.error && suiteList.length === 0 && !suites.loading && (
                <EmptyState
                  icon={<ListChecks size={20} />}
                  title="No suites found"
                  description="Create a suite before running diagnostics."
                  action={
                    <Link to="/suite" className="btn btn-primary">
                      Open Testing Suites
                    </Link>
                  }
                />
              )}

              {suiteList.length > 0 && (
                <>
                  <div className="mb-3 flex items-center gap-2">
                    <button
                      className="btn btn-ghost btn-sm"
                      disabled={isLive}
                      onClick={() =>
                        setPicks(
                          pickedSuites === suiteList.length
                            ? {}
                            : Object.fromEntries(suiteList.map((s) => [s.slug, 'all' as const])),
                        )
                      }
                    >
                      {pickedSuites === suiteList.length ? 'Clear all' : 'Select all'}
                    </button>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => setPickerOpen((open) => !open)}
                    >
                      {pickerOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                      {pickerOpen ? 'Hide suites' : 'Choose suites'}
                    </button>
                  </div>

                  {pickerOpen ? (
                    <div className="animate-fade-in max-h-96 overflow-y-auto pr-1">
                      <SuitePicker
                        suites={suiteList}
                        picks={picks}
                        onChange={setPicks}
                        disabled={isLive}
                      />
                    </div>
                  ) : (
                    <p className="text-[0.75rem] leading-relaxed text-ink-500">
                      {selectedCount === 0
                        ? 'Nothing selected — pick at least one suite.'
                        : `${selectedCount} question${selectedCount === 1 ? '' : 's'} from ${pickedSuites} suite${pickedSuites === 1 ? '' : 's'}, run in order.`}
                    </p>
                  )}
                </>
              )}
            </div>
          </Card>

          <div className="flex gap-2">
            {isLive ? (
              <button className="btn btn-danger flex-1" onClick={doCancel}>
                <Ban size={15} />
                Cancel run
              </button>
            ) : (
              <button className="btn btn-primary flex-1" onClick={launch} disabled={!canLaunch}>
                {starting ? <Spinner /> : <Play size={15} />}
                {starting ? 'Starting…' : 'Run diagnostics'}
              </button>
            )}
          </div>

          <PluginSlot slot="run.aside" autoRefreshMs={isLive ? 4000 : undefined} />
        </div>

        {/* ------------------------------------------------------ live feed */}
        <div className="space-y-5 xl:col-span-8">
          <RunStatusPanel />
          <ResultsFeed outcomes={outcomes} live={isLive} hasRun={!!run} />
          {logs.length > 0 && <ConsoleLog />}
        </div>
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ panels */

function RunStatusPanel() {
  const { run, outcomes, isLive } = useRunFeed()

  if (!run) {
    return (
      <Card>
        <EmptyState
          icon={<Play size={20} />}
          title="Ready when you are"
          description="Pick a provider and model, choose which questions to ask, then start the run. Progress appears here live."
        />
      </Card>
    )
  }

  const percent = run.total ? Math.round((outcomes.length / run.total) * 100) : 0
  const elapsed = (run.finished_at ?? Date.now() / 1000) - run.started_at

  const statusChip = {
    running: <span className="chip chip-ember">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ember-400" />
      Running
    </span>,
    completed: <span className="chip chip-mint"><CheckCircle2 size={11} />Complete</span>,
    cancelled: <span className="chip chip-neutral"><CircleSlash size={11} />Cancelled</span>,
    failed: <span className="chip chip-rose"><TriangleAlert size={11} />Failed</span>,
  }[run.status]

  return (
    <Card raised>
      <div className="p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              {statusChip}
              <h2 className="truncate text-[0.9375rem] font-semibold text-ink-100">
                {run.model_label}
              </h2>
            </div>
            <p className="mt-0.5 text-[0.75rem] text-ink-500">
              {run.provider} · T={run.temperature} · started {clockTime(run.started_at * 1000)}
            </p>
          </div>
          {run.report_name && (
            <Link to={`/reports/${encodeURIComponent(run.report_name)}`} className="btn btn-ghost btn-sm">
              <FileText size={13} />
              Open report
            </Link>
          )}
        </div>

        {/* progress */}
        <div className="mb-4">
          <div className="mb-1.5 flex items-baseline justify-between text-[0.75rem]">
            <span className="text-ink-400">
              {outcomes.length} of {run.total} questions
            </span>
            <span className="num font-semibold text-gold-400">{percent}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-navy-800">
            <div
              className={cx(
                'h-full rounded-full transition-[width] duration-500 ease-out',
                run.status === 'failed'
                  ? 'bg-rose-500'
                  : 'bg-gradient-to-r from-ember-500 to-gold-400',
              )}
              style={{ width: `${Math.max(percent, 2)}%` }}
            />
          </div>
        </div>

        {run.error && <ErrorNote message={run.error} />}

        <div
          className={cx(
            'grid grid-cols-2 gap-2.5',
            run.summary.overall_score != null ? 'sm:grid-cols-5' : 'sm:grid-cols-4',
          )}
        >
          {run.summary.overall_score != null && (
            <StatTile
              label="Score"
              value={`${Math.round(run.summary.overall_score * 100)}%`}
              tone={scoreTone(run.summary.overall_score)}
              hint={`${run.summary.graded} graded`}
            />
          )}
          <StatTile
            label="Avg tok/s"
            value={run.summary.average_tokens_per_second.toFixed(1)}
            tone="gold"
          />
          <StatTile
            label="Avg TTFT"
            value={run.summary.average_time_to_first_token.toFixed(2)}
            unit="s"
            tone="gold"
          />
          <StatTile label="Tokens" value={run.summary.total_tokens.toLocaleString()} tone="neutral" />
          <StatTile
            label={isLive ? 'Elapsed' : 'Duration'}
            value={formatDuration(elapsed)}
            tone="neutral"
          />
        </div>

        {(run.summary.passed > 0 || run.summary.failed > 0) && (
          <div className="mt-2.5 flex items-center gap-2 text-[0.75rem]">
            <span className="chip chip-mint">
              <CheckCircle2 size={11} />
              {run.summary.passed} answered
            </span>
            {run.summary.failed > 0 && (
              <span className="chip chip-rose">
                <TriangleAlert size={11} />
                {run.summary.failed} errored
              </span>
            )}
          </div>
        )}
      </div>
    </Card>
  )
}

function ResultsFeed({
  outcomes,
  live,
  hasRun,
}: {
  outcomes: TestCompletedEvent[]
  live: boolean
  hasRun: boolean
}) {
  if (!hasRun) return null

  return (
    <Card>
      <CardHeader
        title="Results"
        icon={<ListChecks size={14} />}
        hint={live ? 'Streaming as each question completes' : undefined}
        actions={<span className="chip chip-neutral num">{outcomes.length}</span>}
      />
      {outcomes.length === 0 ? (
        <div className="flex items-center gap-2.5 px-4 py-8 text-[0.8125rem] text-ink-400">
          <Spinner className="text-ember-400" />
          Waiting on the first response — the model may need to load into memory.
        </div>
      ) : (
        <ul className="divide-y divide-navy-700/70">
          {outcomes.map((outcome) => (
            <ResultRow key={outcome.index} outcome={outcome} />
          ))}
          {live && (
            <li className="flex items-center gap-2.5 px-4 py-3.5 text-[0.8125rem] text-ink-400">
              <Spinner className="text-ember-400" />
              Running question {outcomes.length + 1}…
            </li>
          )}
        </ul>
      )}
    </Card>
  )
}

function ResultRow({ outcome }: { outcome: TestCompletedEvent }) {
  const [open, setOpen] = useState(false)
  const ok = outcome.status === 'ok'

  return (
    <li className="animate-fade-up">
      <button
        className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-navy-800/40"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span className="mt-0.5 shrink-0">
          {ok ? (
            <CheckCircle2 size={15} className="text-mint-400" />
          ) : (
            <TriangleAlert size={15} className="text-rose-400" />
          )}
        </span>

        <span className="min-w-0 flex-1">
          <span className="flex items-baseline gap-2">
            <span className="num text-[0.6875rem] text-ink-500">
              {String(outcome.index).padStart(2, '0')}
            </span>
            <span className="truncate text-[0.8125rem] font-medium text-ink-100">
              {outcome.title}
            </span>
            {outcome.score != null && (
              <span className="ml-auto shrink-0">
                <ScoreBadge
                  score={outcome.score}
                  title={outcome.grades
                    .map((g) => `${g.grader}: ${Math.round(g.score * 100)}%`)
                    .join('\n')}
                />
              </span>
            )}
          </span>
          <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.6875rem] text-ink-500">
            <span className="font-mono">{outcome.filename}</span>
            {ok && outcome.metrics && (
              <>
                <span className="num text-gold-400">
                  {outcome.metrics.tokens_per_second} tok/s
                </span>
                <span className="num">{outcome.metrics.total_tokens} tokens</span>
                <span className="num">TTFT {outcome.metrics.time_to_first_token}s</span>
                <span className="num">
                  <Clock size={9} className="mr-0.5 inline" />
                  {formatDuration(outcome.elapsed)}
                </span>
              </>
            )}
            {!ok && <span className="truncate text-rose-400">{outcome.error}</span>}
          </span>
        </span>

        <ChevronRight
          size={15}
          className={cx('mt-0.5 shrink-0 text-ink-500 transition-transform', open && 'rotate-90')}
        />
      </button>

      {open && (
        <div className="animate-fade-in border-t border-navy-700/60 bg-navy-950/40 px-4 py-3.5">
          {outcome.grades.length > 0 && (
            <div className="mb-3.5 space-y-1.5 rounded-xl border border-navy-700 bg-navy-900/50 px-3.5 py-3">
              <div className="text-[0.625rem] font-semibold tracking-[0.09em] text-ink-500 uppercase">
                Plugin grades
              </div>
              {outcome.grades.map((grade) => (
                <div key={grade.grader} className="flex items-start gap-2.5 text-[0.75rem]">
                  <ScoreBadge score={grade.score} />
                  <div className="min-w-0">
                    <span className="text-ink-200">{grade.grader}</span>
                    {grade.label && <span className="ml-1.5 text-ink-500">({grade.label})</span>}
                    {grade.notes && (
                      <div className="text-[0.6875rem] text-ink-500">{grade.notes}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          {ok ? (
            <Markdown>{outcome.response ?? '_No response body._'}</Markdown>
          ) : (
            <ErrorNote message={outcome.error ?? 'Unknown error'} />
          )}
        </div>
      )}
    </li>
  )
}

function ConsoleLog() {
  const { logs } = useRunFeed()
  const [open, setOpen] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ block: 'nearest' })
  }, [logs, open])

  const toneClass = useMemo(
    () => ({
      info: 'text-ink-400',
      ok: 'text-mint-400',
      warn: 'text-gold-400',
      error: 'text-rose-400',
    }),
    [],
  )

  return (
    <Card>
      <CardHeader
        title="Activity log"
        icon={<Terminal size={14} />}
        actions={
          <button className="btn btn-ghost btn-sm" onClick={() => setOpen((value) => !value)}>
            {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            {open ? 'Collapse' : 'Expand'}
          </button>
        }
      />
      {open && (
        <div className="max-h-64 overflow-y-auto px-4 py-3 font-mono text-[0.6875rem] leading-relaxed">
          {logs.map((line) => (
            <div key={line.id} className="flex gap-2.5">
              <span className="shrink-0 text-ink-500">{clockTime(line.at)}</span>
              <span className={cx('min-w-0 break-words', toneClass[line.tone])}>{line.message}</span>
            </div>
          ))}
          <div ref={endRef} />
        </div>
      )}
    </Card>
  )
}
