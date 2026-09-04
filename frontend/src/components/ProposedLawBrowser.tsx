import React, { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '../api'
import { COLORS } from './common/types'

type SectionNode = { id: string; title: string; content: string }
type ActNode = { name: string; relation: string; sections: SectionNode[] }
type Item = { id: string; title: string; status?: string; measure_type?: string; summary?: string; announced_date?: string; source_url?: string; notes?: string; commentary?: string; acts?: ActNode[] }

const STATUS_COLORS: Record<string, string> = {
  announced: '#b8860b',
  exposure_draft: '#c0562b',
  before_parliament: '#2f6fb2',
  passed: '#1f7a3d',
  enacted: '#1f7a3d',
  withdrawn: '#777',
}
const TYPE_LABELS: Record<string, string> = { bill: 'Bill', exposure_draft: 'Exposure draft', announcement: 'Announcement', ato_draft: 'ATO draft', other: 'Other' }

/** Read-only Proposed Law viewer — content is managed via MCP (proposed_law_*). */
export default function ProposedLawBrowser({ isMobile }: { isMobile: boolean }) {
  const [items, setItems] = useState<Item[] | null>(null)
  const [sel, setSel] = useState<string | null>(null)
  const [open, setOpen] = useState<Record<string, boolean>>({})

  useEffect(() => { api.proposedLawList().then(d => setItems((d as any)?.items ?? [])) }, [])
  const item = items?.find(i => i.id === sel) ?? null

  return (
    <div style={{ padding: 16, maxWidth: 1100, margin: '0 auto' }}>
      <h2 style={{ color: COLORS.heading, margin: '0 0 12px' }}>Proposed Law</h2>
      <p style={{ color: COLORS.textMuted, margin: '0 0 16px', fontSize: 13 }}>
        Measures announced but not yet law — tracked via MCP (<code>proposed_law_add</code> / <code>proposed_law_update</code>).
        Only integrated into the corpus if enacted.
      </p>
      {!items ? <p style={{ color: COLORS.textMuted }}>Loading…</p> : items.length === 0 ? (
        <p style={{ color: COLORS.textMuted }}>Nothing tracked yet.</p>
      ) : (
        <div style={{ display: 'flex', gap: 16, flexDirection: isMobile ? 'column' : 'row', alignItems: 'flex-start' }}>
          {/* item list */}
          <div style={{ flex: '0 0 280px', width: isMobile ? '100%' : 280, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {items.map(i => (
              <button key={i.id} onClick={() => setSel(i.id)} style={{
                textAlign: 'left', padding: '10px 12px', borderRadius: 8, cursor: 'pointer', border: `1px solid ${sel === i.id ? COLORS.accent : COLORS.border}`,
                background: sel === i.id ? COLORS.surfaceHover : COLORS.surface, color: COLORS.text, fontSize: 14,
              }}>
                <div style={{ fontWeight: 600 }}>{i.title}</div>
                <div style={{ fontSize: 12, marginTop: 4 }}>
                  <span style={{ color: STATUS_COLORS[i.status ?? 'announced'] }}>● {i.status}</span>
                  <span style={{ color: COLORS.textMuted }}> · {TYPE_LABELS[i.measure_type ?? 'other'] ?? i.measure_type}</span>
                </div>
              </button>
            ))}
          </div>
          {/* detail */}
          {item && (
            <div style={{ flex: 1, minWidth: 0 }}>
              <h3 style={{ color: COLORS.heading, margin: '0 0 6px' }}>{item.title}</h3>
              {item.source_url && (
                <p style={{ margin: '0 0 6px', fontSize: 13 }}>
                  <a href={item.source_url} target="_blank" rel="noreferrer" style={{ color: COLORS.accent }}>Source ↗</a>
                  {item.announced_date ? <span style={{ color: COLORS.textMuted }}> · {item.announced_date}</span> : null}
                </p>
              )}
              {item.summary && <p style={{ color: COLORS.text, margin: '0 0 12px', fontSize: 14 }}>{item.summary}</p>}

              {/* Commentary — one big section */}
              <div style={{ border: `1px solid ${COLORS.border}`, borderRadius: 8, background: COLORS.surface, padding: '10px 14px', marginBottom: 12 }}>
                <div style={{ fontWeight: 600, fontSize: 14, color: COLORS.text, marginBottom: 6 }}>Commentary</div>
                {item.commentary?.trim() ? (
                  <div style={{ fontSize: 14, color: COLORS.text }}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.commentary}</ReactMarkdown>
                  </div>
                ) : <span style={{ color: COLORS.textMuted, fontSize: 13 }}>No commentary yet.</span>}
              </div>

              {/* Acts proposed to be amended / introduced */}
              {(item.acts ?? []).map((a, ai) => {
                const expanded = !!open[`${item.id}-${ai}`]
                return (
                  <div key={ai} style={{ border: `1px solid ${COLORS.border}`, borderRadius: 8, background: COLORS.surface, marginBottom: 8 }}>
                    <button onClick={() => setOpen({ ...open, [`${item.id}-${ai}`]: !expanded })} style={{
                      width: '100%', textAlign: 'left', padding: '10px 14px', background: 'transparent', border: 'none', cursor: 'pointer', color: COLORS.text, fontSize: 14,
                    }}>
                      <span style={{ fontWeight: 600 }}>{a.name}</span>
                      <span style={{ color: COLORS.textMuted, fontSize: 12, marginLeft: 8 }}>[{a.relation === 'new' ? 'introduced' : 'amended'}] {a.sections?.length ? `· ${a.sections.length} section${a.sections.length === 1 ? '' : 's'}` : '· no sections yet'}</span>
                    </button>
                    {expanded && (
                      <div style={{ padding: '0 14px 10px' }}>
                        {(a.sections ?? []).map((s, si) => (
                          <div key={si} style={{ borderTop: `1px solid ${COLORS.border}`, padding: '8px 0' }}>
                            <div style={{ fontWeight: 600, fontSize: 13, color: COLORS.text }}>{s.title}</div>
                            {s.content?.trim() ? (
                              <div style={{ fontSize: 13, color: COLORS.text }}>
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{s.content}</ReactMarkdown>
                              </div>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
              {item.notes?.trim() ? (
                <p style={{ color: COLORS.textMuted, fontSize: 12, marginTop: 10, whiteSpace: 'pre-wrap' }}>{item.notes}</p>
              ) : null}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
