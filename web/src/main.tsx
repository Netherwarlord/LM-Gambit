import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import { App } from './App'
import { RouterProvider } from './lib/router'
import { ToastProvider } from './components/ui'
import { RunFeedProvider } from './hooks/useRunFeed'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider>
      <ToastProvider>
        <RunFeedProvider>
          <App />
        </RunFeedProvider>
      </ToastProvider>
    </RouterProvider>
  </StrictMode>,
)
