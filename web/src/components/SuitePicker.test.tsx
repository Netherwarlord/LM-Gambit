/**
 * The run selection model.
 *
 * This is the piece that decides what a run actually covers, and it was
 * browser-verified only. The shape it produces matters as much as the count:
 * a whole suite must serialise as `{suite}` with no filenames, so "all of
 * math-code" stays all of it even after that suite gains a question. Freezing
 * today's filenames into the request would silently narrow future runs.
 */

import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  SuitePicker,
  countSelected,
  selectionsFrom,
  type Picks,
} from './SuitePicker'
import type { SuiteSummary } from '../lib/api'

const SUITES: SuiteSummary[] = [
  { slug: 'language', name: 'Language', description: '', order: 10, builtin: true, count: 6 },
  { slug: 'math-code', name: 'Math & Code', description: '', order: 30, builtin: true, count: 6 },
  { slug: 'safety', name: 'Safety', description: '', order: 50, builtin: true, count: 4 },
  { slug: 'mine', name: 'Mine', description: '', order: 100, builtin: false, count: 2 },
]

describe('selectionsFrom', () => {
  it('sends a whole suite as {suite} with no filenames', () => {
    expect(selectionsFrom({ 'math-code': 'all' })).toEqual([{ suite: 'math-code' }])
  })

  it('sends explicit filenames for a partial suite', () => {
    expect(selectionsFrom({ 'math-code': ['test3.txt', 'test4.txt'] })).toEqual([
      { suite: 'math-code', filenames: ['test3.txt', 'test4.txt'] },
    ])
  })

  it('mixes whole and partial suites in one request', () => {
    expect(selectionsFrom({ safety: 'all', 'math-code': ['test4.txt'] })).toEqual([
      { suite: 'safety' },
      { suite: 'math-code', filenames: ['test4.txt'] },
    ])
  })

  it('omits suites selected down to nothing', () => {
    expect(selectionsFrom({ safety: 'all', 'math-code': [] })).toEqual([{ suite: 'safety' }])
  })

  it('produces nothing for an empty selection', () => {
    expect(selectionsFrom({})).toEqual([])
  })
})

describe('countSelected', () => {
  it('counts a whole suite by its real size, not by listed filenames', () => {
    // The point of 'all': the count tracks the suite, so adding a question
    // later is reflected without the selection being rebuilt.
    expect(countSelected({ 'math-code': 'all' }, SUITES)).toBe(6)
  })

  it('counts a partial suite by its chosen files', () => {
    expect(countSelected({ 'math-code': ['test1.txt', 'test2.txt'] }, SUITES)).toBe(2)
  })

  it('sums across suites', () => {
    expect(countSelected({ safety: 'all', 'math-code': ['test4.txt'] }, SUITES)).toBe(5)
  })

  it('is zero for no selection', () => {
    expect(countSelected({}, SUITES)).toBe(0)
  })

  it('ignores a pick for a suite that no longer exists', () => {
    expect(countSelected({ 'deleted-suite': 'all' }, SUITES)).toBe(0)
  })
})

describe('SuitePicker', () => {
  const renderPicker = (picks: Picks = {}) => {
    const onChange = vi.fn()
    render(<SuitePicker suites={SUITES} picks={picks} onChange={onChange} />)
    return { onChange }
  }

  it('lists every suite', () => {
    renderPicker()
    for (const suite of SUITES) expect(screen.getByText(suite.name)).toBeInTheDocument()
  })

  it('selecting a suite yields "all", not a filename list', async () => {
    const { onChange } = renderPicker()
    await userEvent.click(screen.getByLabelText('Select Safety'))
    expect(onChange).toHaveBeenCalledWith({ safety: 'all' })
  })

  it('deselecting removes the suite entirely rather than emptying it', async () => {
    const { onChange } = renderPicker({ safety: 'all' })
    await userEvent.click(screen.getByLabelText('Select Safety'))
    expect(onChange).toHaveBeenCalledWith({})
  })

  it('shows a partially-selected suite as indeterminate', () => {
    renderPicker({ 'math-code': ['test1.txt', 'test2.txt'] })
    const box = screen.getByLabelText('Select Math & Code') as HTMLInputElement
    // Neither checked nor unchecked: the visual state that tells you a suite
    // is only partly included.
    expect(box.indeterminate).toBe(true)
    expect(box.checked).toBe(true)
  })

  it('a fully-selected suite is checked, not indeterminate', () => {
    renderPicker({ safety: 'all' })
    const box = screen.getByLabelText('Select Safety') as HTMLInputElement
    expect(box.indeterminate).toBe(false)
    expect(box.checked).toBe(true)
  })

  it('an unselected suite is neither', () => {
    renderPicker()
    const box = screen.getByLabelText('Select Language') as HTMLInputElement
    expect(box.indeterminate).toBe(false)
    expect(box.checked).toBe(false)
  })

  it('only fetches a suite\'s questions when it is expanded', async () => {
    const fetched: string[] = []
    vi.spyOn(await import('../lib/api'), 'api', 'get').mockReturnValue({
      suite: async (slug: string) => {
        fetched.push(slug)
        return { slug, name: slug, description: '', order: 1, builtin: true, count: 1, tests: [] }
      },
    } as never)

    renderPicker()
    expect(fetched).toEqual([])
    await userEvent.click(screen.getByText('Safety'))
    await waitFor(() => expect(fetched).toEqual(['safety']))
    vi.restoreAllMocks()
  })

  it('does nothing when disabled', async () => {
    const onChange = vi.fn()
    render(<SuitePicker suites={SUITES} picks={{}} onChange={onChange} disabled />)
    await userEvent.click(screen.getByLabelText('Select Safety'))
    expect(onChange).not.toHaveBeenCalled()
  })
})
