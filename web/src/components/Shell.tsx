/** App chrome: brand rail, navigation, engine status and the live-run beacon. */

import { useEffect, useState, type ReactNode } from 'react'
import {
  BookOpen,
  Cpu,
  FileText,
  FlaskConical,
  Gauge,
  ListChecks,
  Menu,
  Settings2,
  X,
} from 'lucide-react'
import { Logo } from './Logo'
import { pluginIcon } from './PluginBlocks'
import { Link, useRouter } from '../lib/router'
import { api, type Run, type SystemInfo } from '../lib/api'
import { usePluginUI } from '../hooks/usePluginUI'
import { cx } from '../lib/format'

/** Built-ins carry an order so plugin entries can slot between them. */
const NAV = [
  { to: '/', label: 'Run', icon: Gauge, hint: 'Execute the diagnostic suite', order: 10 },
  { to: '/suite', label: 'Testing Suites', icon: ListChecks, hint: 'Browse and author question suites', order: 20 },
  { to: '/reports', label: 'Reports', icon: FileText, hint: 'Read past results', order: 30 },
  { to: '/playground', label: 'Playground', icon: FlaskConical, hint: 'Try a single prompt', order: 40 },
  { to: '/docs', label: 'Docs', icon: BookOpen, hint: 'Plugin framework reference', order: 80 },
  { to: '/settings', label: 'Settings', icon: Settings2, hint: 'Paths and defaults', order: 90 },
]

function isActive(path: string, to: string) {
  return to === '/' ? path === '/' : path.startsWith(to)
}

export function Shell({ children, activeRun }: { children: ReactNode; activeRun: Run | null }) {
  const { path } = useRouter()
  const [system, setSystem] = useState<SystemInfo | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const { nav: pluginNav } = usePluginUI()

  // Plugin entries are merged into the rail rather than fenced off in a
  // section of their own, so a plugin view feels like part of the app.
  const navItems = [
    ...NAV,
    ...pluginNav.map((item) => ({
      to: item.path,
      label: item.label,
      icon: pluginIcon(item.icon),
      hint: item.hint || `From the ${item.slug} plugin`,
      order: item.order,
    })),
  ].sort((a, b) => a.order - b.order || a.label.localeCompare(b.label))

  useEffect(() => {
    api.system().then(setSystem).catch(() => setSystem(null))
  }, [])

  useEffect(() => {
    setDrawerOpen(false)
  }, [path])

  const nav = (
    <nav className="flex flex-col gap-1">
      {navItems.map(({ to, label, icon: Icon, hint }) => {
        const active = isActive(path, to)
        return (
          <Link
            key={to}
            to={to}
            title={hint}
            className={cx(
              'group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-[0.8125rem] font-medium transition-all',
              active
                ? 'bg-navy-750/80 text-ink-100 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.05)]'
                : 'text-ink-400 hover:bg-navy-800/60 hover:text-ink-200',
            )}
          >
            <span
              className={cx(
                'absolute top-1/2 left-0 h-5 w-[3px] -translate-y-1/2 rounded-r-full transition-all',
                active ? 'bg-ember-500' : 'bg-transparent',
              )}
            />
            <Icon size={16} className={active ? 'text-ember-400' : 'text-ink-500 group-hover:text-ink-300'} />
            {label}
            {to === '/' && activeRun && (
              <span className="ml-auto h-1.5 w-1.5 animate-pulse rounded-full bg-ember-400 shadow-[0_0_8px_2px_rgba(244,129,63,0.5)]" />
            )}
          </Link>
        )
      })}
    </nav>
  )

  const engineChip = system && (
    <div className="rounded-xl border border-navy-700 bg-navy-900/50 px-3 py-2.5">
      <div className="flex items-center gap-2 text-[0.6875rem] font-semibold tracking-wide text-ink-400 uppercase">
        <Cpu size={12} className="text-gold-500" />
        Engine
      </div>
      <div className="mt-1 truncate text-[0.75rem] font-medium text-ink-200" title={system.engine_runtime}>
        {system.engine_runtime}
      </div>
      <div className="text-[0.6875rem] text-ink-500">
        {system.engine_architecture}
        {/* The architecture alone is misleading when the installed
            llama-cpp-python is a CPU build: it reports the hardware, not what
            the binary can drive. Saying "CPU build" here is the difference
            between a user seeing "cuda" and assuming the GPU is busy, and
            knowing their card is idle. */}
        {system.engine_gpu_offload === false && (
          <span className="text-amber-400"> · CPU build</span>
        )}
      </div>
      {system.engine_warning && (
        <div className="mt-1.5 text-[0.6875rem] leading-snug text-amber-400">
          {system.engine_warning}
        </div>
      )}
      {!system.template_ok && (
        <div className="mt-1.5 text-[0.6875rem] text-rose-400">Report template missing</div>
      )}
    </div>
  )

  const sidebarBody = (
    <>
      <Link to="/" className="mb-7 flex items-center gap-3">
        <Logo size={32} />
        <div className="leading-tight">
          <div className="text-[0.9375rem] font-semibold tracking-tight text-ink-100">
            LM<span className="text-ember-400">-</span>Gambit
          </div>
          <div className="text-[0.6875rem] text-ink-500">
            Diagnostic suite{system ? ` · v${system.version}` : ''}
          </div>
        </div>
      </Link>
      {nav}
      <div className="mt-auto space-y-2 pt-6">{engineChip}</div>
    </>
  )

  return (
    <div className="flex min-h-screen">
      {/* desktop rail */}
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-navy-700/70 bg-navy-900/45 px-4 py-6 backdrop-blur-xl lg:flex">
        {sidebarBody}
      </aside>

      {/* mobile drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="animate-fade-in absolute inset-0 bg-navy-950/75 backdrop-blur-sm"
            onClick={() => setDrawerOpen(false)}
          />
          <aside className="animate-fade-in relative flex h-full w-64 flex-col border-r border-navy-700 bg-navy-900 px-4 py-6">
            <button
              className="absolute top-5 right-4 text-ink-500 hover:text-ink-200"
              onClick={() => setDrawerOpen(false)}
              aria-label="Close navigation"
            >
              <X size={18} />
            </button>
            {sidebarBody}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-3 border-b border-navy-700/70 px-4 py-3 lg:hidden">
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open navigation"
          >
            <Menu size={16} />
          </button>
          <Logo size={22} />
          <span className="text-sm font-semibold">LM-Gambit</span>
        </div>

        <main className="mx-auto w-full max-w-[1400px] flex-1 px-5 py-7 sm:px-7 lg:px-9">
          {children}
        </main>
      </div>
    </div>
  )
}
