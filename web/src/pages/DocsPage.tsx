/**
 * Plugin framework documentation.
 *
 * The reference prose is static, but the "Installed" section reads the live
 * registry so the examples and the reality can never drift apart.
 */

import { useState } from 'react'
import { BookOpen, CircleAlert, Puzzle } from 'lucide-react'
import { Markdown } from '../components/Markdown'
import { pluginIcon } from '../components/PluginBlocks'
import { Card, CardHeader, PageHeader, useAsync } from '../components/ui'
import { usePluginUI } from '../hooks/usePluginUI'
import { api } from '../lib/api'
import { cx } from '../lib/format'

const SECTIONS = [
  { id: 'start', label: 'Getting started' },
  { id: 'hooks', label: 'Hooks' },
  { id: 'grading', label: 'Grading' },
  { id: 'ui', label: 'Contributing UI' },
  { id: 'http', label: 'HTTP routes' },
  { id: 'installed', label: 'Installed' },
] as const

const GETTING_STARTED = `
Drop a \`.py\` file into \`plugins/\` and it loads at startup. A directory with an
\`__init__.py\` works too, when one file is not enough.

\`\`\`bash
cp plugins/_skeleton.py plugins/my_plugin.py
\`\`\`

Files beginning with \`_\` are ignored, so the skeleton itself never runs.

Every hook is optional — a plugin defining only \`grade\` is perfectly valid.
Plugins import from \`plugin_api\` and nothing else in the project, so they keep
working across refactors of the engine or the server.

\`\`\`python
NAME = "My plugin"          # shown in Settings and in report tables
VERSION = "1.0.0"
DESCRIPTION = "One line."
ENABLED = True              # False keeps the file but stops loading it
\`\`\`

**Reloading.** Settings → Plugins has a refresh button that re-scans the
directory and picks up edits live. The one exception is \`register_routes\`:
HTTP routes are bound when the server starts, so adding or changing them needs
a restart.

**Failure isolation.** A plugin that raises is logged and skipped for that call
only. It stays loaded, its other hooks keep firing, and a broken plugin can
never fail a run or stop the server.
`

const HOOKS = `
| Hook | Called | Use it for |
| --- | --- | --- |
| \`grade(test)\` | after each answer | Score it, or \`None\` to abstain |
| \`on_run_start(run)\` | once, before the first question | Reset state, open a file |
| \`on_test_complete(test)\` | after each question | Log, stream, react to failures |
| \`on_run_complete(run)\` | when the run ends | Notify, export — fires on cancel and failure too |
| \`report_sections(run)\` | after the report is written | Return extra markdown to append |
| \`register_routes(router)\` | at server start | Endpoints under \`/api/plugins/<slug>\` |
| \`ui_contributions()\` | when the UI loads | Nav entries, pages and panels |
| \`register()\` | once, at load | Setup; raising here disables the plugin |

\`TestRecord\` gives you \`index\`, \`total\`, \`title\`, \`filename\`, \`suite\`,
\`prompt\`, \`ok\`, \`response\`, \`error\`, \`metrics\`, \`elapsed\`, plus
\`tokens_per_second\`, \`total_tokens\` and \`time_to_first_token\`.

> **\`filename\` is not unique.** Questions live in named suites and every suite
> has a \`test1.txt\`. Identify a question by \`question_id\` — the qualified
> \`"<suite>/<file>"\` — never by \`filename\` alone. A run routinely spans
> several suites, and graders derive their whole rubric from \`prompt\`, so
> mixing two questions up produces a confident, wrong score in silence.

\`RunRecord\` gives you \`tests\`, \`grades\`, \`summary\`, \`status\`, \`report_path\`,
\`score_for(index)\` and \`overall_score\`.
`

const GRADING = `
\`grade\` may return \`None\` to abstain, a float from 0.0 to 1.0, \`True\`/\`False\`,
or a \`Grade\` with a label and notes that reach the report.

\`\`\`python
from plugin_api import Grade

def grade(test):
    if "json" not in test.prompt.lower():
        return None                       # not my kind of question
    ok = test.response.strip().startswith("{")
    return Grade(
        score=1.0 if ok else 0.0,
        label="valid shape" if ok else "not an object",
        notes="Checked the answer is a bare JSON object.",
    )
\`\`\`

- **Abstaining is free.** \`None\` excludes the question from that grader
  entirely; it never counts as a zero. Prefer it over guessing.
- **A question's score is the mean** of every grader that scored it, and the
  run's score is the mean of those.
- **Failed questions are never graded** — there is no answer to judge. Use
  \`on_test_complete\` to see failures.
- **Two graders should not check the same thing.** The bundled pair are split
  deliberately: \`response_checks\` asks whether an answer contains code,
  \`code_lint\` asks whether that code is any good, and abstains when there is none.
`

const UI_DOCS = `
Plugins describe interface as **data**, and the app renders it. No plugin ships
JavaScript, and installing one never requires rebuilding the frontend.

\`\`\`python
from plugin_api import Action, NavItem, Page, Panel, StatRow, Table

def ui_contributions():
    base = "/api/plugins/my_plugin"
    return [
        NavItem(label="My tool", path="/tool", icon="wrench", order=50),
        Page(
            path="/tool",
            title="My tool",
            subtitle="What it does.",
            blocks=[
                StatRow(source=f"{base}/stats"),
                Panel(title="Results", blocks=[
                    Table(source=f"{base}/rows"),
                    Action(label="Clear", post=f"{base}/clear", style="ghost"),
                ]),
            ],
        ),
    ]
\`\`\`

### Blocks

| Block | Renders | Fields |
| --- | --- | --- |
| \`StatRow\` | a row of headline numbers | \`stats\` of \`Stat(label, value, hint, tone)\` |
| \`Table\` | a column-headed table | \`columns\`, \`rows\`, \`empty\` |
| \`Markdown\` | rendered markdown | \`text\` |
| \`Action\` | a button that POSTs | \`label\`, \`post\`, \`confirm\`, \`style\`, \`icon\` |
| \`Panel\` | a titled card wrapping blocks | \`title\`, \`subtitle\`, \`blocks\` |

\`tone\` is one of \`default\`, \`good\`, \`warn\`, \`bad\`. \`style\` is \`primary\`,
\`ghost\` or \`danger\`.

### Static or live

Every data block takes either inline values or a \`source\` URL. With a source,
the block fetches it and expects the same field names back as JSON — so the
same \`Table\` can be a fixed list or a live view without changing shape.

An \`Action\` may return \`{"message": "..."}\` to raise a toast and
\`{"refresh": true}\` to make sibling blocks re-fetch.

### Surfaces

| Surface | Effect |
| --- | --- |
| \`NavItem(label, path, icon, hint, order)\` | an entry in the left rail |
| \`Page(path, title, subtitle, blocks)\` | a full page |
| \`SlotPanel(slot, panel, order)\` | a panel injected into a built-in page |

Slots are \`run.aside\`, \`reports.aside\`, \`suite.aside\` and \`settings.section\`.

**Paths are namespaced.** Whatever you declare is served under \`/x/<slug>/\`, so
\`"/tool"\` in the plugin \`my_plugin\` becomes \`/x/my_plugin/tool\`. Two plugins
can use the same short path without colliding, and no plugin can ever shadow a
built-in route.

**Icons** are named: \`activity\`, \`alert\`, \`bar\`, \`bug\`, \`check\`, \`database\`,
\`file\`, \`gauge\`, \`hash\`, \`layers\`, \`list\`, \`play\`, \`puzzle\`, \`refresh\`,
\`search\`, \`settings\`, \`shield\`, \`sparkles\`, \`table\`, \`terminal\`, \`trash\`,
\`wrench\`, \`zap\`. An unknown name falls back to a puzzle piece.
`

const HTTP_DOCS = `
\`register_routes\` receives a FastAPI router already prefixed with
\`/api/plugins/<slug>\`. This is where \`source\` and \`post\` URLs point.

\`\`\`python
def register_routes(router):
    @router.get("/stats")
    async def stats() -> dict:
        return {"stats": [
            {"label": "Checked", "value": 12, "hint": "this run", "tone": "good"},
        ]}

    @router.post("/clear")
    async def clear() -> dict:
        return {"message": "Cleared.", "refresh": True}
\`\`\`

The frontend refuses any block URL that does not begin with \`/api/plugins/\`,
so a plugin cannot point the browser at an external host.

> **Routes bind at server start, and reloading does not rebind them.** The
> handlers you register close over the module object that existed at startup.
> After a plugin reload, the *new* module handles \`grade\` and the other hooks
> while your routes keep reading the *old* module's globals — so an endpoint
> can serve stale state with no error to hint at it. Restart the server after
> editing a plugin that defines \`register_routes\`.
`

function SectionCard({ id, title, body }: { id: string; title: string; body: string }) {
  return (
    <Card className="scroll-mt-6" >
      <div id={id}>
        <CardHeader title={title} icon={<BookOpen size={14} />} />
        <div className="px-4 py-3">
          <Markdown>{body}</Markdown>
        </div>
      </div>
    </Card>
  )
}

function Installed() {
  const plugins = useAsync(() => api.plugins(), [])
  const { nav, pages, slots } = usePluginUI()

  const contributionsFor = (slug: string) => {
    const bits: string[] = []
    const navCount = nav.filter((n) => n.slug === slug).length
    const pageCount = pages.filter((p) => p.slug === slug).length
    const slotCount = Object.values(slots ?? {}).flat().filter((s) => s.slug === slug).length
    if (navCount) bits.push(`${navCount} nav entry`)
    if (pageCount) bits.push(`${pageCount} page`)
    if (slotCount) bits.push(`${slotCount} panel`)
    return bits
  }

  return (
    <Card>
      <div id="installed">
        <CardHeader
          title="Installed plugins"
          icon={<Puzzle size={14} />}
          hint="Read live from the registry."
        />
        <div className="divide-y divide-navy-800/70">
          {(plugins.data ?? []).map((plugin) => {
            const Icon = pluginIcon(nav.find((n) => n.slug === plugin.slug)?.icon)
            const bits = contributionsFor(plugin.slug)
            return (
              <div key={plugin.slug} className="flex items-start gap-3 px-4 py-3">
                <Icon size={15} className="mt-0.5 shrink-0 text-gold-500" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="text-[0.8125rem] font-semibold text-ink-200">{plugin.name}</span>
                    <span className="num text-[0.6875rem] text-ink-500">v{plugin.version}</span>
                    <code className="text-[0.6875rem] text-ink-500">{plugin.slug}</code>
                  </div>
                  <p className="mt-0.5 text-[0.8125rem] text-ink-400">{plugin.description}</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {plugin.hooks.map((hook) => (
                      <span
                        key={hook}
                        className="rounded border border-navy-700 bg-navy-800/60 px-1.5 py-0.5 text-[0.625rem] text-ink-400"
                      >
                        {hook}
                      </span>
                    ))}
                    {bits.map((bit) => (
                      <span
                        key={bit}
                        className="rounded border border-gold-500/30 bg-gold-500/10 px-1.5 py-0.5 text-[0.625rem] text-gold-400"
                      >
                        {bit}
                      </span>
                    ))}
                  </div>
                  {plugin.error && (
                    <p className="mt-1.5 flex items-center gap-1.5 text-[0.75rem] text-rose-400">
                      <CircleAlert size={12} /> {plugin.error}
                    </p>
                  )}
                </div>
              </div>
            )
          })}
          {!plugins.data?.length && (
            <p className="px-4 py-6 text-center text-[0.8125rem] text-ink-500">
              Nothing in <code>plugins/</code> yet.
            </p>
          )}
        </div>
      </div>
    </Card>
  )
}

export function DocsPage() {
  const [active, setActive] = useState<string>('start')

  return (
    <>
      <PageHeader
        title="Plugin framework"
        subtitle="Everything a plugin can do: grade answers, extend reports, add HTTP routes, and contribute interface — without shipping a line of JavaScript."
      />

      <nav className="mb-5 flex flex-wrap gap-1.5">
        {SECTIONS.map((section) => (
          <a
            key={section.id}
            href={`#${section.id}`}
            onClick={() => setActive(section.id)}
            className={cx(
              'rounded-lg border px-2.5 py-1 text-[0.75rem] transition-colors',
              active === section.id
                ? 'border-gold-500/40 bg-gold-500/10 text-gold-400'
                : 'border-navy-700 text-ink-400 hover:text-ink-200',
            )}
          >
            {section.label}
          </a>
        ))}
      </nav>

      <div className="space-y-4">
        <SectionCard id="start" title="Getting started" body={GETTING_STARTED} />
        <SectionCard id="hooks" title="Hook reference" body={HOOKS} />
        <SectionCard id="grading" title="Grading" body={GRADING} />
        <SectionCard id="ui" title="Contributing UI" body={UI_DOCS} />
        <SectionCard id="http" title="HTTP routes" body={HTTP_DOCS} />
        <Installed />
      </div>
    </>
  )
}
