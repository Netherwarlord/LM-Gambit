/**
 * A ~40 line History API router.
 *
 * The app has five top-level views and no data loaders, so a routing library
 * would be pure overhead. This gives real URLs, working back/forward buttons
 * and deep links (e.g. /reports/automated_report_Qwen.md) with no dependency.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

interface RouterValue {
  path: string
  navigate: (to: string, options?: { replace?: boolean }) => void
}

const RouterContext = createContext<RouterValue>({ path: '/', navigate: () => {} })

export function RouterProvider({ children }: { children: ReactNode }) {
  const [path, setPath] = useState(() => window.location.pathname || '/')

  useEffect(() => {
    const onPop = () => setPath(window.location.pathname || '/')
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const navigate = useCallback((to: string, options?: { replace?: boolean }) => {
    if (to === window.location.pathname) return
    window.history[options?.replace ? 'replaceState' : 'pushState']({}, '', to)
    setPath(to)
    window.scrollTo({ top: 0 })
  }, [])

  const value = useMemo(() => ({ path, navigate }), [path, navigate])
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>
}

export function useRouter() {
  return useContext(RouterContext)
}

export function Link({
  to,
  className,
  children,
  ...rest
}: { to: string; className?: string; children: ReactNode } & Omit<
  React.AnchorHTMLAttributes<HTMLAnchorElement>,
  'href'
>) {
  const { navigate } = useRouter()
  return (
    <a
      href={to}
      className={className}
      onClick={(event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return
        event.preventDefault()
        navigate(to)
      }}
      {...rest}
    >
      {children}
    </a>
  )
}
