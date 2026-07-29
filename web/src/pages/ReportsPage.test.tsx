/**
 * Report grouping.
 *
 * Reports used to be one file per model, silently overwritten. Now a model has
 * a history, and the list must present it as one thread — with the newest run
 * first, since that ordering is what makes a regression visible.
 */

import { describe, expect, it } from 'vitest'
import { groupByModel } from './ReportsPage'
import type { ReportSummary } from '../lib/api'

const report = (
  model: string,
  modified: number,
  scope = 'all',
  count: number | null = 26,
): ReportSummary => ({
  name: `${model}__${modified}__${scope}__${count}q.md`,
  model_label: model,
  size_bytes: 1000,
  modified_at: modified,
  suite_scope: scope,
  question_count: count,
})

describe('groupByModel', () => {
  it('buckets runs of the same model together', () => {
    const grouped = groupByModel([
      report('gemma', 300, 'safety', 4),
      report('deepseek', 200),
      report('gemma', 100, 'math-code', 6),
    ])
    expect(grouped.map(([model, runs]) => [model, runs.length])).toEqual([
      ['gemma', 2],
      ['deepseek', 1],
    ])
  })

  it('preserves the incoming order, which the API sorts newest-first', () => {
    const [, gemmaRuns] = groupByModel([
      report('gemma', 300, 'safety', 4),
      report('gemma', 100, 'math-code', 6),
    ])[0]
    expect(gemmaRuns.map((r) => r.modified_at)).toEqual([300, 100])
  })

  it('orders models by their most recent run', () => {
    const grouped = groupByModel([
      report('newest', 500),
      report('older', 400),
      report('older', 100),
    ])
    expect(grouped.map(([model]) => model)).toEqual(['newest', 'older'])
  })

  it('keeps runs of one model distinct rather than collapsing them', () => {
    // The bug this whole scheme exists to prevent: a one-question smoke test
    // and a 26-question benchmark are different runs, not one file.
    const [, runs] = groupByModel([
      report('gemma', 300, 'context-knowledge', 1),
      report('gemma', 200, 'all', 26),
    ])[0]
    expect(runs.map((r) => r.question_count)).toEqual([1, 26])
    expect(new Set(runs.map((r) => r.name)).size).toBe(2)
  })

  it('handles an empty list', () => {
    expect(groupByModel([])).toEqual([])
  })

  it('carries legacy reports through with no scope', () => {
    const [[, runs]] = groupByModel([report('old', 100, 'legacy', 4)])
    expect(runs[0].suite_scope).toBe('legacy')
  })
})
