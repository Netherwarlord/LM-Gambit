/**
 * Read-only enforcement on the Testing Suites page.
 *
 * These are presentation guards only — the API returns 409 regardless, and
 * that is the real protection. What is asserted here is that the page does not
 * *offer* an action it cannot perform, since a Rename button that always fails
 * is worse than no button.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { SuitePage } from './SuitePage'
import { RunFeedProvider } from '../hooks/useRunFeed'
import type { SuiteDetail, SuiteSummary } from '../lib/api'

const SUMMARIES: SuiteSummary[] = [
  { slug: 'safety', name: 'Safety', description: 'Guardrails', order: 50, builtin: true, count: 2 },
  { slug: 'mine', name: 'My Suite', description: 'Mine', order: 100, builtin: false, count: 1 },
]

const DETAILS: Record<string, SuiteDetail> = {
  safety: {
    ...SUMMARIES[0],
    tests: [
      { filename: 'test1.txt', title: 'Built-in question one', prompt: 'Built-in question one', suite: 'safety', id: 'safety/test1.txt' },
      { filename: 'test2.txt', title: 'Built-in question two', prompt: 'Built-in question two', suite: 'safety', id: 'safety/test2.txt' },
    ],
  },
  mine: {
    ...SUMMARIES[1],
    tests: [
      { filename: 'test1.txt', title: 'My question', prompt: 'My question', suite: 'mine', id: 'mine/test1.txt' },
    ],
  },
}

// The page only needs these two calls to render; everything else is user-driven.
vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      suites: vi.fn(async () => SUMMARIES),
      suite: vi.fn(async (slug: string) => DETAILS[slug]),
      activeRun: vi.fn(async () => null),
      runs: vi.fn(async () => []),
    },
  }
})

const renderPage = () =>
  render(
    <RunFeedProvider>
      <SuitePage />
    </RunFeedProvider>,
  )

describe('SuitePage read-only guards', () => {
  beforeEach(() => vi.clearAllMocks())

  it('offers Duplicate but not Rename or Delete for a built-in suite', async () => {
    renderPage()
    // The first suite is selected automatically, and it is built-in.
    await waitFor(() => expect(screen.getByRole('button', { name: /duplicate/i })).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /^rename$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /delete suite/i })).not.toBeInTheDocument()
  })

  // The question text appears twice per card - once as the title, once as the
  // textarea value - so questions are counted by role rather than by text.
  const questionBoxes = () => screen.getAllByRole('textbox')
  const waitForQuestions = (count: number) =>
    waitFor(() => expect(questionBoxes()).toHaveLength(count))

  const selectCustomSuite = async () => {
    const { default: userEvent } = await import('@testing-library/user-event')
    await waitFor(() => expect(screen.getByRole('button', { name: /My Suite/ })).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: /My Suite/ }))
  }

  it('marks a built-in suite as read-only and locks its question boxes', async () => {
    renderPage()
    await waitForQuestions(2)
    expect(screen.getByText(/ships with the app/i)).toBeInTheDocument()
    for (const box of questionBoxes()) expect(box).toHaveAttribute('readonly')
  })

  it('offers no save control for a built-in suite', async () => {
    renderPage()
    await waitForQuestions(2)
    expect(screen.queryByRole('button', { name: /save questions/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /add question/i })).not.toBeInTheDocument()
  })

  it('offers Rename and Delete once a custom suite is selected', async () => {
    renderPage()
    await waitForQuestions(2)
    await selectCustomSuite()

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^rename$/i })).toBeInTheDocument(),
    )
    // "Delete suite", not the per-question icon buttons which announce as
    // plain "Delete".
    expect(screen.getByRole('button', { name: /delete suite/i })).toBeInTheDocument()
    expect(screen.queryByText(/ships with the app/i)).not.toBeInTheDocument()
  })

  it('leaves a custom suite\'s question boxes editable', async () => {
    renderPage()
    await waitForQuestions(2)
    await selectCustomSuite()

    await waitForQuestions(1)
    for (const box of questionBoxes()) expect(box).not.toHaveAttribute('readonly')
  })
})
