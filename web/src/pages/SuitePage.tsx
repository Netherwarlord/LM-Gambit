import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import {
  ArrowDown,
  ArrowUp,
  Copy,
  Info,
  ListChecks,
  Plus,
  RotateCcw,
  Save,
  Trash2,
} from 'lucide-react'
import {
  Card,
  ConfirmDialog,
  EmptyState,
  ErrorNote,
  PageHeader,
  SkeletonRows,
  Spinner,
  useToast,
} from '../components/ui'
import { api, ApiError } from '../lib/api'
import { cx, deriveTitle } from '../lib/format'
import { useRunFeed } from '../hooks/useRunFeed'

interface Draft {
  key: string
  prompt: string
  filename: string | null
}

let keySeed = 1
const newKey = () => `q${keySeed++}`

export function SuitePage() {
  const toast = useToast()
  const { isLive } = useRunFeed()

  const [drafts, setDrafts] = useState<Draft[]>([])
  const [baseline, setBaseline] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [confirmDiscard, setConfirmDiscard] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)
  const [focusKey, setFocusKey] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setLoadError(null)
    api
      .tests()
      .then((suite) => {
        setDrafts(
          suite.tests.map((test) => ({
            key: newKey(),
            prompt: test.prompt,
            filename: test.filename,
          })),
        )
        setBaseline(suite.tests.map((test) => test.prompt))
      })
      .catch((cause: unknown) =>
        setLoadError(cause instanceof Error ? cause.message : String(cause)),
      )
      .finally(() => setLoading(false))
  }, [])

  useEffect(load, [load])

  const current = drafts.map((draft) => draft.prompt)
  const dirty =
    current.length !== baseline.length ||
    current.some((prompt, index) => prompt.trim() !== baseline[index]?.trim())

  // Guard against losing edits on reload / close.
  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const update = (key: string, prompt: string) =>
    setDrafts((list) => list.map((d) => (d.key === key ? { ...d, prompt } : d)))

  const addQuestion = () => {
    const key = newKey()
    setDrafts((list) => [...list, { key, prompt: '', filename: null }])
    setFocusKey(key)
  }

  const duplicate = (key: string) =>
    setDrafts((list) => {
      const index = list.findIndex((d) => d.key === key)
      if (index < 0) return list
      const copy = { key: newKey(), prompt: list[index].prompt, filename: null }
      return [...list.slice(0, index + 1), copy, ...list.slice(index + 1)]
    })

  const remove = (key: string) => setDrafts((list) => list.filter((d) => d.key !== key))

  const move = (key: string, direction: -1 | 1) =>
    setDrafts((list) => {
      const index = list.findIndex((d) => d.key === key)
      const target = index + direction
      if (index < 0 || target < 0 || target >= list.length) return list
      const next = [...list]
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })

  const save = async () => {
    const blank = drafts.findIndex((d) => !d.prompt.trim())
    if (blank >= 0) {
      toast(`Question ${blank + 1} is empty. Add a prompt or remove it.`, 'error')
      return
    }
    setSaving(true)
    try {
      const suite = await api.saveTests(drafts.map((d) => d.prompt))
      setDrafts(
        suite.tests.map((test) => ({
          key: newKey(),
          prompt: test.prompt,
          filename: test.filename,
        })),
      )
      setBaseline(suite.tests.map((test) => test.prompt))
      toast(
        `Saved ${suite.tests.length} question${suite.tests.length === 1 ? '' : 's'} to the suite.`,
        'success',
      )
    } catch (cause) {
      toast(cause instanceof ApiError ? cause.message : String(cause), 'error')
    } finally {
      setSaving(false)
    }
  }

  const deleting = drafts.find((d) => d.key === pendingDelete)

  return (
    <>
      <PageHeader
        title="Suite Builder"
        subtitle="Each box is one question. They are sent to the model one at a time, in this order."
        actions={
          <>
            {dirty && (
              <button
                className="btn btn-ghost"
                onClick={() => setConfirmDiscard(true)}
                disabled={saving}
              >
                <RotateCcw size={14} />
                Discard
              </button>
            )}
            <button className="btn btn-primary" onClick={save} disabled={!dirty || saving || isLive}>
              {saving ? <Spinner /> : <Save size={14} />}
              {saving ? 'Saving…' : dirty ? 'Save suite' : 'Saved'}
            </button>
          </>
        }
      />

      {isLive && (
        <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-ember-500/35 bg-ember-500/8 px-4 py-3">
          <Info size={15} className="mt-0.5 shrink-0 text-ember-400" />
          <p className="text-[0.8125rem] text-ember-300">
            A run is in progress. You can edit questions, but saving is blocked until it finishes.
          </p>
        </div>
      )}

      {loadError && <ErrorNote message={loadError} onRetry={load} />}

      {loading ? (
        <Card>
          <SkeletonRows rows={4} />
        </Card>
      ) : (
        <div className="grid gap-5 xl:grid-cols-12">
          <div className="space-y-3 xl:col-span-9">
            {drafts.length === 0 ? (
              <Card>
                <EmptyState
                  icon={<ListChecks size={20} />}
                  title="The suite is empty"
                  description="Add your first question to start benchmarking."
                  action={
                    <button className="btn btn-primary" onClick={addQuestion}>
                      <Plus size={14} />
                      Add question
                    </button>
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
                  autoFocus={focusKey === draft.key}
                  onFocused={() => setFocusKey(null)}
                  onChange={(prompt) => update(draft.key, prompt)}
                  onMoveUp={() => move(draft.key, -1)}
                  onMoveDown={() => move(draft.key, 1)}
                  onDuplicate={() => duplicate(draft.key)}
                  onDelete={() =>
                    draft.prompt.trim() ? setPendingDelete(draft.key) : remove(draft.key)
                  }
                />
              ))
            )}

            {drafts.length > 0 && (
              <button
                className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-navy-600 py-3.5 text-[0.8125rem] font-medium text-ink-400 transition-colors hover:border-ember-500/60 hover:bg-ember-500/5 hover:text-ember-400"
                onClick={addQuestion}
              >
                <Plus size={15} />
                Add question
              </button>
            )}
          </div>

          <aside className="xl:col-span-3">
            <div className="sticky top-6 space-y-3">
              <Card>
                <div className="p-4">
                  <div className="text-[0.625rem] font-semibold tracking-[0.09em] text-ink-500 uppercase">
                    Suite
                  </div>
                  <div className="num mt-1 text-[1.6rem] font-semibold text-gold-400">
                    {drafts.length}
                  </div>
                  <div className="text-[0.75rem] text-ink-500">
                    question{drafts.length === 1 ? '' : 's'}
                    {dirty && <span className="ml-1.5 text-ember-400">· unsaved</span>}
                  </div>
                </div>
              </Card>

              <Card>
                <div className="space-y-2.5 p-4 text-[0.75rem] leading-relaxed text-ink-400">
                  <p className="flex items-center gap-1.5 font-semibold text-ink-300">
                    <Info size={13} className="text-gold-500" />
                    How saving works
                  </p>
                  <p>
                    The whole prompt is sent to the model. Its{' '}
                    <span className="text-ink-200">first line</span> doubles as the title in reports,
                    so lead with the task.
                  </p>
                  <p>
                    Saving rewrites the suite as{' '}
                    <code className="rounded bg-navy-750 px-1 py-0.5 font-mono text-[0.6875rem] text-gold-300">
                      test1.txt … testN.txt
                    </code>{' '}
                    in this order, so the CLI (
                    <code className="font-mono text-[0.6875rem]">auto-test.py</code>) sees exactly
                    what you see here.
                  </p>
                </div>
              </Card>
            </div>
          </aside>
        </div>
      )}

      <ConfirmDialog
        open={confirmDiscard}
        title="Discard changes?"
        body="Your unsaved edits will be replaced with the questions currently on disk."
        confirmLabel="Discard"
        destructive
        onConfirm={() => {
          setConfirmDiscard(false)
          load()
        }}
        onCancel={() => setConfirmDiscard(false)}
      />

      <ConfirmDialog
        open={!!deleting}
        title="Delete this question?"
        body={deriveTitle(deleting?.prompt ?? '', 'This question')}
        confirmLabel="Delete"
        destructive
        onConfirm={() => {
          if (pendingDelete) remove(pendingDelete)
          setPendingDelete(null)
        }}
        onCancel={() => setPendingDelete(null)}
      />
    </>
  )
}

/* ------------------------------------------------------------------- card */

function QuestionCard({
  draft,
  index,
  total,
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

  // Grow the box to fit its content so long prompts stay readable.
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
    <Card
      className={cx('animate-fade-up overflow-hidden', empty && 'border-ember-500/40')}
    >
      <div className="flex items-center gap-3 border-b border-navy-700 px-3.5 py-2.5">
        <span
          className={cx(
            'num flex h-6 w-6 shrink-0 items-center justify-center rounded-lg text-[0.6875rem] font-semibold',
            empty
              ? 'bg-ember-500/15 text-ember-400'
              : 'bg-gold-500/12 text-gold-400',
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
      </div>

      <textarea
        ref={textareaRef}
        value={draft.prompt}
        onChange={(event) => onChange(event.target.value)}
        placeholder={
          'Write the question exactly as the model should receive it.\n\nExample: Write a Swift function that solves the FizzBuzz problem.'
        }
        spellCheck={false}
        className="w-full resize-none border-0 bg-transparent px-4 py-3.5 font-mono text-[0.8125rem] leading-relaxed text-ink-200 placeholder:text-ink-500/70 focus:outline-none"
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
