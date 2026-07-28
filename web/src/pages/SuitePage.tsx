/**
 * Testing Suites — browse every suite, edit the custom ones.
 *
 * Two tiers. Built-ins ship with the app and are read-only at both levels: the
 * suite cannot be renamed or deleted, and its questions cannot be edited. That
 * is enforced by the API (409), not by the disabled controls here — this page
 * only reflects it. "Duplicate" is what keeps read-only from being a dead end.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import {
  ArrowDown,
  ArrowUp,
  Copy,
  FolderPlus,
  Info,
  Layers,
  ListChecks,
  Lock,
  Pencil,
  Plus,
  RotateCcw,
  Save,
  Trash2,
} from 'lucide-react'
import {
  Card,
  CardHeader,
  ConfirmDialog,
  EmptyState,
  ErrorNote,
  PageHeader,
  SkeletonRows,
  Spinner,
  useAsync,
  useToast,
} from '../components/ui'
import { PluginSlot } from '../components/PluginBlocks'
import { api, ApiError, type SuiteDetail, type SuiteSummary } from '../lib/api'
import { cx, deriveTitle } from '../lib/format'
import { useRunFeed } from '../hooks/useRunFeed'

interface Draft {
  key: string
  prompt: string
  filename: string | null
}

let keySeed = 1
const newKey = () => `q${keySeed++}`

const PLACEHOLDER =
  'Write the question exactly as the model should receive it.\n\n' +
  'Example: Analyze the sentiment of the following customer review.'

export function SuitePage() {
  const toast = useToast()
  const { isLive } = useRunFeed()

  const suites = useAsync(() => api.suites(), [])
  const [activeSlug, setActiveSlug] = useState<string | null>(null)
  const [detail, setDetail] = useState<SuiteDetail | null>(null)
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [baseline, setBaseline] = useState<string[]>([])
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [busy, setBusy] = useState(false)

  const [focusKey, setFocusKey] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)
  const [confirmDiscard, setConfirmDiscard] = useState(false)
  const [pendingSwitch, setPendingSwitch] = useState<string | null>(null)
  const [deleteSuiteOpen, setDeleteSuiteOpen] = useState(false)
  const [dialog, setDialog] = useState<null | { mode: 'create' | 'rename' | 'duplicate' }>(null)

  const list = suites.data ?? []
  const builtins = list.filter((s) => s.builtin)
  const customs = list.filter((s) => !s.builtin)
  const readOnly = detail?.builtin ?? true

  // Select something as soon as the list arrives.
  useEffect(() => {
    if (!activeSlug && list.length) setActiveSlug(list[0].slug)
  }, [list, activeSlug])

  const loadDetail = useCallback((slug: string) => {
    setLoadingDetail(true)
    setDetailError(null)
    api
      .suite(slug)
      .then((data) => {
        setDetail(data)
        setDrafts(
          data.tests.map((t) => ({ key: newKey(), prompt: t.prompt, filename: t.filename })),
        )
        setBaseline(data.tests.map((t) => t.prompt))
      })
      .catch((cause: unknown) =>
        setDetailError(cause instanceof Error ? cause.message : String(cause)),
      )
      .finally(() => setLoadingDetail(false))
  }, [])

  useEffect(() => {
    if (activeSlug) loadDetail(activeSlug)
  }, [activeSlug, loadDetail])

  const current = drafts.map((d) => d.prompt)
  const dirty =
    !readOnly &&
    (current.length !== baseline.length ||
      current.some((p, i) => p.trim() !== baseline[i]?.trim()))

  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  /** Switching away from unsaved edits asks first. */
  const selectSuite = (slug: string) => {
    if (slug === activeSlug) return
    if (dirty) setPendingSwitch(slug)
    else setActiveSlug(slug)
  }

  /* ------------------------------------------------------------ questions */

  const update = (key: string, prompt: string) =>
    setDrafts((l) => l.map((d) => (d.key === key ? { ...d, prompt } : d)))

  const addQuestion = () => {
    const key = newKey()
    setDrafts((l) => [...l, { key, prompt: '', filename: null }])
    setFocusKey(key)
  }

  const duplicateQuestion = (key: string) =>
    setDrafts((l) => {
      const i = l.findIndex((d) => d.key === key)
      if (i < 0) return l
      return [...l.slice(0, i + 1), { key: newKey(), prompt: l[i].prompt, filename: null }, ...l.slice(i + 1)]
    })

  const removeQuestion = (key: string) => setDrafts((l) => l.filter((d) => d.key !== key))

  const move = (key: string, direction: -1 | 1) =>
    setDrafts((l) => {
      const i = l.findIndex((d) => d.key === key)
      const target = i + direction
      if (i < 0 || target < 0 || target >= l.length) return l
      const next = [...l]
      ;[next[i], next[target]] = [next[target], next[i]]
      return next
    })

  const save = async () => {
    if (!detail) return
    const blank = drafts.findIndex((d) => !d.prompt.trim())
    if (blank >= 0) {
      toast(`Question ${blank + 1} is empty. Add a prompt or remove it.`, 'error')
      return
    }
    setSaving(true)
    try {
      const saved = await api.saveSuiteTests(detail.slug, drafts.map((d) => d.prompt))
      setDetail(saved)
      setDrafts(saved.tests.map((t) => ({ key: newKey(), prompt: t.prompt, filename: t.filename })))
      setBaseline(saved.tests.map((t) => t.prompt))
      suites.reload()
      toast(`Saved ${saved.tests.length} question${saved.tests.length === 1 ? '' : 's'} to ${saved.name}.`, 'success')
    } catch (cause) {
      toast(cause instanceof ApiError ? cause.message : String(cause), 'error')
    } finally {
      setSaving(false)
    }
  }

  /* --------------------------------------------------------------- suites */

  const submitDialog = async (name: string, description: string) => {
    if (!name.trim()) return
    setBusy(true)
    try {
      let result: SuiteDetail
      if (dialog?.mode === 'create') {
        result = await api.createSuite({ name, description })
        toast(`Created "${result.name}".`, 'success')
      } else if (dialog?.mode === 'duplicate') {
        result = await api.duplicateSuite(detail!.slug, name)
        toast(`Copied to "${result.name}" — this one is editable.`, 'success')
      } else {
        result = await api.updateSuite(detail!.slug, { name, description })
        toast('Suite renamed.', 'success')
      }
      setDialog(null)
      await suites.reload()
      setActiveSlug(result.slug)
      if (result.slug === activeSlug) loadDetail(result.slug)
    } catch (cause) {
      toast(cause instanceof ApiError ? cause.message : String(cause), 'error')
    } finally {
      setBusy(false)
    }
  }

  const deleteSuite = async () => {
    if (!detail) return
    setDeleteSuiteOpen(false)
    setBusy(true)
    try {
      await api.deleteSuite(detail.slug)
      toast(`Deleted "${detail.name}".`, 'success')
      setActiveSlug(null)
      setDetail(null)
      await suites.reload()
    } catch (cause) {
      toast(cause instanceof ApiError ? cause.message : String(cause), 'error')
    } finally {
      setBusy(false)
    }
  }

  const deletingQuestion = drafts.find((d) => d.key === pendingDelete)

  return (
    <>
      <PageHeader
        title="Testing Suites"
        subtitle="Questions are grouped into named suites. Built-in suites ship with the app and are read-only; duplicate one to make it yours."
        actions={
          <>
            {dirty && (
              <button className="btn btn-ghost" onClick={() => setConfirmDiscard(true)} disabled={saving}>
                <RotateCcw size={14} />
                Discard
              </button>
            )}
            {!readOnly && detail && (
              <button className="btn btn-primary" onClick={save} disabled={!dirty || saving || isLive}>
                {saving ? <Spinner /> : <Save size={14} />}
                {saving ? 'Saving…' : dirty ? 'Save questions' : 'Saved'}
              </button>
            )}
          </>
        }
      />

      {isLive && (
        <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-ember-500/35 bg-ember-500/8 px-4 py-3">
          <Info size={15} className="mt-0.5 shrink-0 text-ember-400" />
          <p className="text-[0.8125rem] text-ember-300">
            A run is in progress. Editing is blocked until it finishes.
          </p>
        </div>
      )}

      {suites.error && <ErrorNote message={suites.error} onRetry={suites.reload} />}

      <div className="grid gap-5 xl:grid-cols-12">
        {/* ------------------------------------------------- suite list */}
        <div className="xl:col-span-4">
          <Card className="xl:sticky xl:top-6">
            <CardHeader
              title="Suites"
              icon={<Layers size={14} />}
              actions={
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => setDialog({ mode: 'create' })}
                  disabled={busy || isLive}
                >
                  <FolderPlus size={13} />
                  New
                </button>
              }
            />

            {suites.loading && !list.length ? (
              <SkeletonRows rows={4} />
            ) : (
              <div className="p-2">
                <SuiteGroup label="Built-in" hint="read-only">
                  {builtins.map((s) => (
                    <SuiteRow
                      key={s.slug}
                      suite={s}
                      active={s.slug === activeSlug}
                      onClick={() => selectSuite(s.slug)}
                    />
                  ))}
                </SuiteGroup>

                <SuiteGroup label="Custom" hint={customs.length ? 'editable' : undefined}>
                  {customs.length ? (
                    customs.map((s) => (
                      <SuiteRow
                        key={s.slug}
                        suite={s}
                        active={s.slug === activeSlug}
                        onClick={() => selectSuite(s.slug)}
                      />
                    ))
                  ) : (
                    <p className="px-2.5 py-3 text-[0.75rem] leading-relaxed text-ink-500">
                      None yet. Duplicate a built-in suite, or create an empty one.
                    </p>
                  )}
                </SuiteGroup>
              </div>
            )}
          </Card>

          <PluginSlot slot="suite.aside" className="mt-4" />
        </div>

        {/* ---------------------------------------------- selected suite */}
        <div className="space-y-3 xl:col-span-8">
          {detailError && <ErrorNote message={detailError} onRetry={() => activeSlug && loadDetail(activeSlug)} />}

          {loadingDetail && !detail ? (
            <Card>
              <SkeletonRows rows={4} />
            </Card>
          ) : !detail ? (
            <Card>
              <EmptyState
                icon={<Layers size={20} />}
                title="No suite selected"
                description="Pick one on the left, or create a new custom suite."
              />
            </Card>
          ) : (
            <>
              <Card raised>
                <div className="flex flex-wrap items-start justify-between gap-3 p-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <h2 className="text-[0.9375rem] font-semibold text-ink-100">{detail.name}</h2>
                      {detail.builtin ? (
                        <span className="flex items-center gap-1 rounded border border-gold-500/30 bg-gold-500/10 px-1.5 py-0.5 text-[0.625rem] text-gold-400">
                          <Lock size={9} /> built-in
                        </span>
                      ) : (
                        <span className="rounded border border-mint-500/30 bg-mint-500/10 px-1.5 py-0.5 text-[0.625rem] text-mint-400">
                          custom
                        </span>
                      )}
                    </div>
                    <p className="mt-1 max-w-xl text-[0.8125rem] leading-relaxed text-ink-400">
                      {detail.description || 'No description.'}
                    </p>
                    <p className="mt-1.5 text-[0.6875rem] text-ink-500">
                      <code className="font-mono">{detail.slug}</code> · {drafts.length} question
                      {drafts.length === 1 ? '' : 's'}
                      {dirty && <span className="ml-1.5 text-ember-400">· unsaved</span>}
                    </p>
                  </div>

                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => setDialog({ mode: 'duplicate' })}
                      disabled={busy || isLive}
                      title="Clone this suite into an editable custom one"
                    >
                      <Copy size={13} />
                      Duplicate
                    </button>
                    {!readOnly && (
                      <>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => setDialog({ mode: 'rename' })}
                          disabled={busy || isLive}
                        >
                          <Pencil size={13} />
                          Rename
                        </button>
                        <button
                          className="btn btn-ghost btn-sm text-rose-400 hover:bg-rose-500/10"
                          onClick={() => setDeleteSuiteOpen(true)}
                          disabled={busy || isLive}
                        >
                          <Trash2 size={13} />
                          Delete
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {readOnly && (
                  <div className="flex items-start gap-2.5 border-t border-navy-700 bg-gold-500/5 px-4 py-3">
                    <Lock size={14} className="mt-0.5 shrink-0 text-gold-400" />
                    <p className="text-[0.75rem] leading-relaxed text-gold-300">
                      This suite ships with the app, so its questions cannot be changed. Use{' '}
                      <strong>Duplicate</strong> to get an editable copy — the original stays intact
                      as a stable baseline for comparing models.
                    </p>
                  </div>
                )}
              </Card>

              {drafts.length === 0 ? (
                <Card>
                  <EmptyState
                    icon={<ListChecks size={20} />}
                    title="No questions yet"
                    description={
                      readOnly
                        ? 'This suite is empty.'
                        : 'Add your first question to start benchmarking.'
                    }
                    action={
                      readOnly ? undefined : (
                        <button className="btn btn-primary" onClick={addQuestion}>
                          <Plus size={14} />
                          Add question
                        </button>
                      )
                    }
                  />
                </Card>
              ) : (
                drafts.map((draft, index) => (
                  <QuestionCard
                    key={draft.key}
                    draft={draft}
                    index={index}
                    total={drafts.length}
                    readOnly={readOnly}
                    autoFocus={focusKey === draft.key}
                    onFocused={() => setFocusKey(null)}
                    onChange={(prompt) => update(draft.key, prompt)}
                    onMoveUp={() => move(draft.key, -1)}
                    onMoveDown={() => move(draft.key, 1)}
                    onDuplicate={() => duplicateQuestion(draft.key)}
                    onDelete={() =>
                      draft.prompt.trim() ? setPendingDelete(draft.key) : removeQuestion(draft.key)
                    }
                  />
                ))
              )}

              {!readOnly && drafts.length > 0 && (
                <button
                  className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-navy-600 py-3.5 text-[0.8125rem] font-medium text-ink-400 transition-colors hover:border-ember-500/60 hover:bg-ember-500/5 hover:text-ember-400"
                  onClick={addQuestion}
                >
                  <Plus size={15} />
                  Add question
                </button>
              )}
            </>
          )}
        </div>
      </div>

      <SuiteDialog
        open={!!dialog}
        mode={dialog?.mode ?? 'create'}
        busy={busy}
        initialName={
          dialog?.mode === 'rename'
            ? (detail?.name ?? '')
            : dialog?.mode === 'duplicate'
              ? `${detail?.name ?? 'Suite'} (copy)`
              : ''
        }
        initialDescription={dialog?.mode === 'rename' ? (detail?.description ?? '') : ''}
        onSubmit={submitDialog}
        onCancel={() => setDialog(null)}
      />

      <ConfirmDialog
        open={deleteSuiteOpen}
        title={`Delete "${detail?.name}"?`}
        body={`This removes the suite and all ${drafts.length} of its questions from disk. This cannot be undone.`}
        confirmLabel="Delete suite"
        destructive
        onConfirm={deleteSuite}
        onCancel={() => setDeleteSuiteOpen(false)}
      />

      <ConfirmDialog
        open={confirmDiscard}
        title="Discard changes?"
        body="Your unsaved edits will be replaced with the questions currently on disk."
        confirmLabel="Discard"
        destructive
        onConfirm={() => {
          setConfirmDiscard(false)
          if (activeSlug) loadDetail(activeSlug)
        }}
        onCancel={() => setConfirmDiscard(false)}
      />

      <ConfirmDialog
        open={!!pendingSwitch}
        title="Leave without saving?"
        body="You have unsaved edits in this suite. Switching will discard them."
        confirmLabel="Discard and switch"
        destructive
        onConfirm={() => {
          setActiveSlug(pendingSwitch)
          setPendingSwitch(null)
        }}
        onCancel={() => setPendingSwitch(null)}
      />

      <ConfirmDialog
        open={!!deletingQuestion}
        title="Delete this question?"
        body={deriveTitle(deletingQuestion?.prompt ?? '', 'This question')}
        confirmLabel="Delete"
        destructive
        onConfirm={() => {
          if (pendingDelete) removeQuestion(pendingDelete)
          setPendingDelete(null)
        }}
        onCancel={() => setPendingDelete(null)}
      />
    </>
  )
}

/* -------------------------------------------------------------- suite list */

function SuiteGroup({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div className="mb-1 last:mb-0">
      <div className="flex items-baseline gap-2 px-2.5 pt-2 pb-1">
        <span className="text-[0.625rem] font-semibold tracking-[0.09em] text-ink-500 uppercase">
          {label}
        </span>
        {hint && <span className="text-[0.625rem] text-ink-600">{hint}</span>}
      </div>
      <div className="space-y-0.5">{children}</div>
    </div>
  )
}

function SuiteRow({
  suite,
  active,
  onClick,
}: {
  suite: SuiteSummary
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={cx(
        'flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors',
        active ? 'bg-navy-750 text-ink-100' : 'text-ink-300 hover:bg-navy-800/60',
      )}
    >
      {suite.builtin ? (
        <Lock size={12} className={cx('shrink-0', active ? 'text-gold-400' : 'text-ink-500')} />
      ) : (
        <ListChecks size={12} className={cx('shrink-0', active ? 'text-mint-400' : 'text-ink-500')} />
      )}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[0.8125rem] font-medium">{suite.name}</span>
        <span className="block truncate text-[0.6875rem] text-ink-500">{suite.slug}</span>
      </span>
      <span className="num shrink-0 text-[0.6875rem] text-ink-500">{suite.count}</span>
    </button>
  )
}

/* ----------------------------------------------------------- name dialog */

function SuiteDialog({
  open,
  mode,
  busy,
  initialName,
  initialDescription,
  onSubmit,
  onCancel,
}: {
  open: boolean
  mode: 'create' | 'rename' | 'duplicate'
  busy: boolean
  initialName: string
  initialDescription: string
  onSubmit: (name: string, description: string) => void
  onCancel: () => void
}) {
  const [name, setName] = useState(initialName)
  const [description, setDescription] = useState(initialDescription)

  useEffect(() => {
    if (open) {
      setName(initialName)
      setDescription(initialDescription)
    }
  }, [open, initialName, initialDescription])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onCancel])

  if (!open) return null

  const copy = {
    create: { title: 'New suite', action: 'Create suite' },
    rename: { title: 'Rename suite', action: 'Save' },
    duplicate: { title: 'Duplicate to a custom suite', action: 'Duplicate' },
  }[mode]

  return (
    <div
      className="animate-fade-in fixed inset-0 z-50 flex items-center justify-center bg-navy-950/75 p-5 backdrop-blur-sm"
      onClick={onCancel}
    >
      <form
        className="surface-raised animate-fade-up w-full max-w-md p-5"
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault()
          onSubmit(name, description)
        }}
      >
        <h3 className="text-[0.9375rem] font-semibold text-ink-100">{copy.title}</h3>

        <label className="label mt-4 block" htmlFor="suite-name">
          Name
        </label>
        <input
          id="suite-name"
          className="field"
          value={name}
          autoFocus
          maxLength={80}
          placeholder="e.g. Domain knowledge"
          onChange={(event) => setName(event.target.value)}
        />

        {mode !== 'duplicate' && (
          <>
            <label className="label mt-3 block" htmlFor="suite-description">
              Description <span className="text-ink-600">(optional)</span>
            </label>
            <input
              id="suite-description"
              className="field"
              value={description}
              placeholder="What this suite covers"
              onChange={(event) => setDescription(event.target.value)}
            />
          </>
        )}

        {mode === 'duplicate' && (
          <p className="mt-3 text-[0.75rem] leading-relaxed text-ink-500">
            Copies every question into a new custom suite you can edit. The original is
            untouched.
          </p>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={!name.trim() || busy}>
            {busy && <Spinner className="h-3.5 w-3.5" />}
            {copy.action}
          </button>
        </div>
      </form>
    </div>
  )
}

/* ------------------------------------------------------------- question */

function QuestionCard({
  draft,
  index,
  total,
  readOnly,
  autoFocus,
  onFocused,
  onChange,
  onMoveUp,
  onMoveDown,
  onDuplicate,
  onDelete,
}: {
  draft: Draft
  index: number
  total: number
  readOnly: boolean
  autoFocus: boolean
  onFocused: () => void
  onChange: (prompt: string) => void
  onMoveUp: () => void
  onMoveDown: () => void
  onDuplicate: () => void
  onDelete: () => void
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const title = deriveTitle(draft.prompt, 'Untitled question')
  const empty = !draft.prompt.trim()
  const words = draft.prompt.trim() ? draft.prompt.trim().split(/\s+/).length : 0

  useLayoutEffect(() => {
    const node = textareaRef.current
    if (!node) return
    node.style.height = 'auto'
    node.style.height = `${Math.max(node.scrollHeight, 92)}px`
  }, [draft.prompt])

  useEffect(() => {
    if (autoFocus) {
      textareaRef.current?.focus()
      onFocused()
    }
  }, [autoFocus, onFocused])

  return (
    <Card className={cx('animate-fade-up overflow-hidden', empty && !readOnly && 'border-ember-500/40')}>
      <div className="flex items-center gap-3 border-b border-navy-700 px-3.5 py-2.5">
        <span
          className={cx(
            'num flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-[0.6875rem] font-semibold',
            empty && !readOnly ? 'bg-ember-500/15 text-ember-400' : 'bg-gold-500/12 text-gold-400',
          )}
        >
          {index + 1}
        </span>

        <span
          className={cx(
            'min-w-0 flex-1 truncate text-[0.8125rem] font-medium',
            empty ? 'text-ink-500 italic' : 'text-ink-100',
          )}
          title={title}
        >
          {empty ? 'Empty question — add a prompt' : title}
        </span>

        <span className="hidden shrink-0 items-center gap-2 text-[0.6875rem] text-ink-500 sm:flex">
          {draft.filename && <span className="font-mono">{draft.filename}</span>}
          <span className="num">{words}w</span>
        </span>

        {readOnly ? (
          <Lock size={12} className="shrink-0 text-ink-600" aria-label="Read-only" />
        ) : (
          <div className="flex shrink-0 items-center gap-0.5">
            <IconButton label="Move up" disabled={index === 0} onClick={onMoveUp}>
              <ArrowUp size={13} />
            </IconButton>
            <IconButton label="Move down" disabled={index === total - 1} onClick={onMoveDown}>
              <ArrowDown size={13} />
            </IconButton>
            <IconButton label="Duplicate" onClick={onDuplicate}>
              <Copy size={13} />
            </IconButton>
            <IconButton label="Delete" danger onClick={onDelete}>
              <Trash2 size={13} />
            </IconButton>
          </div>
        )}
      </div>

      <textarea
        ref={textareaRef}
        value={draft.prompt}
        readOnly={readOnly}
        onChange={(event) => onChange(event.target.value)}
        placeholder={PLACEHOLDER}
        spellCheck={false}
        className={cx(
          'w-full resize-none border-0 bg-transparent px-4 py-3.5 font-mono text-[0.8125rem] leading-relaxed placeholder:text-ink-500/70 focus:outline-none',
          readOnly ? 'cursor-default text-ink-300' : 'text-ink-200',
        )}
      />
    </Card>
  )
}

function IconButton({
  children,
  label,
  onClick,
  disabled,
  danger,
}: {
  children: React.ReactNode
  label: string
  onClick: () => void
  disabled?: boolean
  danger?: boolean
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
      className={cx(
        'flex h-6.5 w-6.5 items-center justify-center rounded-md p-1 transition-colors disabled:cursor-not-allowed disabled:opacity-30',
        danger
          ? 'text-ink-500 hover:bg-rose-500/15 hover:text-rose-400'
          : 'text-ink-500 hover:bg-navy-750 hover:text-ink-200',
      )}
    >
      {children}
    </button>
  )
}
