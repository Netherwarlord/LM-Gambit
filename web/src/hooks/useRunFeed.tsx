/**
 * Owns the live state of a diagnostic run.
 *
 * Lives above the router so a run keeps streaming while the user browses other
 * views, and re-attaches to an in-flight run after a page reload by asking the
 * server what is currently active.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import {
  api,
  subscribeToRun,
  type Run,
  type RunEvent,
  type TestCompletedEvent,
} from '../lib/api'

export interface LogLine {
  id: number
  at: number
  tone: 'info' | 'ok' | 'error' | 'warn'
  message: string
}

export interface PlannedTest {
  index: number
  title: string
  filename: string
}

interface RunFeedValue {
  run: Run | null
  plan: PlannedTest[]
  outcomes: TestCompletedEvent[]
  logs: LogLine[]
  starting: boolean
  isLive: boolean
  start: (input: {
    provider: string
    model_id: string
    temperature: number
    filenames?: string[]
  }) => Promise<void>
  cancel: () => Promise<void>
  clear: () => void
  attach: (runId: string) => void
}

const RunFeedContext = createContext<RunFeedValue | null>(null)

export function useRunFeed() {
  const value = useContext(RunFeedContext)
  if (!value) throw new Error('useRunFeed must be used inside <RunFeedProvider>')
  return value
}

export function RunFeedProvider({ children }: { children: ReactNode }) {
  const [run, setRun] = useState<Run | null>(null)
  const [plan, setPlan] = useState<PlannedTest[]>([])
  const [outcomes, setOutcomes] = useState<TestCompletedEvent[]>([])
  const [logs, setLogs] = useState<LogLine[]>([])
  const [starting, setStarting] = useState(false)

  const unsubscribe = useRef<(() => void) | null>(null)
  const logId = useRef(1)

  const log = useCallback((message: string, tone: LogLine['tone'] = 'info') => {
    setLogs((current) => [
      ...current.slice(-299),
      { id: logId.current++, at: Date.now(), tone, message },
    ])
  }, [])

  const handleEvent = useCallback(
    (event: RunEvent) => {
      switch (event.type) {
        case 'run.started':
          setRun(event.run)
          setPlan(event.tests)
          log(
            `Run started · ${event.run.model_label} · ${event.run.total} question${
              event.run.total === 1 ? '' : 's'
            } · T=${event.run.temperature}`,
          )
          break

        case 'test.completed':
          setOutcomes((current) =>
            current.some((o) => o.index === event.index) ? current : [...current, event],
          )
          setRun((current) => (current ? { ...current, completed: event.index } : current))
          log(
            event.status === 'ok'
              ? `[${event.index}/${event.total}] ${event.title} — ${
                  event.metrics?.tokens_per_second ?? 0
                } tok/s in ${event.elapsed}s`
              : `[${event.index}/${event.total}] ${event.title} — FAILED: ${event.error}`,
            event.status === 'ok' ? 'ok' : 'error',
          )
          break

        case 'run.completed':
          setRun(event.run)
          log(`Run complete · report saved as ${event.run.report_name}`, 'ok')
          break

        case 'run.cancelled':
          setRun(event.run)
          log('Run cancelled. Partial report was saved.', 'warn')
          break

        case 'run.failed':
          setRun(event.run)
          log(`Run failed: ${event.message ?? event.run.error ?? 'unknown error'}`, 'error')
          break
      }
    },
    [log],
  )

  const attach = useCallback(
    (runId: string) => {
      unsubscribe.current?.()
      unsubscribe.current = subscribeToRun(runId, handleEvent)
    },
    [handleEvent],
  )

  // Re-attach to whatever the server is running when the app loads.
  useEffect(() => {
    let cancelled = false
    api
      .activeRun()
      .then((active) => {
        if (cancelled || !active) return
        setRun(active)
        setOutcomes([])
        setLogs([])
        attach(active.id)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
      unsubscribe.current?.()
    }
  }, [attach])

  const start = useCallback(
    async (input: {
      provider: string
      model_id: string
      temperature: number
      filenames?: string[]
    }) => {
      setStarting(true)
      try {
        setOutcomes([])
        setPlan([])
        setLogs([])
        const created = await api.startRun(input)
        setRun(created)
        attach(created.id)
      } finally {
        setStarting(false)
      }
    },
    [attach],
  )

  const cancel = useCallback(async () => {
    if (!run) return
    log('Cancelling after the current question finishes…', 'warn')
    await api.cancelRun(run.id)
  }, [run, log])

  const clear = useCallback(() => {
    unsubscribe.current?.()
    unsubscribe.current = null
    setRun(null)
    setPlan([])
    setOutcomes([])
    setLogs([])
  }, [])

  const value = useMemo<RunFeedValue>(
    () => ({
      run,
      plan,
      outcomes,
      logs,
      starting,
      isLive: run?.status === 'running',
      start,
      cancel,
      clear,
      attach,
    }),
    [run, plan, outcomes, logs, starting, start, cancel, clear, attach],
  )

  return <RunFeedContext.Provider value={value}>{children}</RunFeedContext.Provider>
}
