/**
 * A plugin-assigned score.
 *
 * Scores come from user-written graders, so they carry a deliberately neutral
 * visual weight — mint/gold/rose signal the band, never "this answer is right".
 */

import { cx } from '../lib/format'

export function scoreTone(score: number): 'mint' | 'gold' | 'rose' {
  if (score >= 0.8) return 'mint'
  if (score >= 0.5) return 'gold'
  return 'rose'
}

export function letterGrade(score: number): string {
  if (score >= 0.97) return 'A+'
  if (score >= 0.93) return 'A'
  if (score >= 0.9) return 'A-'
  if (score >= 0.87) return 'B+'
  if (score >= 0.83) return 'B'
  if (score >= 0.8) return 'B-'
  if (score >= 0.77) return 'C+'
  if (score >= 0.73) return 'C'
  if (score >= 0.7) return 'C-'
  if (score >= 0.67) return 'D+'
  if (score >= 0.6) return 'D'
  return 'F'
}

export function ScoreBadge({
  score,
  title,
  showLetter,
}: {
  score: number
  title?: string
  showLetter?: boolean
}) {
  const tone = scoreTone(score)
  const toneClass = {
    mint: 'chip-mint',
    gold: 'chip-gold',
    rose: 'chip-rose',
  }[tone]

  return (
    <span className={cx('chip num', toneClass)} title={title}>
      {Math.round(score * 100)}%{showLetter && ` · ${letterGrade(score)}`}
    </span>
  )
}
