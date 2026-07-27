import { useCallback, useEffect, useState } from 'react'
import {
  Blocks,
  CircleSlash,
  Cpu,
  FolderOpen,
  HardDrive,
  Info,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  Settings2,
  SlidersHorizontal,
  Trash2,
  TriangleAlert,
} from 'lucide-react'
import {
  Card,
  CardHeader,
  ErrorNote,
  PageHeader,
  SkeletonRows,
  Spinner,
  TemperatureSlider,
  useAsync,
  useToast,
} from '../components/ui'
import { api, ApiError, type ModelPathEntry, type PluginSummary } from '../lib/api'
import { cx } from '../lib/format'

export function SettingsPage() {
  const toast = useToast()
  const providers = useAsync(() => api.providers(), [])
  const system = useAsync(() => api.system(), [])

  const [defaultProvider, setDefaultProvider] = useState('')
  const [defaultTemperature, setDefaultTemperature] = useState(0.1)
  const [paths, setPaths] = useState<ModelPathEntry[]>([])
  const [dirs, setDirs] = useState<{ tests: string; results: string; models: string } | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    setLoadError(null)
    api
      .settings()
      .then((settings) => {
        setDefaultProvider(settings.default_provider)
        setDefaultTemperature(settings.default_temperature)
        setPaths(settings.local_model_paths)
        setDirs({
          tests: settings.tests_dir,
          results: settings.results_dir,
          models: settings.models_dir,
        })
      })
      .catch((cause: unknown) =>
        setLoadError(cause instanceof Error ? cause.message : String(cause)),
      )
      .finally(() => setLoading(false))
  }, [])

  useEffect(load, [load])

  const save = async () => {
    setSaving(true)
    try {
      const saved = await api.saveSettings({
        default_provider: defaultProvider,
        default_temperature: defaultTemperature,
        local_model_paths: paths.filter((entry) => entry.path.trim()),
      })
      setPaths(saved.local_model_paths)
      toast('Settings saved.', 'success')
    } catch (cause) {
      toast(cause instanceof ApiError ? cause.message : String(cause), 'error')
    } finally {
      setSaving(false)
    }
  }

  const updatePath = (index: number, patch: Partial<ModelPathEntry>) =>
    setPaths((list) => list.map((entry, i) => (i === index ? { ...entry, ...patch } : entry)))

  return (
    <>
      <PageHeader
        title="Settings"
        subtitle="Defaults for new runs, plus where the Local Engine looks for model weights."
        actions={
          <>
            <button className="btn btn-ghost" onClick={load} disabled={saving || loading}>
              <RotateCcw size={14} />
              Reload
            </button>
            <button className="btn btn-primary" onClick={save} disabled={saving || loading}>
              {saving ? <Spinner /> : <Save size={14} />}
              {saving ? 'Saving…' : 'Save settings'}
            </button>
          </>
        }
      />

      {loadError && <ErrorNote message={loadError} onRetry={load} />}

      {loading ? (
        <Card>
          <SkeletonRows rows={4} />
        </Card>
      ) : (
        <div className="grid gap-5 xl:grid-cols-12">
          <div className="space-y-5 xl:col-span-7">
            <Card raised>
              <CardHeader
                title="Run defaults"
                icon={<SlidersHorizontal size={14} />}
                hint="Applied when the Run page loads"
              />
              <div className="space-y-4 p-4">
                <div>
                  <label className="label" htmlFor="default-provider">
                    Default provider
                  </label>
                  <select
                    id="default-provider"
                    className="field"
                    value={defaultProvider}
                    onChange={(event) => setDefaultProvider(event.target.value)}
                  >
                    {(providers.data ?? []).map((item) => (
                      <option key={item.name} value={item.name}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </div>
                <TemperatureSlider value={defaultTemperature} onChange={setDefaultTemperature} />
              </div>
            </Card>

            <Card raised>
              <CardHeader
                title="Model search paths"
                icon={<FolderOpen size={14} />}
                hint="Folders scanned for .gguf and MLX weights"
                actions={
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => setPaths((list) => [...list, { nickname: '', path: '' }])}
                  >
                    <Plus size={12} />
                    Add
                  </button>
                }
              />
              <div className="space-y-2.5 p-4">
                {paths.length === 0 && (
                  <p className="py-2 text-[0.8125rem] text-ink-500">
                    No extra paths. The engine still scans the bundled{' '}
                    <code className="font-mono text-[0.75rem] text-gold-300">models/</code> folder.
                  </p>
                )}

                {paths.map((entry, index) => (
                  <div key={index} className="flex items-start gap-2">
                    <input
                      className="field w-32 shrink-0"
                      placeholder="Nickname"
                      value={entry.nickname}
                      onChange={(event) => updatePath(index, { nickname: event.target.value })}
                    />
                    <input
                      className="field min-w-0 flex-1 font-mono text-[0.75rem]"
                      placeholder="/path/to/models"
                      value={entry.path}
                      spellCheck={false}
                      onChange={(event) => updatePath(index, { path: event.target.value })}
                    />
                    <button
                      className="mt-1 shrink-0 rounded-md p-1.5 text-ink-500 transition-colors hover:bg-rose-500/15 hover:text-rose-400"
                      onClick={() => setPaths((list) => list.filter((_, i) => i !== index))}
                      aria-label="Remove path"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}

                <div className="flex items-start gap-2 pt-1 text-[0.75rem] text-ink-500">
                  <Info size={13} className="mt-0.5 shrink-0 text-gold-600" />
                  <p>
                    Nicknames are for your reference only. Paths are shared with the CLI through{' '}
                    <code className="font-mono text-[0.6875rem]">.core/user_settings.json</code>,
                    and <code className="font-mono text-[0.6875rem]">LOCAL_LLM_PATHS</code> is still
                    honoured on top of them.
                  </p>
                </div>
              </div>
            </Card>
          </div>

          <div className="space-y-5 xl:col-span-5">
            <Card>
              <CardHeader title="Engine" icon={<Cpu size={14} />} />
              <div className="p-4">
                {system.error && <ErrorNote message={system.error} onRetry={system.reload} />}
                {system.data && (
                  <dl className="space-y-2.5 text-[0.8125rem]">
                    <InfoRow label="Runtime" value={system.data.engine_runtime} mono />
                    <InfoRow label="Architecture" value={system.data.engine_architecture} />
                    <InfoRow label="Platform" value={system.data.metrics.platform ?? '—'} />
                    <InfoRow label="Python" value={system.data.python_version} mono />
                    <InfoRow label="LM-Gambit" value={`v${system.data.version}`} mono />
                    <InfoRow
                      label="Report template"
                      value={system.data.template_ok ? 'Found' : 'Missing'}
                      tone={system.data.template_ok ? 'ok' : 'bad'}
                    />
                  </dl>
                )}
              </div>
            </Card>

            <Card>
              <CardHeader title="Folders" icon={<HardDrive size={14} />} />
              <div className="space-y-3 p-4">
                {dirs && (
                  <>
                    <PathRow label="Questions" path={dirs.tests} />
                    <PathRow label="Reports" path={dirs.results} />
                    <PathRow label="Bundled models" path={dirs.models} />
                  </>
                )}
              </div>
            </Card>

            <PluginsCard />

            <Card>
              <CardHeader title="Environment overrides" icon={<Settings2 size={14} />} />
              <div className="space-y-2 p-4 text-[0.75rem] text-ink-400">
                {[
                  ['LM_STUDIO_BASE_URL', 'LM Studio endpoint'],
                  ['AUTO_TEST_TEMPERATURE', 'Default temperature'],
                  ['AUTO_TEST_PROVIDER', 'Default provider for the CLI'],
                  ['LOCAL_LLM_PATHS', 'Extra model directories'],
                ].map(([name, description]) => (
                  <div key={name} className="flex items-baseline justify-between gap-3">
                    <code className="font-mono text-[0.6875rem] text-gold-300">{name}</code>
                    <span className="text-right text-ink-500">{description}</span>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      )}
    </>
  )
}

function PluginsCard() {
  const toast = useToast()
  const plugins = useAsync(() => api.plugins(), [])
  const [reloading, setReloading] = useState(false)

  const reload = async () => {
    setReloading(true)
    try {
      const next = await api.reloadPlugins()
      plugins.setData(next)
      const broken = next.filter((p) => p.error).length
      toast(
        broken
          ? `Reloaded ${next.length} plugin(s) — ${broken} failed to load.`
          : `Reloaded ${next.length} plugin(s).`,
        broken ? 'error' : 'success',
      )
    } catch (cause) {
      toast(cause instanceof ApiError ? cause.message : String(cause), 'error')
    } finally {
      setReloading(false)
    }
  }

  const items = plugins.data ?? []

  return (
    <Card>
      <CardHeader
        title="Plugins"
        icon={<Blocks size={14} />}
        hint="Dropped into plugins/"
        actions={
          <button className="btn btn-ghost btn-sm" onClick={reload} disabled={reloading}>
            {reloading ? <Spinner className="h-3 w-3" /> : <RefreshCw size={12} />}
            Reload
          </button>
        }
      />
      <div className="p-4">
        {plugins.error && <ErrorNote message={plugins.error} onRetry={plugins.reload} />}

        {!plugins.loading && items.length === 0 && !plugins.error && (
          <p className="text-[0.8125rem] text-ink-500">
            No plugins yet. Copy{' '}
            <code className="font-mono text-[0.75rem] text-gold-300">plugins/_skeleton.py</code> to
            a new name to write one.
          </p>
        )}

        <div className="space-y-2.5">
          {items.map((plugin) => (
            <PluginRow key={plugin.slug} plugin={plugin} />
          ))}
        </div>

        {items.some((p) => p.hooks.includes('register_routes')) && (
          <p className="mt-3 flex items-start gap-1.5 text-[0.6875rem] text-ink-500">
            <Info size={12} className="mt-0.5 shrink-0 text-gold-600" />
            Reloading picks up new graders and hooks. Plugins that add HTTP routes need a full
            server restart.
          </p>
        )}
      </div>
    </Card>
  )
}

function PluginRow({ plugin }: { plugin: PluginSummary }) {
  const broken = !!plugin.error
  const disabled = !plugin.enabled && !broken

  return (
    <div
      className={cx(
        'rounded-xl border px-3.5 py-2.5',
        broken
          ? 'border-rose-500/40 bg-rose-500/8'
          : disabled
            ? 'border-navy-700 bg-navy-900/30 opacity-65'
            : 'border-navy-700 bg-navy-900/40',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            {broken ? (
              <TriangleAlert size={12} className="shrink-0 text-rose-400" />
            ) : disabled ? (
              <CircleSlash size={12} className="shrink-0 text-ink-500" />
            ) : (
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-mint-400" />
            )}
            <span className="truncate text-[0.8125rem] font-medium text-ink-100">
              {plugin.name}
            </span>
            <span className="num shrink-0 text-[0.6875rem] text-ink-500">v{plugin.version}</span>
          </div>
          {plugin.description && (
            <p className="mt-0.5 text-[0.75rem] text-ink-400">{plugin.description}</p>
          )}
        </div>
        <code className="shrink-0 font-mono text-[0.625rem] text-ink-500">{plugin.slug}</code>
      </div>

      {broken && (
        <p className="mt-1.5 font-mono text-[0.6875rem] break-words text-rose-400">
          {plugin.error}
        </p>
      )}

      {disabled && (
        <p className="mt-1.5 text-[0.6875rem] text-ink-500">
          Disabled by <code className="font-mono">ENABLED = False</code>.
        </p>
      )}

      {!broken && plugin.hooks.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {plugin.hooks.map((hook) => (
            <span key={hook} className="chip chip-neutral font-mono !text-[0.625rem]">
              {hook}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function InfoRow({
  label,
  value,
  mono,
  tone,
}: {
  label: string
  value: string
  mono?: boolean
  tone?: 'ok' | 'bad'
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="shrink-0 text-ink-500">{label}</dt>
      <dd
        className={[
          'min-w-0 truncate text-right',
          mono ? 'font-mono text-[0.75rem]' : '',
          tone === 'ok' ? 'text-mint-400' : tone === 'bad' ? 'text-rose-400' : 'text-ink-200',
        ].join(' ')}
        title={value}
      >
        {value}
      </dd>
    </div>
  )
}

function PathRow({ label, path }: { label: string; path: string }) {
  return (
    <div>
      <div className="text-[0.625rem] font-semibold tracking-[0.09em] text-ink-500 uppercase">
        {label}
      </div>
      <div className="mt-0.5 font-mono text-[0.6875rem] break-all text-ink-300" title={path}>
        {path}
      </div>
    </div>
  )
}
