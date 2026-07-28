/**
 * The plugin UI manifest, fetched once and shared.
 *
 * Nav entries, pages and slot panels all come from here, so a single fetch at
 * startup is enough for plugins to appear everywhere they contribute. The
 * manifest is intentionally forgiving: if it cannot be loaded the app renders
 * exactly as it did before plugins existed rather than showing an error.
 */

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, type PluginSlotPanel, type PluginUIManifest } from '../lib/api'

const EMPTY: PluginUIManifest = { nav: [], pages: [], slots: {} }

interface PluginUIValue extends PluginUIManifest {
  reload: () => void
}

const PluginUIContext = createContext<PluginUIValue>({ ...EMPTY, reload: () => {} })

export function PluginUIProvider({ children }: { children: ReactNode }) {
  const [manifest, setManifest] = useState<PluginUIManifest>(EMPTY)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let cancelled = false
    api
      .pluginUI()
      .then((next) => {
        if (!cancelled) setManifest(next ?? EMPTY)
      })
      .catch(() => {
        // A plugin manifest is additive. Failing to load one must never take
        // the rest of the app down with it.
        if (!cancelled) setManifest(EMPTY)
      })
    return () => {
      cancelled = true
    }
  }, [nonce])

  const value = useMemo(
    () => ({ ...manifest, reload: () => setNonce((n) => n + 1) }),
    [manifest],
  )
  return <PluginUIContext.Provider value={value}>{children}</PluginUIContext.Provider>
}

export function usePluginUI() {
  return useContext(PluginUIContext)
}

/** Panels contributed to one injection point, already ordered. */
export function usePluginSlot(slot: string): PluginSlotPanel[] {
  const { slots } = usePluginUI()
  return slots?.[slot] ?? []
}
