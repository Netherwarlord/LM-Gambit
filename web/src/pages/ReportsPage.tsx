import { useEffect, useMemo, useState } from 'react'
import {
  BarChart3,
  CheckCircle2,
  FileText,
  LayoutList,
  Table2,
  Trash2,
  TriangleAlert,
} from 'lucide-react'
import {
  Card,
  CardHeader,
  ConfirmDialog,
  EmptyState,
  ErrorNote,
  PageHeader,
  SkeletonRows,
  StatTile,
  useAsync,
  useToast,
} from '../components/ui'
import { PluginSlot } from '../components/PluginBlocks'
import { Markdown } from '../components/Markdown'
import { ScoreBadge, scoreTone } from '../components/ScoreBadge'
import { ThroughputChart } from '../components/ThroughputChart'
import { api, ApiError, type ReportDetail } from '../lib/api'
import { parseReport } from '../lib/report'
import { cx, formatBytes, formatRelativeTime } from '../lib/format'
import { useRouter } from '../lib/router'

type View = 'chart' | 'table' | 'full'

/**
 * Hide the sentinels the engine uses to locate rewritable blocks (the summary,
 * and the analysis section grader plugins fill in). Only those exact markers
 * are removed, so HTML inside a model's code fence is left untouched.
 */
function readableReport(markdown: string): string {
  return markdown.replace(/^[ \t]*<!--(?:SUMMARY|ANALYSIS)_(?:START|END)-->[ \t]*\n?/gm, '')
}

export function ReportsPage() {
  const toast = useToast()
  const { path, navigate } = useRouter()
  const reports = useAsync(() => api.reports(), [])

  const routeName = useMemo(() => {
    const match = path.match(/^\/reports\/(.+)$/)
    return match ? decodeURIComponent(match[1]) : null
  }, [path])

  const [detail, setDetail] = useState<ReportDetail | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [view, setView] = useState<View>('chart')
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)

  // Default to the newest report when landing on /reports.
  useEffect(() => {
    if (routeName || !reports.data?.length) return
    navigate(`/reports/${encodeURIComponent(reports.data[0].name)}`, { replace: true })
  }, [routeName, reports.data, navigate])

  useEffect(() => {
    if (!routeName) {
      setDetail(null)
      return
    }
    let cancelled = false
    setLoadingDetail(true)
    setDetailError(null)
    api
      .report(routeName)
      .then((value) => {
        if (!cancelled) setDetail(value)
      })
      .catch((cause: unknown) => {
        if (!cancelled) setDetailError(cause instanceof Error ? cause.message : String(cause))
      })
      .finally(() => {
        if (!cancelled) setLoadingDetail(false)
      })
    return () => {
      cancelled = true
    }
  }, [routeName])

  const parsed = useMemo(() => (detail ? parseReport(detail.content) : null), [detail])

  const confirmDelete = async () => {
    if (!pendingDelete) return
    try {
      await api.deleteReport(pendingDelete)
      toast(`Deleted ${pendingDelete}`, 'success')
      if (routeName === pendingDelete) {
        setDetail(null)
        navigate('/reports', { replace: true })
      }
      reports.reload()
    } catch (cause) {
      toast(cause instanceof ApiError ? cause.message : String(cause), 'error')
    } finally {
      setPendingDelete(null)
    }
  }

  const items = reports.data ?? []

  return (
    <>
      <PageHeader
        title="Reports"
        subtitle="Every run writes a markdown report to the results folder. Open one to review answers and throughput."
      />

      {reports.error && <ErrorNote message={reports.error} onRetry={reports.reload} />}

      {!reports.loading && items.length === 0 && !reports.error ? (
        <Card>
          <EmptyState
            icon={<FileText size={20} />}
            title="No reports yet"
            description="Run the diagnostic suite and the report will show up here."
          />
        </Card>
      ) : (
        <div className="grid gap-5 xl:grid-cols-12">
          {/* ------------------------------------------------------- list */}
          <div className="xl:col-span-4">
            <Card className="xl:sticky xl:top-6">
              <CardHeader
                title="Saved reports"
                icon={<LayoutList size={14} />}
                actions={<span className="chip chip-neutral num">{items.length}</span>}
              />
              {reports.loading ? (
                <SkeletonRows rows={3} />
              ) : (
                <ul className="max-h-[70vh] divide-y divide-navy-700/60 overflow-y-auto">
                  {items.map((report) => {
                    const active = report.name === routeName
                    return (
                      <li key={report.name}>
                        <div
                          className={cx(
                            'group relative flex items-center gap-2 px-4 py-3 transition-colors',
                            active ? 'bg-navy-750/60' : 'hover:bg-navy-800/40',
                          )}
                        >
                          {active && (
                            <span className="absolute top-1/2 left-0 h-8 w-[3px] -translate-y-1/2 rounded-r-full bg-ember-500" />
                          )}
                          <button
                            className="min-w-0 flex-1 text-left"
                            onClick={() =>
                              navigate(`/reports/${encodeURIComponent(report.name)}`)
                            }
                          >
                            <div
                              className={cx(
                                'truncate text-[0.8125rem] font-medium',
                                active ? 'text-ink-100' : 'text-ink-200',
                              )}
                            >
                              {report.model_label}
                            </div>
                            <div className="mt-0.5 flex items-center gap-2 text-[0.6875rem] text-ink-500">
                              <span>{formatRelativeTime(report.modified_at)}</span>
                              <span>·</span>
                              <span className="num">{formatBytes(report.size_bytes)}</span>
                            </div>
                          </button>
                          <button
                            className="shrink-0 rounded-md p-1.5 text-ink-500 opacity-0 transition-all group-hover:opacity-100 hover:bg-rose-500/15 hover:text-rose-400 focus-visible:opacity-100"
                            onClick={() => setPendingDelete(report.name)}
                            aria-label={`Delete ${report.name}`}
                            title="Delete report"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}
            </Card>
            <PluginSlot slot="reports.aside" className="mt-4" />
          </div>

          {/* ----------------------------------------------------- detail */}
          <div className="space-y-5 xl:col-span-8">
            {detailError && <ErrorNote message={detailError} />}

            {loadingDetail && (
              <Card>
                <SkeletonRows rows={5} />
              </Card>
            )}

            {detail && parsed && !loadingDetail && (
              <>
                <Card raised>
                  <div className="p-4">
                    <h2 className="text-[1.05rem] font-semibold text-ink-100">
                      {parsed.modelLabel}
                    </h2>
                    <p className="mt-0.5 font-mono text-[0.6875rem] text-ink-500">{detail.name}</p>

                    <div
                      className={cx(
                        'mt-3.5 grid grid-cols-2 gap-2.5',
                        parsed.overallScore != null ? 'sm:grid-cols-5' : 'sm:grid-cols-4',
                      )}
                    >
                      {parsed.overallScore != null && (
                        <StatTile
                          label="Score"
                          value={`${Math.round(parsed.overallScore * 100)}%`}
                          tone={scoreTone(parsed.overallScore)}
                          hint={parsed.graders.join(', ')}
                        />
                      )}
                      <StatTile
                        label="Avg tok/s"
                        value={parsed.averageTokensPerSecond?.toFixed(1) ?? '—'}
                        tone="gold"
                      />
                      <StatTile
                        label="Avg TTFT"
                        value={parsed.averageTimeToFirstToken?.toFixed(2) ?? '—'}
                        unit="s"
                        tone="gold"
                      />
                      <StatTile
                        label="Tokens"
                        value={parsed.totalTokens?.toLocaleString() ?? '—'}
                        tone="neutral"
                      />
                      <StatTile label="Questions" value={parsed.tests.length} tone="neutral" />
                    </div>

                    <div className="mt-2.5 flex flex-wrap items-center gap-2">
                      <span className="chip chip-mint">
                        <CheckCircle2 size={11} />
                        {parsed.tests.filter((t) => t.ok).length} answered
                      </span>
                      {parsed.tests.some((t) => !t.ok) && (
                        <span className="chip chip-rose">
                          <TriangleAlert size={11} />
                          {parsed.tests.filter((t) => !t.ok).length} errored
                        </span>
                      )}
                    </div>
                  </div>
                </Card>

                <Card>
                  <CardHeader
                    title="Analysis"
                    icon={<BarChart3 size={14} />}
                    actions={
                      <div className="flex gap-1">
                        {(
                          [
                            ['chart', 'Chart', BarChart3],
                            ['table', 'Table', Table2],
                            ['full', 'Report', FileText],
                          ] as const
                        ).map(([key, label, Icon]) => (
                          <button
                            key={key}
                            className={
                              view === key
                                ? 'btn btn-sm border-gold-500/40 bg-gold-500/15 text-gold-300'
                                : 'btn btn-ghost btn-sm'
                            }
                            onClick={() => setView(key)}
                          >
                            <Icon size={12} />
                            {label}
                          </button>
                        ))}
                      </div>
                    }
                  />

                  {view === 'chart' && <ThroughputChart tests={parsed.tests} />}

                  {view === 'table' && (
                    <div className="overflow-x-auto">
                      <table className="w-full text-[0.75rem]">
                        <thead>
                          <tr className="border-b border-navy-700 text-left text-[0.6875rem] tracking-wide text-ink-500 uppercase">
                            <th className="px-4 py-2.5 font-semibold">#</th>
                            <th className="px-3 py-2.5 font-semibold">Question</th>
                            {parsed.overallScore != null && (
                              <th className="px-3 py-2.5 text-right font-semibold">Score</th>
                            )}
                            <th className="px-3 py-2.5 text-right font-semibold">tok/s</th>
                            <th className="px-3 py-2.5 text-right font-semibold">Tokens</th>
                            <th className="px-3 py-2.5 text-right font-semibold">TTFT</th>
                            <th className="px-4 py-2.5 font-semibold">Stop</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-navy-700/60">
                          {parsed.tests.map((test) => (
                            <tr key={test.index} className="hover:bg-navy-800/40">
                              <td className="num px-4 py-2.5 text-ink-500">{test.index}</td>
                              <td className="max-w-xs px-3 py-2.5">
                                <span className="block truncate text-ink-200" title={test.title}>
                                  {test.title}
                                </span>
                                {!test.ok && (
                                  <span className="mt-0.5 flex items-center gap-1 text-[0.6875rem] text-rose-400">
                                    <TriangleAlert size={10} />
                                    Error: {test.error}
                                  </span>
                                )}
                              </td>
                              {parsed.overallScore != null && (
                                <td className="px-3 py-2.5 text-right">
                                  {test.score != null ? (
                                    <ScoreBadge score={test.score} />
                                  ) : (
                                    <span className="text-ink-500">—</span>
                                  )}
                                </td>
                              )}
                              <td className="num px-3 py-2.5 text-right text-gold-400">
                                {test.tokensPerSecond?.toFixed(1) ?? '—'}
                              </td>
                              <td className="num px-3 py-2.5 text-right text-ink-300">
                                {test.totalTokens?.toLocaleString() ?? '—'}
                              </td>
                              <td className="num px-3 py-2.5 text-right text-ink-300">
                                {test.timeToFirstToken != null
                                  ? `${test.timeToFirstToken.toFixed(2)}s`
                                  : '—'}
                              </td>
                              <td className="px-4 py-2.5 text-ink-500">{test.stopReason ?? '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {view === 'full' && (
                    <div className="max-h-[75vh] overflow-y-auto px-4 py-4">
                      <Markdown>{readableReport(detail.content)}</Markdown>
                    </div>
                  )}
                </Card>
              </>
            )}
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!pendingDelete}
        title="Delete this report?"
        body={`${pendingDelete} will be removed from the results folder. This cannot be undone.`}
        confirmLabel="Delete"
        destructive
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </>
  )
}
