import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import { COLORS } from './common/types'
import { createMarkdownComponents } from './MarkdownRenderers'

type TreatyContentProps = {
  country: string
  articleData: any
  isMobile: boolean
  onNavigate: (act: string, section: string, anchor?: string) => void
  onNavigateRuling: (citation: string) => void
}

export default function TreatyContent({
  country,
  articleData,
  isMobile,
  onNavigate,
  onNavigateRuling,
}: TreatyContentProps) {
  const articleId = articleData?.article ?? ''
  const articleTitle = articleData?.title || ''
  const body = (articleData?.content || '').replace(/^---\n[\s\S]*?\n---\n?/, '').replace(/^#\s+[^\n]+\n?/, '')
  const components = createMarkdownComponents(isMobile, country, onNavigate, onNavigateRuling)

  return (
    <div>
      <div style={{
        marginBottom: 20, color: COLORS.textMuted, fontSize: 12,
        fontFamily: "'Montserrat', sans-serif", letterSpacing: 0.3,
        textTransform: 'uppercase' as const,
      }}>
        {country} &rsaquo; Article {articleId}
      </div>

      {articleTitle && (
        <h1 style={{
          color: COLORS.heading, fontSize: isMobile ? 20 : 22,
          fontWeight: 600, marginTop: 0, marginBottom: 20,
          fontFamily: "'Montserrat', sans-serif",
        }}>
          {articleTitle}
        </h1>
      )}

      <div style={{ lineHeight: 1.7, fontSize: isMobile ? 15 : 15, color: COLORS.text }}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]} components={components}>
          {body}
        </ReactMarkdown>
      </div>
    </div>
  )
}
