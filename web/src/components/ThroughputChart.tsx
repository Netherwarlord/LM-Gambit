/**
 * Per-question throughput, as a horizontal bar chart.
 *
 * One measure, one series: magnitude is carried by bar length in a single hue
 * (#b8892f — validated in-band and above 3:1 against the navy chart surface),
 * so there is no legend to restate the title. Questions that errored have no
 * throughput; they are listed under the plot with an icon and the word "Error"
 * rather than being coloured into the series.
 */

import { useId, useState } from 'react'
import { TriangleAlert } from 'lucide-react'
import type { ParsedTest } from '../lib/report'

const BAR_COLOR = '#b8892f'
const BAR_HEIGHT = 18 // ≤ 24px mark
const ROW_GAP = 10 // ≥ 2px surface gap between adjacent bars
const LEFT = 34
const RIGHT = 56
const TOP = 22
const BOTTOM = 26

type Measure = 'tokensPerSecond' | 'timeToFirstToken'

const MEASURES: Record<Measure, { label: string; unit: string; decimals: number }> = {
  tokensPerSecond: { label: 'Throughput', unit: 'tok/s', decimals: 1 },
  timeToFirstToken: { label: 'Time to first token', unit: 's', decimals: 2 },
}

/** Round up to a clean axis maximum without leaving the plot mostly empty. */
function niceMax(value: number): number {
  if (value <= 0) return 1
  const magnitude = 10 ** Math.floor(Math.log10(value))
  const normalized = value / magnitude
  const step = [1, 1.2, 1.6, 2, 2.5, 3, 4, 5, 6, 8, 10].find((s) => normalized <= s) ?? 10
  return step * magnitude
}

export function ThroughputChart({ tests }: { tests: ParsedTest[] }) {
  const clipId = useId()
  const [measure, setMeasure] = useState<Measure>('tokensPerSecond')
  const [hovered, setHovered] = useState<number | null>(null)

  const scored = tests.filter((test) => test.ok && test[measure] != null)
  const errored = tests.filter((test) => !test.ok)

  if (scored.length === 0) {
    return (
      <p className="px-4 py-6 text-[0.8125rem] text-ink-500">
        No successful questions in this report, so there is nothing to plot.
      </p>
    )
  }

  const config = MEASURES[measure]
  const max = niceMax(Math.max(...scored.map((test) => test[measure] as number)))
  const rowHeight = BAR_HEIGHT + ROW_GAP
  const plotWidth = 660
  const height = TOP + scored.length * rowHeight + BOTTOM
  const barArea = plotWidth - LEFT - RIGHT
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((fraction) => fraction * max)

  return (
    <div className="px-4 pt-2 pb-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[0.8125rem] font-medium text-ink-300">
          {config.label} by question{' '}
          <span className="text-ink-500">({config.unit})</span>
        </h3>
        <div className="flex gap-1">
          {(Object.keys(MEASURES) as Measure[]).map((key) => (
            <button
              key={key}
              className={
                measure === key
                  ? 'btn btn-sm border-gold-500/40 bg-gold-500/15 text-gold-300'
                  : 'btn btn-ghost btn-sm'
              }
              onClick={() => setMeasure(key)}
            >
              {MEASURES[key].label}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${plotWidth} ${height}`}
          width="100%"
          style={{ minWidth: 420 }}
          role="img"
          aria-label={`${config.label} per question in ${config.unit}`}
        >
          <defs>
            {/* Square at the baseline, 4px rounded at the data end. */}
            <clipPath id={clipId}>
              <rect x={0} y={0} width={plotWidth} height={height} />
            </clipPath>
          </defs>

          {/* recessive hairline gridlines */}
          {ticks.map((tick) => {
            const x = LEFT + (tick / max) * barArea
            return (
              <g key={tick}>
                <line
                  x1={x}
                  y1={TOP - 6}
                  x2={x}
                  y2={height - BOTTOM + 4}
                  stroke="#223353"
                  strokeWidth={1}
                />
                <text
                  x={x}
                  y={height - BOTTOM + 17}
                  textAnchor="middle"
                  fill="#55688a"
                  fontSize={9.5}
                  style={{ fontVariantNumeric: 'tabular-nums' }}
                >
                  {tick.toFixed(config.decimals === 2 && max < 5 ? 1 : 0)}
                </text>
              </g>
            )
          })}

          {scored.map((test, row) => {
            const value = test[measure] as number
            const y = TOP + row * rowHeight
            const width = Math.max((value / max) * barArea, 2)
            const active = hovered === test.index

            return (
              <g
                key={test.index}
                onMouseEnter={() => setHovered(test.index)}
                onMouseLeave={() => setHovered(null)}
              >
                {/* hit target larger than the mark */}
                <rect
                  x={0}
                  y={y - ROW_GAP / 2}
                  width={plotWidth}
                  height={rowHeight}
                  fill={active ? '#ffffff' : 'transparent'}
                  fillOpacity={active ? 0.035 : 0}
                />
                <text
                  x={LEFT - 8}
                  y={y + BAR_HEIGHT / 2 + 3.5}
                  textAnchor="end"
                  fill="#7288ab"
                  fontSize={10}
                  style={{ fontVariantNumeric: 'tabular-nums' }}
                >
                  {String(test.index).padStart(2, '0')}
                </text>
                <rect
                  x={LEFT}
                  y={y}
                  width={width}
                  height={BAR_HEIGHT}
                  rx={4}
                  fill={BAR_COLOR}
                  fillOpacity={active ? 1 : 0.88}
                  clipPath={`url(#${clipId})`}
                />
                {/* square off the baseline end */}
                <rect x={LEFT} y={y} width={Math.min(4, width)} height={BAR_HEIGHT} fill={BAR_COLOR} fillOpacity={active ? 1 : 0.88} />
                <text
                  x={LEFT + width + 7}
                  y={y + BAR_HEIGHT / 2 + 3.5}
                  fill="#c8d5ea"
                  fontSize={10.5}
                  style={{ fontVariantNumeric: 'tabular-nums' }}
                >
                  {value.toFixed(config.decimals)}
                </text>
              </g>
            )
          })}

          {/* baseline */}
          <line x1={LEFT} y1={TOP - 6} x2={LEFT} y2={height - BOTTOM + 4} stroke="#2e4467" strokeWidth={1} />
        </svg>
      </div>

      {hovered != null && (
        <div className="mt-1 rounded-lg border border-navy-700 bg-navy-900/80 px-3 py-2 text-[0.75rem]">
          <span className="text-ink-200">
            {scored.find((test) => test.index === hovered)?.title}
          </span>
          <span className="num ml-2 text-gold-400">
            {(scored.find((test) => test.index === hovered)?.[measure] ?? 0).toFixed(
              config.decimals,
            )}{' '}
            {config.unit}
          </span>
        </div>
      )}

      {errored.length > 0 && (
        <div className="mt-3 border-t border-navy-700 pt-3">
          <p className="mb-1.5 text-[0.6875rem] font-semibold tracking-wide text-ink-500 uppercase">
            Not plotted — no measurement
          </p>
          <ul className="space-y-1">
            {errored.map((test) => (
              <li key={test.index} className="flex items-start gap-2 text-[0.75rem]">
                <TriangleAlert size={12} className="mt-0.5 shrink-0 text-rose-400" />
                <span className="text-ink-400">
                  <span className="num mr-1.5 text-ink-500">
                    {String(test.index).padStart(2, '0')}
                  </span>
                  {test.title}
                  <span className="ml-1.5 font-medium text-rose-400">Error</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
