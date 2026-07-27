/** Shared presentational primitives. */

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
import { AlertTriangle, CheckCircle2, Info, Loader2, X } from 'lucide-react'
import { cx } from '../lib/format'

/* ------------------------------------------------------------------ layout */

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string
  subtitle?: string
  actions?: ReactNode
}) {
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-[1.6rem] leading-tight font-semibold text-ink-100">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-[0.8125rem] text-ink-400">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}

export function Card({
  children,
  className,
  raised,
}: {
  children: ReactNode
  className?: string
  raised?: boolean
}) {
  return <section className={cx(raised ? 'surface-raised' : 'surface', className)}>{children}</section>
}

export function CardHeader({
  title,
  icon,
  actions,
  hint,
}: {
  title: string
  icon?: ReactNode
  actions?: ReactNode
  hint?: string
}) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-navy-700 px-4 py-3">
      <div className="min-w-0">
        <h2 className="flex items-center gap-2 text-[0.8125rem] font-semibold tracking-wide text-ink-200">
          {icon && <span className="text-gold-500">{icon}</span>}
          {title}
        </h2>
        {hint && <p className="mt-0.5 text-[0.6875rem] text-ink-500">{hint}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}

/* ------------------------------------------------------------------- stats */

export function StatTile({
  label,
  value,
  unit,
  tone = 'gold',
  hint,
}: {
  label: string
  value: string | number
  unit?: string
  tone?: 'gold' | 'ember' | 'mint' | 'rose' | 'neutral'
  hint?: string
}) {
  const toneClass = {
    gold: 'text-gold-400',
    ember: 'text-ember-400',
    mint: 'text-mint-400',
    rose: 'text-rose-400',
    neutral: 'text-ink-200',
  }[tone]

  return (
    <div className="surface px-3.5 py-3">
      <div className="text-[0.625rem] font-semibold tracking-[0.09em] text-ink-500 uppercase">
        {label}
      </div>
      <div className={cx('num mt-1 flex items-baseline gap-1 text-[1.35rem] font-semibold', toneClass)}>
        {value}
        {unit && <span className="text-[0.7rem] font-medium text-ink-500">{unit}</span>}
      </div>
      {hint && <div className="mt-0.5 text-[0.6875rem] text-ink-500">{hint}</div>}
    </div>
  )
}

/* ------------------------------------------------------------------ states */

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cx('animate-spin', className)} size={15} />
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: ReactNode
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full border border-navy-700 bg-navy-800/60 text-ink-500">
        {icon}
      </div>
      <h3 className="text-sm font-semibold text-ink-200">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-[0.8125rem] text-ink-500">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-3">
      <AlertTriangle size={16} className="mt-0.5 shrink-0 text-rose-400" />
      <div className="min-w-0 flex-1">
        <p className="text-[0.8125rem] break-words text-rose-400">{message}</p>
        {onRetry && (
          <button className="btn btn-ghost btn-sm mt-2" onClick={onRetry}>
            Try again
          </button>
        )}
      </div>
    </div>
  )
}

export function SkeletonRows({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-4">
      {Array.from({ length: rows }).map((_, index) => (
        <div
          key={index}
          className="relative h-11 overflow-hidden rounded-lg border border-navy-700 bg-navy-800/40"
        >
          <div className="animate-sweep absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-navy-700/50 to-transparent" />
        </div>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ toasts */

type ToastTone = 'success' | 'error' | 'info'
interface Toast {
  id: number
  tone: ToastTone
  message: string
}

const ToastContext = createContext<(message: string, tone?: ToastTone) => void>(() => {})

export function useToast() {
  return useContext(ToastContext)
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(1)

  const push = useCallback((message: string, tone: ToastTone = 'info') => {
    const id = nextId.current++
    setToasts((current) => [...current, { id, tone, message }])
    setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), 5200)
  }, [])

  const dismiss = (id: number) => setToasts((current) => current.filter((t) => t.id !== id))

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed right-5 bottom-5 z-50 flex w-[min(23rem,calc(100vw-2.5rem))] flex-col gap-2">
        {toasts.map((toast) => {
          const Icon = { success: CheckCircle2, error: AlertTriangle, info: Info }[toast.tone]
          const tone = {
            success: 'border-mint-500/45 text-mint-400',
            error: 'border-rose-500/45 text-rose-400',
            info: 'border-navy-600 text-ink-300',
          }[toast.tone]
          return (
            <div
              key={toast.id}
              className={cx(
                'animate-fade-up pointer-events-auto flex items-start gap-2.5 rounded-xl border bg-navy-850/95 px-3.5 py-2.5 shadow-[0_18px_40px_-20px_rgba(0,0,0,0.9)] backdrop-blur',
                tone,
              )}
            >
              <Icon size={15} className="mt-0.5 shrink-0" />
              <p className="min-w-0 flex-1 text-[0.8125rem] break-words text-ink-200">
                {toast.message}
              </p>
              <button
                className="shrink-0 text-ink-500 transition-colors hover:text-ink-200"
                onClick={() => dismiss(toast.id)}
                aria-label="Dismiss"
              >
                <X size={14} />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

/* ------------------------------------------------------------------- modal */

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = 'Confirm',
  destructive,
  onConfirm,
  onCancel,
}: {
  open: boolean
  title: string
  body: string
  confirmLabel?: string
  destructive?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onCancel])

  if (!open) return null

  return (
    <div
      className="animate-fade-in fixed inset-0 z-50 flex items-center justify-center bg-navy-950/75 p-5 backdrop-blur-sm"
      onClick={onCancel}
    >
      <div
        className="surface-raised animate-fade-up w-full max-w-sm p-5"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <h3 className="text-[0.9375rem] font-semibold text-ink-100">{title}</h3>
        <p className="mt-2 text-[0.8125rem] text-ink-400">{body}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button className="btn btn-ghost" onClick={onCancel}>
            Cancel
          </button>
          <button
            className={cx('btn', destructive ? 'btn-danger' : 'btn-primary')}
            onClick={onConfirm}
            autoFocus
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ slider */

export function TemperatureSlider({
  value,
  onChange,
  disabled,
}: {
  value: number
  onChange: (next: number) => void
  disabled?: boolean
}) {
  const percent = Math.min(100, Math.max(0, (value / 1) * 100))
  const descriptor = value <= 0.15 ? 'Deterministic' : value <= 0.5 ? 'Balanced' : 'Creative'

  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="label mb-0">Temperature</span>
        <span className="num text-[0.8125rem] font-semibold text-gold-400">{value.toFixed(2)}</span>
      </div>
      <input
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full outline-none disabled:cursor-not-allowed disabled:opacity-50 [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-navy-950 [&::-webkit-slider-thumb]:bg-gold-400 [&::-webkit-slider-thumb]:shadow-[0_0_0_3px_rgba(227,173,70,0.22)]"
        style={{
          background: `linear-gradient(90deg, var(--color-gold-500) 0%, var(--color-gold-500) ${percent}%, var(--color-navy-700) ${percent}%, var(--color-navy-700) 100%)`,
        }}
      />
      <div className="mt-1 text-[0.6875rem] text-ink-500">{descriptor}</div>
    </div>
  )
}

/* -------------------------------------------------------------- data hooks */

export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    loader()
      .then((value) => {
        if (!cancelled) setData(value)
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
  }, [...deps, nonce])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  return useMemo(
    () => ({ data, error, loading, reload, setData }),
    [data, error, loading, reload],
  )
}
