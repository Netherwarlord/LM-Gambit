import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import { cx } from '../lib/format'

/** Renders model output / reports. Raw HTML is never enabled. */
export const Markdown = memo(function Markdown({
  children,
  className,
}: {
  children: string
  className?: string
}) {
  return (
    <div className={cx('md', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
})
