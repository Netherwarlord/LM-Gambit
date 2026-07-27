/** Small display helpers shared across views. */

export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '—'
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds % 60)
  if (minutes < 60) return `${minutes}m ${rest}s`
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function formatRelativeTime(epochSeconds: number): string {
  const delta = Date.now() / 1000 - epochSeconds
  if (delta < 60) return 'just now'
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`
  if (delta < 604800) return `${Math.floor(delta / 86400)}d ago`
  return new Date(epochSeconds * 1000).toLocaleDateString()
}

export function formatTimestamp(epochSeconds: number): string {
  return new Date(epochSeconds * 1000).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function clockTime(epochMs: number = Date.now()): string {
  return new Date(epochMs).toLocaleTimeString(undefined, { hour12: false })
}

/** Title shown for a question — the engine uses the first non-empty line. */
export function deriveTitle(prompt: string, fallback = 'Untitled question'): string {
  for (const line of prompt.split('\n')) {
    const trimmed = line.trim()
    if (trimmed) return trimmed
  }
  return fallback
}

export function cx(...values: (string | false | null | undefined)[]): string {
  return values.filter(Boolean).join(' ')
}
