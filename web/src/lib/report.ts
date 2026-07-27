/**
 * Parses the markdown reports the Python engine writes.
 *
 * The shape is fixed by `.core/templates/test-block.md`, so a report can be
 * read back into structured metrics for charting without the server having to
 * keep a parallel database of past runs.
 */

export interface ParsedTest {
  index: number
  title: string
  filename: string
  ok: boolean
  error: string | null
  tokensPerSecond: number | null
  totalTokens: number | null
  timeToFirstToken: number | null
  stopReason: string | null
  /** Mean plugin score for this question, when the report carries grades. */
  score: number | null
}

export interface ParsedReport {
  modelLabel: string
  tests: ParsedTest[]
  averageTokensPerSecond: number | null
  averageTimeToFirstToken: number | null
  totalTokens: number | null
  overallScore: number | null
  graders: string[]
}

function numberOrNull(raw: string | undefined): number | null {
  if (!raw) return null
  const value = Number.parseFloat(raw.replace(/[^\d.-]/g, ''))
  return Number.isFinite(value) ? value : null
}

function metric(block: string, label: string): string | undefined {
  const match = block.match(new RegExp(`\\*\\*${label}:\\*\\*\\s*(.+)`))
  return match?.[1]?.trim()
}

/**
 * Read grades back out of the analysis block that grader plugins write.
 *
 * Rows look like: `| 3 | Question title | 80% (4/5 checks) | My Grader | notes |`
 * A question graded by several plugins gets one row each, so scores are
 * averaged per question — matching how the run computed them live.
 */
function parseGrades(markdown: string): {
  scores: Map<number, number>
  overall: number | null
  graders: string[]
} {
  const block = markdown.match(/<!--ANALYSIS_START-->([\s\S]*?)<!--ANALYSIS_END-->/)?.[1]
  const scores = new Map<number, number>()
  const graders = new Set<string>()

  if (!block) return { scores, overall: null, graders: [] }

  const overallMatch = block.match(/\*\*Overall score:\s*(\d+(?:\.\d+)?)%/)
  const overall = overallMatch ? Number.parseFloat(overallMatch[1]) / 100 : null

  const collected = new Map<number, number[]>()
  const row = /^\|\s*(\d+)\s*\|[^|]*\|\s*(\d+(?:\.\d+)?)%[^|]*\|([^|]*)\|/gm
  let match: RegExpExecArray | null
  while ((match = row.exec(block)) !== null) {
    const index = Number.parseInt(match[1], 10)
    const value = Number.parseFloat(match[2]) / 100
    if (!Number.isFinite(index) || !Number.isFinite(value)) continue
    collected.set(index, [...(collected.get(index) ?? []), value])
    const grader = match[3]?.trim()
    if (grader && grader !== '—') graders.add(grader)
  }

  for (const [index, values] of collected) {
    scores.set(index, values.reduce((a, b) => a + b, 0) / values.length)
  }

  return { scores, overall, graders: [...graders] }
}

export function parseReport(markdown: string): ParsedReport {
  const modelLabel =
    markdown.match(/^#\s*Automated Diagnostic Report:\s*(.+)$/m)?.[1]?.trim() ?? 'Unknown model'

  const summary = markdown.match(/<!--SUMMARY_START-->([\s\S]*?)<!--SUMMARY_END-->/)?.[1] ?? ''

  const { scores, overall, graders } = parseGrades(markdown)

  const tests: ParsedTest[] = []
  // Split on the test headings the template emits; the first chunk is the preamble.
  const chunks = markdown.split(/^##\s+Test\s+(\d+):\s*(.*)$/m)

  for (let i = 1; i < chunks.length; i += 3) {
    const index = Number.parseInt(chunks[i], 10)
    const title = (chunks[i + 1] ?? '').trim()
    const body = chunks[i + 2] ?? ''

    const errorMatch = body.match(/\*\*ERROR:\*\*\s*(.+)/)
    const stopReason = metric(body, 'Stop Reason') ?? null

    tests.push({
      index,
      title: title || `Test ${index}`,
      filename: body.match(/\*Source:\*\s*`([^`]+)`/)?.[1] ?? '',
      ok: !errorMatch,
      error: errorMatch?.[1]?.trim() ?? null,
      tokensPerSecond: numberOrNull(metric(body, 'Tokens/s')),
      totalTokens: numberOrNull(metric(body, 'Total Tokens')),
      timeToFirstToken: numberOrNull(metric(body, 'Time to First Token')),
      stopReason: stopReason === 'N/A' ? null : stopReason,
      score: scores.get(index) ?? null,
    })
  }

  return {
    modelLabel,
    tests,
    averageTokensPerSecond: numberOrNull(metric(summary, 'Average Tokens/s')),
    averageTimeToFirstToken: numberOrNull(metric(summary, 'Average Time to First Token')),
    totalTokens: numberOrNull(metric(summary, 'Total Tokens Generated')),
    overallScore: overall,
    graders,
  }
}
