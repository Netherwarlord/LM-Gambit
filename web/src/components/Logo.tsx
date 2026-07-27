/** LM-Gambit brand mark — a chess pawn cut from a warm gradient. */

import { useId } from 'react'

export function Logo({ size = 30 }: { size?: number }) {
  // The mark renders more than once per page (rail + mobile bar), so the
  // gradient needs a unique id or the second instance resolves to the first.
  const gradientId = useId()

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={gradientId} x1="4" y1="2" x2="36" y2="38" gradientUnits="userSpaceOnUse">
          <stop stopColor="#F4813F" />
          <stop offset="1" stopColor="#E3AD46" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="38" height="38" rx="11" fill={`url(#${gradientId})`} />
      <rect
        x="1"
        y="1"
        width="38"
        height="38"
        rx="11"
        stroke="#FFD9AE"
        strokeOpacity="0.35"
        strokeWidth="1.2"
      />
      {/* pawn silhouette */}
      <path
        d="M20 9.4a4 4 0 0 1 2.35 7.24c1.5.93 2.4 2.42 2.4 4.06 0 1.5-.74 2.86-1.96 3.79l1.9 6.7h-9.38l1.9-6.7a4.78 4.78 0 0 1-1.96-3.79c0-1.64.9-3.13 2.4-4.06A4 4 0 0 1 20 9.4Z"
        fill="#160B04"
        fillOpacity="0.82"
      />
      <rect x="12.4" y="29.4" width="15.2" height="3.4" rx="1.7" fill="#160B04" fillOpacity="0.82" />
    </svg>
  )
}
