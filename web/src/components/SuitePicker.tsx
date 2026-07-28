/**
 * Pick which suites — and which questions inside them — a run should cover.
 *
 * The selection model mirrors the API's `selections` shape rather than a flat
 * list of question IDs, which buys two things:
 *
 *  - A whole suite is expressed as `{suite}` with no filenames, so "run all of
 *    math-code" stays true even if that suite gains a question later.
 *  - Selecting a suite needs no knowledge of its contents, so questions are
 *    only fetched for the suites a user actually expands.
 */

import { useCallback, useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, Loader2, Lock } from 'lucide-react'
import { api, type RunSelection, type SuiteSummary, type TestPrompt } from '../lib/api'
import { cx } from '../lib/format'

/** `'all'` means the whole suite; an array means those filenames only. */
export type Picks = Record<string, 'all' | string[]>

export function selectionsFrom(picks: Picks): RunSelection[] {
  return Object.entries(picks)
    .filter(([, value]) => value === 'all' || value.length > 0)
    .map(([suite, value]) =>
      value === 'all' ? { suite } : { suite, filenames: value },
    )
}

export function countSelected(picks: Picks, suites: SuiteSummary[]): number {
  return suites.reduce((total, suite) => {
    const pick = picks[suite.slug]
    if (pick === 'all') return total + suite.count
    return total + (pick?.length ?? 0)
  }, 0)
}

type PickState = 'none' | 'some' | 'all'

function stateOf(pick: Picks[string] | undefined, count: number): PickState {
  if (pick === 'all') return 'all'
  if (!pick || pick.length === 0) return 'none'
  return pick.length >= count ? 'all' : 'some'
}

export function SuitePicker({
  suites,
  picks,
  onChange,
  disabled,
}: {
  suites: SuiteSummary[]
  picks: Picks
  onChange: (next: Picks) => void
  disabled?: boolean
}) {
  const [expanded, setExpanded] = useState<string | null>(null)
  const [questions, setQuestions] = useState<Record<string, TestPrompt[]>>({})
  const [loading, setLoading] = useState<string | null>(null)

  // Only fetch a suite's questions when it is actually opened.
  const expand = useCallback(
    (slug: string) => {
      if (expanded === slug) {
        setExpanded(null)
        return
      }
      setExpanded(slug)
      if (questions[slug]) return
      setLoading(slug)
      api
        .suite(slug)
        .then((detail) => setQuestions((map) => ({ ...map, [slug]: detail.tests })))
        .catch(() => setQuestions((map) => ({ ...map, [slug]: [] })))
        .finally(() => setLoading(null))
    },
    [expanded, questions],
  )

  const toggleSuite = (suite: SuiteSummary) => {
    const next = { ...picks }
    if (stateOf(picks[suite.slug], suite.count) === 'none') next[suite.slug] = 'all'
    else delete next[suite.slug]
    onChange(next)
  }

  const toggleQuestion = (suite: SuiteSummary, filename: string) => {
    const loaded = questions[suite.slug] ?? []
    const currentPick = picks[suite.slug]
    // Narrowing an "all" suite needs its concrete filenames first.
    const current =
      currentPick === 'all' ? loaded.map((q) => q.filename) : [...(currentPick ?? [])]

    const at = current.indexOf(filename)
    if (at >= 0) current.splice(at, 1)
    else current.push(filename)

    const next = { ...picks }
    if (current.length === 0) delete next[suite.slug]
    else if (loaded.length > 0 && current.length >= loaded.length) next[suite.slug] = 'all'
    else next[suite.slug] = current
    onChange(next)
  }

  return (
    <ul className="space-y-1.5">
      {suites.map((suite) => {
        const state = stateOf(picks[suite.slug], suite.count)
        const open = expanded === suite.slug
        const rows = questions[suite.slug] ?? []
        const pick = picks[suite.slug]

        return (
          <li
            key={suite.slug}
            className={cx(
              'overflow-hidden rounded-lg border transition-colors',
              state === 'none'
                ? 'border-navy-700 bg-navy-900/30'
                : 'border-gold-500/35 bg-gold-500/8',
            )}
          >
            <div className="flex items-center gap-2 px-2.5 py-2">
              <input
                type="checkbox"
                className="h-3.5 w-3.5 shrink-0 accent-[#e3ad46]"
                checked={state !== 'none'}
                ref={(node) => {
                  // Partial selection is neither checked nor unchecked.
                  if (node) node.indeterminate = state === 'some'
                }}
                disabled={disabled}
                onChange={() => toggleSuite(suite)}
                aria-label={`Select ${suite.name}`}
              />

              <button
                className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
                onClick={() => expand(suite.slug)}
                disabled={disabled}
              >
                {open ? (
                  <ChevronDown size={12} className="shrink-0 text-ink-500" />
                ) : (
                  <ChevronRight size={12} className="shrink-0 text-ink-500" />
                )}
                {suite.builtin && <Lock size={10} className="shrink-0 text-ink-600" />}
                <span className="truncate text-[0.75rem] text-ink-200">{suite.name}</span>
              </button>

              <span className="num shrink-0 text-[0.6875rem] text-ink-500">
                {state === 'all'
                  ? suite.count
                  : state === 'some'
                    ? `${(pick as string[]).length}/${suite.count}`
                    : suite.count}
              </span>
            </div>

            {open && (
              <div className="border-t border-navy-700/70 bg-navy-950/30 px-2.5 py-2">
                {loading === suite.slug ? (
                  <p className="flex items-center gap-2 py-1 text-[0.75rem] text-ink-500">
                    <Loader2 size={12} className="animate-spin" /> Loading questions…
                  </p>
                ) : rows.length === 0 ? (
                  <p className="py-1 text-[0.75rem] text-ink-500">This suite has no questions.</p>
                ) : (
                  <ul className="space-y-0.5">
                    {rows.map((question, index) => {
                      const checked =
                        pick === 'all' || (pick ?? []).includes(question.filename)
                      return (
                        <li key={question.id}>
                          <label
                            className={cx(
                              'flex cursor-pointer items-start gap-2 rounded px-1.5 py-1 transition-colors hover:bg-navy-800/60',
                              disabled && 'cursor-not-allowed opacity-60',
                            )}
                          >
                            <input
                              type="checkbox"
                              className="mt-0.5 h-3 w-3 shrink-0 accent-[#e3ad46]"
                              checked={checked}
                              disabled={disabled}
                              onChange={() => toggleQuestion(suite, question.filename)}
                            />
                            <span className="min-w-0">
                              <span className="num mr-1.5 text-[0.625rem] text-ink-600">
                                {String(index + 1).padStart(2, '0')}
                              </span>
                              <span className="text-[0.6875rem] leading-snug text-ink-300">
                                {question.title}
                              </span>
                            </span>
                          </label>
                        </li>
                      )
                    })}
                  </ul>
                )}
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}

/** Default selection: every built-in suite, matching the CLI's bare run. */
export function useDefaultPicks(suites: SuiteSummary[]) {
  const [picks, setPicks] = useState<Picks>({})
  const [seeded, setSeeded] = useState(false)

  useEffect(() => {
    if (seeded || !suites.length) return
    const next: Picks = {}
    for (const suite of suites) if (suite.builtin) next[suite.slug] = 'all'
    setPicks(next)
    setSeeded(true)
  }, [suites, seeded])

  return [picks, setPicks] as const
}
