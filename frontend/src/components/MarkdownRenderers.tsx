import React from 'react'
import { COLORS } from './common/types'

type NavigateFn = (act: string, section: string, anchor?: string) => void
type NavigateRulingFn = (citation: string) => void
type RenderLinkFn = (href?: string, children?: React.ReactNode) => React.ReactNode | null

export function createMarkdownComponents(
  isMobile: boolean,
  act: string,
  onNavigate: NavigateFn,
  onNavigateRuling: NavigateRulingFn,
  renderLink?: RenderLinkFn,
) {
  const headingStyle = {
    color: COLORS.heading,
    fontWeight: 600,
  } as const

  return {
    h1: ({ children }: { children?: React.ReactNode }) => (
      <h1 style={{ ...headingStyle, fontSize: isMobile ? 20 : 22, marginBottom: 16, borderBottom: `1px solid ${COLORS.border}`, paddingBottom: 8 }}>
        {children}
      </h1>
    ),
    h2: ({ children }: { children?: React.ReactNode }) => (
      <h2 style={{ ...headingStyle, fontSize: isMobile ? 17 : 18, marginTop: 24, marginBottom: 12 }}>
        {children}
      </h2>
    ),
    h3: ({ children }: { children?: React.ReactNode }) => (
      <h3 style={{ ...headingStyle, fontSize: isMobile ? 15 : 16, marginTop: 20, marginBottom: 10 }}>
        {children}
      </h3>
    ),
    p: ({ children }: { children?: React.ReactNode }) => (
      <p style={{ marginBottom: 12, color: COLORS.text }}>{children}</p>
    ),
    a: ({ children, href }: { children?: React.ReactNode; href?: string }) => {
      if (renderLink) {
        const popover = renderLink(href, children)
        if (popover) return popover
      }
      const handleClick = (e: React.MouseEvent<HTMLAnchorElement>) => {
        if (!href) return
        const sectionMatch = href.match(/\/(itaa-\d{4})\/s([^#]+)(?:#(.+))?/)
        const rulingMatch = href.match(/\/rulings\/(.+)/)
        if (sectionMatch) {
          const targetAct = sectionMatch[1]
          const targetSection = sectionMatch[2]
          const anchor = sectionMatch[3]
          if (targetAct === act) {
            e.preventDefault()
            onNavigate(targetAct, targetSection, anchor)
          }
        } else if (rulingMatch) {
          const targetRuling = decodeURIComponent(rulingMatch[1])
          e.preventDefault()
          onNavigateRuling(targetRuling)
        }
      }
      return <a href={href} onClick={handleClick} style={{ color: COLORS.accent, textDecoration: 'none' }}>{children}</a>
    },
    blockquote: ({ children }: { children?: React.ReactNode }) => (
      <blockquote style={{ marginLeft: 16, paddingLeft: 12, borderLeft: `3px solid ${COLORS.border}`, color: COLORS.textMuted }}>
        {children}
      </blockquote>
    ),
    ul: ({ children }: { children?: React.ReactNode }) => <ul style={{ marginLeft: 20, marginBottom: 12 }}>{children}</ul>,
    ol: ({ children }: { children?: React.ReactNode }) => <ol style={{ marginLeft: 20, marginBottom: 12 }}>{children}</ol>,
    li: ({ children }: { children?: React.ReactNode }) => <li style={{ marginBottom: 4 }}>{children}</li>,
    table: ({ children }: { children?: React.ReactNode }) => (
      <table style={{ borderCollapse: 'collapse', width: '100%', marginBottom: 16, border: `1px solid ${COLORS.border}`, fontSize: 'inherit' }}>
        {children}
      </table>
    ),
    thead: ({ children }: { children?: React.ReactNode }) => <thead style={{ background: COLORS.surfaceHover }}>{children}</thead>,
    tbody: ({ children }: { children?: React.ReactNode }) => <tbody>{children}</tbody>,
    tr: ({ children }: { children?: React.ReactNode }) => <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>{children}</tr>,
    th: ({ children }: { children?: React.ReactNode }) => (
      <th style={{ border: `1px solid ${COLORS.border}`, padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: COLORS.heading }}>
        {children}
      </th>
    ),
    td: ({ children }: { children?: React.ReactNode }) => (
      <td style={{ border: `1px solid ${COLORS.border}`, padding: '8px 12px', color: COLORS.text }}>
        {children}
      </td>
    ),
  }
}
