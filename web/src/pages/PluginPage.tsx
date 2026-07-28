/** Renders a page declared by a plugin, matched on the current path. */

import { Puzzle } from 'lucide-react'
import { PluginBlocks } from '../components/PluginBlocks'
import { EmptyState, PageHeader } from '../components/ui'
import { usePluginUI } from '../hooks/usePluginUI'
import { useRouter } from '../lib/router'
import { Link } from '../lib/router'

export function PluginPage() {
  const { path } = useRouter()
  const { pages } = usePluginUI()

  const page = pages.find((candidate) => candidate.path === path)

  if (!page) {
    return (
      <EmptyState
        icon={<Puzzle size={18} />}
        title="No plugin owns this page"
        description={`Nothing is registered at ${path}. The plugin that provided it may have been disabled or removed — check Settings, or reload plugins.`}
        action={
          <Link to="/settings" className="btn btn-ghost btn-sm">
            Open Settings
          </Link>
        }
      />
    )
  }

  return (
    <>
      <PageHeader
        title={page.title}
        subtitle={page.subtitle || undefined}
        actions={
          <span className="rounded-lg border border-navy-700 bg-navy-800/60 px-2.5 py-1 text-[0.6875rem] text-ink-500">
            from {page.plugin}
          </span>
        }
      />
      <PluginBlocks blocks={page.blocks} />
    </>
  )
}
