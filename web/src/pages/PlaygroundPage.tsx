import { useEffect, useState } from 'react'
import { FlaskConical, Info, Plus, Send, Zap } from 'lucide-react'
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
import { Link } from '../lib/router'
import { api, ApiError, type PlaygroundResult } from '../lib/api'
import { formatDuration } from '../lib/format'
import { useRunFeed } from '../hooks/useRunFeed'

export function PlaygroundPage() {
  const toast = useToast()
  const { isLive } = useRunFeed()

  const providers = useAsync(() => api.providers(), [])
  const [provider, setProvider] = useState('')
  const [modelId, setModelId] = useState('')
  const [temperature, setTemperature] = useState(0.3)
  const [prompt, setPrompt] = useState('')
  const [result, setResult] = useState<PlaygroundResult | null>(null)
  const [sending, setSending] = useState(false)
  const [saveTarget, setSaveTarget] = useState<null | true>(null)
  // Built-ins are read-only, so only custom suites are valid targets.
  const customSuites = useAsync(
    () => api.suites().then((all) => all.filter((s) => !s.builtin)),
    [],
  )

  useEffect(() => {
    if (!providers.data?.length || provider) return
    setProvider(providers.data.find((p) => p.is_default)?.name ?? providers.data[0].name)
  }, [providers.data, provider])

  const models = useAsync(
    () => (provider ? api.models(provider) : Promise.resolve(null)),
    [provider],
  )

  useEffect(() => {
    const list = models.data?.models ?? []
    setModelId((current) => (list.some((m) => m.id === current) ? current : (list[0]?.id ?? '')))
  }, [models.data])

  const send = async () => {
    if (!prompt.trim() || !provider || !modelId) return
    setSending(true)
    setResult(null)
    try {
      setResult(await api.playground({ provider, model_id: modelId, prompt, temperature }))
    } catch (cause) {
      toast(cause instanceof ApiError ? cause.message : String(cause), 'error')
    } finally {
      setSending(false)
    }
  }

  /**
   * Append the prompt to a custom suite.
   *
   * There is no longer a single "the suite" to append to, and the built-ins
   * are read-only, so this needs an explicit target. Only custom suites can
   * be chosen; if none exist yet the button points at Testing Suites instead.
   */
  const saveAsQuestion = async (slug: string) => {
    if (!prompt.trim()) return
    setSaveTarget(null)
    try {
      const detail = await api.suite(slug)
      const saved = await api.saveSuiteTests(slug, [
        ...detail.tests.map((t) => t.prompt),
        prompt.trim(),
      ])
      toast(`Added to "${saved.name}" as question ${saved.tests.length}.`, 'success')
      customSuites.reload()
    } catch (cause) {
      toast(cause instanceof ApiError ? cause.message : String(cause), 'error')
    }
  }

  const disabled = isLive || sending

  return (
    <>
      <PageHeader
        title="Playground"
        subtitle="Try a single prompt against a model without touching the suite or writing a report."
      />

      {isLive && (
        <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-ember-500/35 bg-ember-500/8 px-4 py-3">
          <Info size={15} className="mt-0.5 shrink-0 text-ember-400" />
          <p className="text-[0.8125rem] text-ember-300">
            A diagnostic run is using the engine. The playground is paused until it finishes.
          </p>
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-12">
        <div className="space-y-5 xl:col-span-5">
          <Card raised>
            <CardHeader title="Target" icon={<Zap size={14} />} />
            <div className="space-y-4 p-4">
              {providers.error && <ErrorNote message={providers.error} onRetry={providers.reload} />}
              <div>
                <label className="label" htmlFor="pg-provider">
                  Provider
                </label>
                <select
                  id="pg-provider"
                  className="field"
                  value={provider}
                  disabled={disabled}
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
                <label className="label" htmlFor="pg-model">
                  Model
                </label>
                {models.error ? (
                  <ErrorNote message={models.error} onRetry={models.reload} />
                ) : (
                  <select
                    id="pg-model"
                    className="field"
                    value={modelId}
                    disabled={disabled || models.loading || !models.data?.models.length}
                    onChange={(event) => setModelId(event.target.value)}
                  >
                    {models.loading && <option>Discovering models…</option>}
                    {!models.loading && !models.data?.models.length && (
                      <option>No models found</option>
                    )}
                    {(models.data?.models ?? []).map((model) => (
                      <option key={model.id} value={model.id}>
                        {model.display_name}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              <TemperatureSlider value={temperature} onChange={setTemperature} disabled={disabled} />
            </div>
          </Card>

          <Card raised>
            <CardHeader
              title="Prompt"
              icon={<FlaskConical size={14} />}
              actions={
                <div className="relative">
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => setSaveTarget((open) => (open ? null : true))}
                    disabled={!prompt.trim() || disabled}
                    title="Append this prompt to a custom suite"
                  >
                    <Plus size={12} />
                    Add to suite
                  </button>

                  {saveTarget && (
                    <>
                      <div className="fixed inset-0 z-10" onClick={() => setSaveTarget(null)} />
                      <div className="surface-raised animate-fade-up absolute right-0 z-20 mt-1.5 w-60 p-1.5">
                        <p className="px-2 py-1 text-[0.625rem] font-semibold tracking-[0.09em] text-ink-500 uppercase">
                          Add to
                        </p>
                        {customSuites.data?.length ? (
                          customSuites.data.map((suite) => (
                            <button
                              key={suite.slug}
                              className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-[0.75rem] text-ink-300 transition-colors hover:bg-navy-750 hover:text-ink-100"
                              onClick={() => saveAsQuestion(suite.slug)}
                            >
                              <span className="truncate">{suite.name}</span>
                              <span className="num shrink-0 text-[0.6875rem] text-ink-500">
                                {suite.count}
                              </span>
                            </button>
                          ))
                        ) : (
                          <div className="px-2 py-2">
                            <p className="text-[0.75rem] leading-relaxed text-ink-500">
                              No custom suites yet. Built-in suites are read-only.
                            </p>
                            <Link
                              to="/suite"
                              className="btn btn-ghost btn-sm mt-2 w-full"
                              onClick={() => setSaveTarget(null)}
                            >
                              Open Testing Suites
                            </Link>
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </div>
              }
            />
            <div className="p-4">
              <textarea
                className="field min-h-44 font-mono text-[0.8125rem] leading-relaxed"
                placeholder="Ask the model something…"
                value={prompt}
                spellCheck={false}
                disabled={disabled}
                onChange={(event) => setPrompt(event.target.value)}
                onKeyDown={(event) => {
                  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') send()
                }}
              />
              <div className="mt-3 flex items-center justify-between gap-2">
                <span className="text-[0.6875rem] text-ink-500">⌘↵ to send</span>
                <button
                  className="btn btn-primary"
                  onClick={send}
                  disabled={!prompt.trim() || !modelId || disabled}
                >
                  {sending ? <Spinner /> : <Send size={14} />}
                  {sending ? 'Generating…' : 'Send'}
                </button>
              </div>
            </div>
          </Card>
        </div>

        <div className="xl:col-span-7">
          <Card className="xl:sticky xl:top-6">
            <CardHeader
              title="Response"
              icon={<Send size={14} />}
              actions={
                result?.elapsed ? (
                  <span className="chip chip-neutral num">{formatDuration(result.elapsed)}</span>
                ) : null
              }
            />

            {sending && (
              <div className="flex items-center gap-2.5 px-4 py-10 text-[0.8125rem] text-ink-400">
                <Spinner className="text-ember-400" />
                Waiting on the model — a cold model may take a moment to load.
              </div>
            )}

            {!sending && !result && (
              <EmptyState
                icon={<FlaskConical size={20} />}
                title="Nothing sent yet"
                description="Write a prompt and hit Send. Responses render as markdown with syntax highlighting."
              />
            )}

            {!sending && result?.error && (
              <div className="p-4">
                <ErrorNote message={result.error} />
              </div>
            )}

            {!sending && result?.response != null && (
              <>
                {result.metrics && (
                  <div className="grid grid-cols-2 gap-2.5 border-b border-navy-700 p-4 sm:grid-cols-4">
                    <StatTile
                      label="tok/s"
                      value={result.metrics.tokens_per_second.toFixed(1)}
                      tone="gold"
                    />
                    <StatTile
                      label="TTFT"
                      value={result.metrics.time_to_first_token.toFixed(2)}
                      unit="s"
                      tone="gold"
                    />
                    <StatTile
                      label="Tokens"
                      value={result.metrics.total_tokens.toLocaleString()}
                      tone="neutral"
                    />
                    <StatTile label="Stop" value={result.metrics.stop_reason} tone="neutral" />
                  </div>
                )}
                <div className="max-h-[60vh] overflow-y-auto p-4">
                  <Markdown>{result.response || '_Empty response._'}</Markdown>
                </div>
              </>
            )}
          </Card>
        </div>
      </div>

      <p className="mt-5 text-[0.75rem] text-ink-500">
        Looking to save a set of questions instead?{' '}
        <Link to="/suite" className="text-ember-400 underline underline-offset-2">
          Open the Suite Builder
        </Link>
        .
      </p>
    </>
  )
}
