/**
 * Renders the interface plugins declare.
 *
 * A plugin returns data — never code — from its `ui_contributions()` hook, and
 * this module draws it with the same primitives the built-in pages use, so a
 * plugin panel is indistinguishable from a native one. That is the whole reason
 * installing a plugin never requires rebuilding this bundle.
 *
 * Blocks may carry inline data or a `source` URL. With a source the block
 * fetches its own data and re-fetches whenever `refreshKey` changes, which is
 * how an Action button refreshes its siblings.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  Activity, AlertTriangle, BarChart3, Bug, CheckCircle2, Database, FileText,
  Gauge, Hash, Layers, ListChecks, Play, Puzzle, RefreshCw, Search, Settings2,
  Shield, Sparkles, Table2, Terminal, Trash2, Wrench, Zap,
} from 'lucide-react'
import { Markdown } from './Markdown'
import { Card, CardHeader, ConfirmDialog, EmptyState, ErrorNote, Spinner, StatTile, useToast } from './ui'
import { api, type ActionBlock, type MarkdownBlock, type PanelBlock, type PluginBlock, type StatRowBlock, type TableBlock } from '../lib/api'
import { usePluginSlot } from '../hooks/usePluginUI'
import { cx } from '../lib/format'

/* Plugins name an icon; only these resolve. An unknown name is not an error —
 * it falls back to a puzzle piece so a typo never blanks the interface. */
const ICONS: Record<string, typeof Puzzle> = {
  activity: Activity, alert: AlertTriangle, bar: BarChart3, bug: Bug,
  check: CheckCircle2, database: Database, file: FileText, gauge: Gauge,
  hash: Hash, layers: Layers, list: ListChecks, play: Play, puzzle: Puzzle,
  refresh: RefreshCw, search: Search, settings: Settings2, shield: Shield,
  sparkles: Sparkles, table: Table2, terminal: Terminal, trash: Trash2,
  wrench: Wrench, zap: Zap,
}

export function pluginIcon(name: string | null | undefined) {
  return ICONS[(name || '').toLowerCase()] ?? Puzzle
}

const TONE_TO_TILE = {
  default: 'neutral',
  good: 'mint',
  warn: 'gold',
  bad: 'rose',
} as const

/* ------------------------------------------------------------ data plumbing */

/** Inline data, or fetched from `source` and refreshed on demand. */
function useBlockData<T extends object>(block: T & { source?: string | null }, refreshKey: number) {
  const [data, setData] = useState<T>(block)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(Boolean(block.source))

  useEffect(() => {
    if (!block.source) {
      setData(block)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    api
      .pluginData<Partial<T>>(block.source)
      .then((fresh) => {
        if (!cancelled) {
          setData({ ...block, ...fresh })
          setError(null)
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : String(cause))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [block.source, refreshKey])

  return { data, error, loading }
}

/* ------------------------------------------------------------------ blocks */

function StatRow({ block, refreshKey }: { block: StatRowBlock; refreshKey: number }) {
  const { data, error, loading } = useBlockData(block, refreshKey)
  if (error) return <ErrorNote message={error} />
  const stats = data.stats ?? []
  if (loading && !stats.length) {
    return <div className="flex items-center gap-2 text-[0.8125rem] text-ink-500"><Spinner /> Loading…</div>
  }
  if (!stats.length) return null

  return (
    <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
      {stats.map((stat, index) => (
        <StatTile
          key={`${stat.label}-${index}`}
          label={stat.label}
          value={stat.value}
          hint={stat.hint}
          tone={TONE_TO_TILE[stat.tone] ?? 'neutral'}
        />
      ))}
    </div>
  )
}

function PluginTable({ block, refreshKey }: { block: TableBlock; refreshKey: number }) {
  const { data, error, loading } = useBlockData(block, refreshKey)
  if (error) return <ErrorNote message={error} />

  const rows = data.rows ?? []
  const columns = data.columns ?? []

  if (loading && !rows.length) {
    return <div className="flex items-center gap-2 px-4 py-6 text-[0.8125rem] text-ink-500"><Spinner /> Loading…</div>
  }
  if (!rows.length) {
    return <EmptyState icon={<Table2 size={18} />} title="Nothing yet" description={data.empty} />
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[0.8125rem]">
        <thead>
          <tr className="border-b border-navy-700">
            {columns.map((column) => (
              <th key={column} className="px-4 py-2.5 text-[0.6875rem] font-semibold tracking-wide text-ink-500 uppercase">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-b border-navy-800/70 last:border-0 hover:bg-navy-800/40">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="px-4 py-2.5 align-top text-ink-300">
                  {String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PluginMarkdown({ block, refreshKey }: { block: MarkdownBlock; refreshKey: number }) {
  const { data, error } = useBlockData(block, refreshKey)
  if (error) return <ErrorNote message={error} />
  if (!data.text) return null
  return (
    <div className="px-4 py-3">
      <Markdown>{data.text}</Markdown>
    </div>
  )
}

function PluginAction({ block, onRefresh }: { block: ActionBlock; onRefresh: () => void }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const Icon = pluginIcon(block.icon)

  const fire = useCallback(async () => {
    setConfirming(false)
    setBusy(true)
    try {
      const result = await api.pluginAction(block.post)
      if (result?.message) toast(result.message, 'success')
      if (result?.refresh) onRefresh()
    } catch (cause: unknown) {
      toast(cause instanceof Error ? cause.message : String(cause), 'error')
    } finally {
      setBusy(false)
    }
  }, [block.post, onRefresh, toast])

  const style =
    block.style === 'danger' ? 'btn-danger' : block.style === 'ghost' ? 'btn-ghost' : 'btn-primary'

  return (
    <>
      <button
        className={cx('btn btn-sm', style)}
        disabled={busy}
        onClick={() => (block.confirm ? setConfirming(true) : fire())}
      >
        {busy ? <Spinner className="h-3.5 w-3.5" /> : <Icon size={14} />}
        {block.label}
      </button>
      <ConfirmDialog
        open={confirming}
        title={block.label}
        body={block.confirm ?? ''}
        confirmLabel={block.label}
        destructive={block.style === 'danger'}
        onConfirm={fire}
        onCancel={() => setConfirming(false)}
      />
    </>
  )
}

function PluginPanel({
  block,
  refreshKey,
  onRefresh,
}: {
  block: PanelBlock
  refreshKey: number
  onRefresh: () => void
}) {
  const children = block.blocks ?? []
  // Actions belong in the panel header, everything else in the body.
  const actions = children.filter((child): child is ActionBlock => child.kind === 'action')
  const body = children.filter((child) => child.kind !== 'action')
  // Padding is the block's own job for tables and markdown, which bleed to the edge.
  const bleeds = (kind: string) => kind === 'table' || kind === 'markdown'

  return (
    <Card>
      <CardHeader
        title={block.title}
        hint={block.subtitle || undefined}
        actions={
          actions.length ? (
            <div className="flex items-center gap-2">
              {actions.map((action, index) => (
                <PluginAction key={index} block={action} onRefresh={onRefresh} />
              ))}
            </div>
          ) : undefined
        }
      />
      {body.map((child, index) => (
        <div key={index} className={bleeds(child.kind) ? '' : 'px-4 py-3'}>
          <BlockView block={child} refreshKey={refreshKey} onRefresh={onRefresh} />
        </div>
      ))}
    </Card>
  )
}

function BlockView({
  block,
  refreshKey,
  onRefresh,
}: {
  block: PluginBlock
  refreshKey: number
  onRefresh: () => void
}): ReactNode {
  switch (block.kind) {
    case 'stat_row':
      return <StatRow block={block} refreshKey={refreshKey} />
    case 'table':
      return <PluginTable block={block} refreshKey={refreshKey} />
    case 'markdown':
      return <PluginMarkdown block={block} refreshKey={refreshKey} />
    case 'action':
      return <PluginAction block={block} onRefresh={onRefresh} />
    case 'panel':
      return <PluginPanel block={block} refreshKey={refreshKey} onRefresh={onRefresh} />
    default:
      // A plugin built against a newer host than this bundle. Say so rather
      // than rendering nothing, so the cause is obvious.
      return (
        <ErrorNote
          message={`This build does not know how to render a "${(block as { kind: string }).kind}" block.`}
        />
      )
  }
}

/* ------------------------------------------------------------------- public */

export function PluginBlocks({
  blocks,
  className,
  autoRefreshMs,
}: {
  blocks: PluginBlock[]
  className?: string
  autoRefreshMs?: number
}) {
  const [refreshKey, setRefreshKey] = useState(0)
  const refresh = useCallback(() => setRefreshKey((key) => key + 1), [])

  useEffect(() => {
    if (!autoRefreshMs) return
    const timer = setInterval(refresh, autoRefreshMs)
    return () => clearInterval(timer)
  }, [autoRefreshMs, refresh])

  const rendered = useMemo(
    () =>
      blocks.map((block, index) => (
        <BlockView key={index} block={block} refreshKey={refreshKey} onRefresh={refresh} />
      )),
    [blocks, refreshKey, refresh],
  )

  return <div className={cx('space-y-4', className)}>{rendered}</div>
}

/**
 * Every panel plugins contributed to one injection point.
 *
 * Renders nothing at all when no plugin uses the slot, so built-in pages carry
 * these with no visual cost until something opts in.
 */
export function PluginSlot({
  slot,
  className,
  autoRefreshMs,
}: {
  slot: string
  className?: string
  autoRefreshMs?: number
}) {
  const panels = usePluginSlot(slot)
  if (!panels.length) return null

  return (
    <div className={cx('space-y-4', className)}>
      {panels.map((entry, index) => (
        <PluginBlocks
          key={`${entry.slug}-${index}`}
          blocks={[entry.panel]}
          autoRefreshMs={autoRefreshMs}
        />
      ))}
    </div>
  )
}
