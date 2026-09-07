import React, { useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '../api'
import { COLORS } from './common/types'

type SectionNode = { id: string; title: string; content: string }
type ActNode = { name: string; relation: string; sections: SectionNode[] }
type DocNode = { title: string; url: string; note?: string }
type Item = {
  id: string
  title: string
  status?: string
  measure_type?: string
  summary?: string
  announced_date?: string
  source_url?: string
  notes?: string
  commentary?: string
  acts?: ActNode[]
  documents?: DocNode[]
}

const STATUS_COLORS: Record<string, string> = {
  announced: '#b8860b',
  exposure_draft: '#c0562b',
  before_parliament: '#2f6fb2',
  passed: '#1f7a3d',
  enacted: '#1f7a3d',
  withdrawn: '#777',
}
const TYPE_LABELS: Record<string, string> = { bill: 'Bill', exposure_draft: 'Exposure draft', announcement: 'Announcement', ato_draft: 'ATO draft', other: 'Other' }

/** Tree address of the selected node: `${itemId}::act:${ai}` or `${itemId}::sec:${ai}:${si}` */
function addr(itemId: string, actIdx: number, secIdx?: number): string {
  return secIdx === undefined ? `${itemId}::act:${actIdx}` : `${itemId}::sec:${actIdx}:${secIdx}`
}

/**
 * Read-only Proposed Law viewer — a three-level tree per proposal:
 *   proposal (title + date)  →  each act (amended / new)  →  each proposed section.
 * Commentary / EM material stays as external links (source_url etc).
 * Content is authored via MCP (proposed_law_add / proposed_law_update); nothing here edits.
 */
export default function ProposedLawBrowser({ isMobile }: { isMobile: boolean }) {
  const [items, setItems] = useState<Item[] | null>(null)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [sel, setSel] = useState<string | null>(null)
  const [detail, setDetail] = useState<{ item: Item; act?: ActNode; actIdx?: number; section?: SectionNode } | null>(null)

  useEffect(() => { api.proposedLawList().then(d => setItems((d as any)?.items ?? [])) }, [])

  // Default: first proposal expanded, nothing selected yet (overview shows on the right).
  useEffect(() => {
    if (items && items.length > 0) {
      setExpanded(prev => {
        if (Object.keys(prev).length > 0) return prev
        const next: Record<string, boolean> = {}
        for (const it of items) next[`i:${it.id}`] = prev[`i:${it.id}`] ?? (it.id === items[0].id)
        return next
      })
    }
  }, [items])

  const toggle = (key: string) => setExpanded(prev => ({ ...prev, [key]: !prev[key] }))

  const openAct = (item: Item, ai: number) => {
    toggle(`a:${item.id}:${ai}`)
  }

  const openSection = (item: Item, ai: number, si: number) => {
    const act = item.acts?.[ai]
    const section = act?.sections?.[si]
    if (!act || !section) return
    setSel(addr(item.id, ai, si))
    setDetail({ item, act, actIdx: ai, section })
  }

  const openOverview = (item: Item) => {
    setSel(`i:${item.id}`)
    setDetail({ item })
  }

  // Effective detail pane (keeps showing content even if item list re-fetches).
  const shown = detail ?? (items?.[0] ? { item: items[0] } : null)

  const chevron = (key: string) => {
    const isOpen = !!expanded[key]
    return <span style={{ color: COLORS.textMuted, fontSize: 11, width: 16, display: 'inline-block', textAlign: 'center', userSelect: 'none' }}>{isOpen ? '▼' : '▶'}</span>
  }

  const actTag = (relation: string) => (
    <span style={{
      fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 4, marginLeft: 6,
      color: '#fff',
      background: relation === 'new' ? '#1f7a3d' : '#2f6fb2',
      verticalAlign: 'middle',
    }}>{relation === 'new' ? 'NEW' : 'AMEND'}</span>
  )

  return (
    <div style={{ padding: 16, maxWidth: 1100, margin: '0 auto' }}>
      <h2 style={{ color: COLORS.heading, margin: '0 0 4px' }}>Proposed Law</h2>
      <p style={{ color: COLORS.textMuted, margin: '0 0 16px', fontSize: 13 }}>
        Tracked measures — not yet law. Authoring via MCP (<code>proposed_law_add</code> / <code>proposed_law_update</code>).
        Only integrated into the corpus if enacted.
      </p>

      {!items ? (
        <p style={{ color: COLORS.textMuted }}>Loading…</p>
      ) : items.length === 0 ? (
        <p style={{ color: COLORS.textMuted }}>Nothing tracked yet.</p>
      ) : (
        <div style={{ display: 'flex', gap: 16, flexDirection: isMobile ? 'column' : 'row', alignItems: 'flex-start' }}>
          {/* ── Tree pane ─────────────────────────────────────────────── */}
          <div style={{
            flex: '0 0 340px', width: isMobile ? '100%' : 340,
            border: `1px solid ${COLORS.border}`, borderRadius: 10,
            background: COLORS.surface, overflow: 'auto', maxHeight: isMobile ? '50vh' : '70vh',
          }}>
            {items.map(it => {
              const itemKey = `i:${it.id}`
              const itemOpen = !!expanded[itemKey]
              const acts = it.acts ?? []
              return (
                <div key={it.id} style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  {/* Level 1 — the proposal itself */}
                  <button onClick={() => { toggle(itemKey); openOverview(it) }} style={{
                    width: '100%', textAlign: 'left', padding: '10px 12px', cursor: 'pointer',
                    background: sel === `i:${it.id}` ? COLORS.surfaceHover : 'transparent', border: 'none',
                    color: COLORS.text, display: 'flex', alignItems: 'center', gap: 6,
                  }}>
                    {chevron(itemKey)}
                    <span style={{ fontWeight: 600, fontSize: 14, flex: 1 }}>{it.title}</span>
                    <span style={{ color: STATUS_COLORS[it.status ?? 'announced'], fontSize: 11, fontWeight: 600 }}>● {it.status}</span>
                  </button>

                  {itemOpen && (
                    <div style={{ paddingBottom: 8 }}>
                      {/* External material row */}
                      {(it.source_url || it.commentary?.trim()) && (
                        <div style={{ marginLeft: 34, marginBottom: 4 }}>
                          <div style={{ fontSize: 12, color: COLORS.textMuted, padding: '3px 8px' }}>
                            {it.announced_date && <span style={{ marginRight: 8 }}>📅 {it.announced_date}</span>}
                            {it.source_url && (
                              <a href={it.source_url} target="_blank" rel="noreferrer" style={{ color: COLORS.accent, marginRight: 8 }}>
                                Consultation ↗
                              </a>
                            )}
                            <span style={{ color: COLORS.textMuted }}>{TYPE_LABELS[it.measure_type ?? 'other'] ?? it.measure_type}</span>
                          </div>
                        </div>
                      )}

                      {/* Documents — plain external links, no breakdown */}
                      {(it.documents ?? []).length > 0 && (
                        <div style={{ marginLeft: 34, marginBottom: 6 }}>
                          {(it.documents ?? []).map((doc, di) => (
                            <div key={di} style={{ padding: '2px 8px' }}>
                              <a href={doc.url || '#'} target="_blank" rel="noreferrer"
                                 style={{ color: COLORS.accent, fontSize: 12.5, textDecoration: 'none' }}>
                                📄 {doc.title}
                              </a>
                              {doc.note ? <span style={{ color: COLORS.textMuted, fontSize: 11, marginLeft: 6 }}>{doc.note}</span> : null}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Level 2 — each act proposed to be amended / introduced */}
                      {acts.length === 0 && (
                        <div style={{ marginLeft: 34, fontSize: 12, color: COLORS.textMuted, padding: '4px 8px' }}>
                          No acts modelled yet — add via <code>proposed_law_update</code> with <code>acts</code>.
                        </div>
                      )}
                      {acts.map((a, ai) => {
                        const actKey = `a:${it.id}:${ai}`
                        const actOpen = !!expanded[actKey]
                        return (
                          <div key={`${it.id}-${ai}`}>
                            <button onClick={() => openAct(it, ai)} style={{
                              width: '100%', textAlign: 'left', padding: '6px 8px', paddingLeft: 34,
                              cursor: 'pointer', background: sel === addr(it.id, ai) ? COLORS.surfaceHover : 'transparent',
                              border: 'none', color: COLORS.text, display: 'flex', alignItems: 'center', gap: 4,
                              fontSize: 13,
                            }}>
                              {chevron(actKey)}
                              <span style={{ fontWeight: 600 }}>{a.name}</span>
                              {actTag(a.relation ?? 'amended')}
                              <span style={{ color: COLORS.textMuted, fontSize: 11, marginLeft: 'auto' }}>
                                {a.sections?.length ?? 0} section{(a.sections?.length ?? 0) === 1 ? '' : 's'}
                              </span>
                            </button>

                            {/* Level 3 — each proposed section */}
                            {actOpen && (
                              <div style={{ marginLeft: 34 + 16 }}>
                                {(a.sections ?? []).length === 0 && (
                                  <div style={{ fontSize: 12, color: COLORS.textMuted, padding: '4px 8px' }}>
                                    No sections yet.
                                  </div>
                                )}
                                {(a.sections ?? []).map((s, si) => {
                                  const a2 = addr(it.id, ai, si)
                                  return (
                                    <button key={a2} onClick={() => openSection(it, ai, si)} style={{
                                      display: 'block', width: '100%', textAlign: 'left', padding: '5px 8px', paddingLeft: 8,
                                      cursor: 'pointer', background: sel === a2 ? COLORS.surfaceHover : 'transparent',
                                      border: 'none', borderLeft: `2px solid ${sel === a2 ? COLORS.accent : 'transparent'}`,
                                      color: sel === a2 ? COLORS.accent : COLORS.text, fontSize: 12.5,
                                    }}>
                                      {s.title}
                                    </button>
                                  )
                                })}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {/* ── Content pane ──────────────────────────────────────────── */}
          <div style={{ flex: 1, minWidth: 0 }}>
            {!shown ? (
              <p style={{ color: COLORS.textMuted }}>Select a proposal or section.</p>
            ) : (
              <>
                <h3 style={{ color: COLORS.heading, margin: '0 0 4px', fontSize: 17 }}>
                  {shown.section ? shown.act?.name : shown.item.title}
                </h3>
                <div style={{ color: COLORS.textMuted, fontSize: 12, marginBottom: 10 }}>
                  {shown.section
                    ? `${shown.item.title} › ${shown.act?.name} [${shown.act?.relation === 'new' ? 'introduced' : 'amended'}] › ${shown.section.title}`
                    : `${shown.item.status ?? ''}${shown.item.announced_date ? ' · ' + shown.item.announced_date : ''}${shown.item.measure_type ? ' · ' + (TYPE_LABELS[shown.item.measure_type] ?? shown.item.measure_type) : ''}`}
                </div>

                {shown.section ? (
                  <div style={{ border: `1px solid ${COLORS.border}`, borderRadius: 8, background: COLORS.surface, padding: '14px 18px' }}>
                    <div style={{ fontWeight: 700, fontSize: 15, color: COLORS.heading, marginBottom: 8 }}>{shown.section.title}</div>
                    {shown.section.content?.trim() ? (
                      <div style={{ fontSize: 14, color: COLORS.text, lineHeight: 1.6 }}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{shown.section.content}</ReactMarkdown>
                      </div>
                    ) : (
                      <span style={{ color: COLORS.textMuted, fontSize: 13 }}>No proposed text yet.</span>
                    )}
                  </div>
                ) : (
                  <>
                    {shown.item.summary && <p style={{ color: COLORS.text, margin: '0 0 12px', fontSize: 14 }}>{shown.item.summary}</p>}

                    {/* Overview: proposed amendment tree summary */}
                    {(shown.item.acts ?? []).length > 0 && (
                      <div style={{ marginBottom: 12 }}>
                        <div style={{ fontWeight: 600, fontSize: 13, color: COLORS.text, marginBottom: 6 }}>Proposed changes</div>
                        {(shown.item.acts ?? []).map((a, ai) => (
                          <div key={ai} style={{ border: `1px solid ${COLORS.border}`, borderRadius: 8, background: COLORS.surface, padding: '10px 14px', marginBottom: 6 }}>
                            <div style={{ fontSize: 14, color: COLORS.text }}>
                              <span style={{ fontWeight: 600 }}>{a.name}</span>
                              {actTag(a.relation ?? 'amended')}
                            </div>
                            {(a.sections ?? []).map((s, si) => (
                              <button key={si} onClick={() => openSection(shown.item as Item, ai, si)} style={{
                                display: 'block', marginTop: 6, textAlign: 'left', width: '100%',
                                background: 'transparent', border: 'none', cursor: 'pointer',
                                color: COLORS.accent, fontSize: 13, padding: '2px 0',
                              }}>
                                › {s.title}
                              </button>
                            ))}
                          </div>
                        ))}
                      </div>
                    )}

                    {shown.item.commentary?.trim() ? (
                      <div style={{ border: `1px solid ${COLORS.border}`, borderRadius: 8, background: COLORS.surface, padding: '10px 14px', marginBottom: 12 }}>
                        <div style={{ fontWeight: 600, fontSize: 14, color: COLORS.text, marginBottom: 6 }}>Commentary</div>
                        <div style={{ fontSize: 14, color: COLORS.text }}>
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{shown.item.commentary}</ReactMarkdown>
                        </div>
                      </div>
                    ) : null}

                    {shown.item.notes?.trim() && (
                      <p style={{ color: COLORS.textMuted, fontSize: 12, whiteSpace: 'pre-wrap' }}>{shown.item.notes}</p>
                    )}

                    {/* Documents — plain external links */}
                    {(shown.item.documents ?? []).length > 0 && (
                      <div style={{ marginTop: 12 }}>
                        <div style={{ fontWeight: 600, fontSize: 13, color: COLORS.text, marginBottom: 6 }}>Documents</div>
                        {(shown.item.documents ?? []).map((doc, di) => (
                          <div key={di} style={{ padding: '3px 0' }}>
                            <a href={doc.url || '#'} target="_blank" rel="noreferrer" style={{ color: COLORS.accent, fontSize: 13 }}>
                              📄 {doc.title}
                            </a>
                            {doc.note ? <span style={{ color: COLORS.textMuted, fontSize: 12, marginLeft: 6 }}>{doc.note}</span> : null}
                          </div>
                        ))}
                      </div>
                    )}

                    {shown.item.source_url && !shown.section && (
                      <p style={{ margin: '4px 0 0' }}>
                        <a href={shown.item.source_url} target="_blank" rel="noreferrer" style={{ color: COLORS.accent, fontSize: 13 }}>
                          Consultation / EM material ↗
                        </a>
                      </p>
                    )}
                  </>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
