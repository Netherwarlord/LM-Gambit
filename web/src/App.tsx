import { Shell } from './components/Shell'
import { useRouter } from './lib/router'
import { useRunFeed } from './hooks/useRunFeed'
import { RunPage } from './pages/RunPage'
import { SuitePage } from './pages/SuitePage'
import { ReportsPage } from './pages/ReportsPage'
import { PlaygroundPage } from './pages/PlaygroundPage'
import { SettingsPage } from './pages/SettingsPage'
import { NotFoundPage } from './pages/NotFoundPage'

export function App() {
  const { path } = useRouter()
  const { run, isLive } = useRunFeed()

  let page
  if (path === '/') page = <RunPage />
  else if (path === '/suite') page = <SuitePage />
  else if (path.startsWith('/reports')) page = <ReportsPage />
  else if (path === '/playground') page = <PlaygroundPage />
  else if (path === '/settings') page = <SettingsPage />
  else page = <NotFoundPage />

  return <Shell activeRun={isLive ? run : null}>{page}</Shell>
}
