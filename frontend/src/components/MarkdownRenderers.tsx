import React from 'react'
import { COLORS } from './common/types'

type NavigateFn = (act: string, section: string, anchor?: string) => void
type NavigateRulingFn = (citation: string) => void
export type RenderLinkFn = (href?: string, children?: React.ReactNode) => React.ReactNode | null

// Subparagraph hierarchy from the leading **(n)** marker in a paragraph:
//   **(1)** digits -> level 0 (flush)
//   **(a)** single lowercase letter -> level 1
//   **(i)** roman numeral -> level 2
//   **(A)** single uppercase letter -> level 3
const _ROMAN = /^(i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv|xvi|xvii|xviii|xix|xx)$/i

export function subparagraphLevel(children: React.ReactNode): number {
  const text = React.Children.toArray(children)
    .map((c) => (typeof c === 'string' ? c : (c as React.ReactElement).props?.children))
    .flat()
    .join('')
    .replace(/<[^>]*>/g, ' ') // drop raw anchor tags like <a id="s333-1"></a>
    .trim()
  const m = text.match(/^\(([^)]{1,6})\)/)
  if (!m) return 0
  const tok = m[1]
  if (/^\d+$/.test(tok)) return 0
  if (_ROMAN.test(tok)) return 2
  if (/^[a-z]$/.test(tok)) return 1
  if (/^[A-Z]$/.test(tok)) return 3
  return 0
}

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
    p: ({ children }: { children?: React.ReactNode }) => {
      const level = subparagraphLevel(children)
      const indent = level * (isMobile ? 16 : 20)
      return (
        <p style={{ marginBottom: 12, color: COLORS.text, marginLeft: indent }}>
          {children}
        </p>
      )
    },
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
