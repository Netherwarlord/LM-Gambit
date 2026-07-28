import { Shell } from './components/Shell'
import { useRouter } from './lib/router'
import { useRunFeed } from './hooks/useRunFeed'
import { PluginUIProvider } from './hooks/usePluginUI'
import { RunPage } from './pages/RunPage'
import { SuitePage } from './pages/SuitePage'
import { ReportsPage } from './pages/ReportsPage'
import { PlaygroundPage } from './pages/PlaygroundPage'
import { SettingsPage } from './pages/SettingsPage'
import { DocsPage } from './pages/DocsPage'
import { PluginPage } from './pages/PluginPage'
import { NotFoundPage } from './pages/NotFoundPage'

function Routes() {
  const { path } = useRouter()
  const { run, isLive } = useRunFeed()

  let page
  if (path === '/') page = <RunPage />
  else if (path === '/suite') page = <SuitePage />
  else if (path.startsWith('/reports')) page = <ReportsPage />
  else if (path === '/playground') page = <PlaygroundPage />
  else if (path === '/settings') page = <SettingsPage />
  else if (path === '/docs') page = <DocsPage />
  // Everything under /x/ belongs to a plugin; PluginPage resolves which one.
  else if (path.startsWith('/x/')) page = <PluginPage />
  else page = <NotFoundPage />

  return <Shell activeRun={isLive ? run : null}>{page}</Shell>
}

export function App() {
  return (
    <PluginUIProvider>
      <Routes />
    </PluginUIProvider>
  )
}
