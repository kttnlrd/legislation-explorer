import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import { createMarkdownComponents, RenderLinkFn } from './MarkdownRenderers'
import SmartLinkPanel from './SmartLinkPanel'

interface SectionContentProps {
  act: string
  sectionData: any
  isMobile: boolean
  isPinned?: boolean
  togglePin?: () => void
  renderLink?: RenderLinkFn
  onNavigate: (act: string, section: string, anchor?: string) => void
  onNavigateRuling: (citation: string) => void
  onNavigateCase: (citation: string) => void
}

const SectionContent: React.FC<SectionContentProps> = ({
  act,
  sectionData,
  isMobile,
  isPinned,
  togglePin,
  renderLink,
  onNavigate,
  onNavigateRuling,
  onNavigateCase,
}) => {
  const fm = sectionData?.frontmatter || {}
  const components = createMarkdownComponents(isMobile, act, onNavigate, onNavigateRuling, renderLink)

  const sectionId = fm.section || ''

  const sep = <span className="lk-reader-crumb__sep" aria-hidden="true">/</span>
  const crumbs = [
    fm.act,
    fm.part && `Part ${fm.part}`,
    fm.division && `Division ${fm.division}`,
    fm.subdivision && `Subdivision ${fm.subdivision}`,
  ].filter(Boolean) as string[]

  return (
    <div className={`lk-reader${isMobile ? ' lk-reader--mobile' : ''}`}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 16, maxWidth: 740 }}>
        <nav aria-label="Breadcrumb" className="lk-reader-crumb" style={{ margin: 0, flex: 1, minWidth: 0, paddingTop: 10 }}>
          {crumbs.map((c, i) => (
            <React.Fragment key={i}>
              {i > 0 && sep}
              <span>{c}</span>
            </React.Fragment>
          ))}
        </nav>
        <button
          type="button"
          onClick={togglePin}
          aria-pressed={!!isPinned}
          className={`lk-reader-btn${isPinned ? ' lk-reader-btn--primary' : ''}`}
          title={isPinned ? 'Unpin this section' : 'Pin this section'}
        >
          {isPinned ? 'Unpin' : 'Pin'}
        </button>
      </div>

      <div className="lk-reader-body">
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]} components={components}>
          {sectionData.body || sectionData.markdown}
        </ReactMarkdown>
      </div>

      {/* Smart Links — Related content */}
      <div className="lk-reader-divider">
        <SmartLinkPanel
          act={act}
          section={sectionId}
          onNavigate={onNavigate}
          onNavigateRuling={onNavigateRuling}
          onNavigateCase={onNavigateCase}
        />
      </div>
    </div>
  )
}

export default SectionContent
