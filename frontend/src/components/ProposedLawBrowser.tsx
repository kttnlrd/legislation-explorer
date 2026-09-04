import React, { useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '../api'
import { COLORS } from './common/types'

const STATUS_COLORS: Record<string, string> = {
  announced: '#b8860b',
  exposure_draft: '#c05621',
  before_parliament: '#1f6feb',
  passed: '#2f855a',
  enacted: '#276749',
  withdrawn: '#7d8590',
}
const STATUSES = ['announced', 'exposure_draft', 'before_parliament', 'passed', 'enacted', 'withdrawn']
const TYPE_LABEL: Record<string, string> = {
  bill: 'Bill', exposure_draft: 'Exposure draft', announcement: 'Announcement',
  ato_draft: 'ATO draft', other: 'Other',
}

interface Section { title: string; content: string }
interface Act { name: string; relation: string; sections: Section[] }
interface Item {
  id: string; title: string; status: string; measure_type: string; summary: string;
  announced_date?: string; source_url?: string; notes: string; commentary: string;
  acts: Act[]; added_at?: string;
}

const button: React.CSSProperties = {
  background: COLORS.surfaceHover, color: COLORS.text, border: `1px solid ${COLORS.border}`,
  borderRadius: 6, padding: '4px 10px', fontSize: 13, cursor: 'pointer',
}
const accentButton: React.CSSProperties = { ...button, background: COLORS.accent, color: '#fff', border: 'none' }
const dangerButton: React.CSSProperties = { ...button, background: 'transparent', color: '#d1242f', border: `1px solid #d1242f` }
const input: React.CSSProperties = {
  width: '100%', background: COLORS.surfaceHover, color: COLORS.text, border: `1px solid ${COLORS.border}`,
  borderRadius: 6, padding: '6px 8px', fontSize: 14, fontFamily: 'inherit', boxSizing: 'border-box' as const,
}
const textarea: React.CSSProperties = { ...input, minHeight: 140, fontFamily: 'ui-monospace, monospace', fontSize: 13, lineHeight: 1.5 }

function Markdown({ md }: { md: string }) {
  return (
    <div style={{ fontSize: 15, lineHeight: 1.7 }}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{md || '*Nothing here yet.*'}</ReactMarkdown>
    </div>
  )
}

export default function ProposedLawBrowser({ isMobile }: { isMobile: boolean }) {
  const [items, setItems] = useState<Item[] | null>(null)
  const [selId, setSelId] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [selNode, setSelNode] = useState<string>('commentary') // 'commentary' | `a{ai}s{si}`
  const [showAdd, setShowAdd] = useState(false)
  const [err, setErr] = useState('')
  // add-item form
  const [fTitle, setFTitle] = useState('')
  const [fStatus, setFStatus] = useState('announced')
  const [fType, setFType] = useState('bill')
  const [fSummary, setFSummary] = useState('')
  const [fUrl, setFUrl] = useState('')
  // editing content (in-pane textarea)
  const [editText, setEditText] = useState<string | null>(null)   // null = view mode
  // add-act / add-section inline forms
  const [addingAct, setAddingAct] = useState(false)
  const [aActName, setAActName] = useState('')
  const [aActRel, setAActRel] = useState('amended')
  const [addingSec, setAddingSec] = useState(false)
  const [aSecTitle, setASecTitle] = useState('')

  useEffect(() => {
    api.proposedLawList().then((d: any) => {
      const its: Item[] = (d?.items || []).map((it: any) => ({ acts: [], commentary: '', ...it }))
      setItems(its)
      if (its.length && !selId) setSelId(its[0].id)
    }).catch(() => setErr('Failed to load proposed law items'))
  }, [])

  const sel = useMemo(() => (items || []).find(i => i.id === selId) || null, [items, selId])
  const actIdx = selNode === 'commentary' ? -1 : parseInt(selNode.split('a')[1]?.split('s')[0] || '-1', 10)
  const secIdx = selNode === 'commentary' ? -1 : parseInt(selNode.split('s')[1] || '-1', 10)

  function refresh(it: Item) {
    setItems(prev => (prev || []).map(x => (x.id === it.id ? it : x)))
  }
  async function save(fn: () => Promise<any>, onDone?: () => void) {
    try {
      await fn()
      const d: any = await api.proposedLawList()
      setItems((d?.items || []).map((x: any) => ({ acts: [], commentary: '', ...x })))
      onDone && onDone()
    } catch (e: any) { setErr(e?.message || 'Save failed') }
  }

  function nodeContent(): { title: string; body: string } {
    if (!sel) return { title: '', body: '' }
    if (selNode === 'commentary') return { title: 'Commentary', body: sel.commentary }
    const act = sel.acts[actIdx]
    if (!act) return { title: '', body: '' }
    const sec = act.sections[secIdx]
    if (secIdx >= 0 && sec) return { title: sec.title, body: sec.content }
    return { title: act.name, body: `*${act.relation === 'introduced' ? 'New Act' : 'Proposed amendments'} — ${act.sections.length} section${act.sections.length === 1 ? '' : 's'}.*` }
  }

  const toggle = (k: string) => setExpanded(p => ({ ...p, [k]: !p[k] }))

  if (items === null) return <div style={{ color: COLORS.text, padding: 16 }}>Loading…</div>

  // ---------- item list view (no selection yet / mobile back) ----------
  if (!sel) {
    return (
      <div style={{ padding: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 12 }}>
          <h2 style={{ color: COLORS.heading, margin: 0 }}>Proposed Law</h2>
          <button style={accentButton} onClick={() => setShowAdd(v => !v)}>{showAdd ? 'Cancel' : '+ Add item'}</button>
        </div>
        {err && <div style={{ color: '#d1242f', marginBottom: 8 }}>{err}</div>}
        {showAdd && (
          <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: 12, marginBottom: 12, display: 'grid', gap: 8 }}>
            <input style={input} placeholder="Measure title (e.g. Treasury Laws Amendment …)" value={fTitle} onChange={e => setFTitle(e.target.value)} />
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <select style={input} value={fStatus} onChange={e => setFStatus(e.target.value)}>
                {STATUSES.map(s => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
              </select>
              <select style={input} value={fType} onChange={e => setFType(e.target.value)}>
                {Object.entries(TYPE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <textarea style={textarea} placeholder="Summary — what the measure does" value={fSummary} onChange={e => setFSummary(e.target.value)} />
            <input style={input} placeholder="Source URL" value={fUrl} onChange={e => setFUrl(e.target.value)} />
            <div style={{ display: 'flex', gap: 8 }}>
              <button style={accentButton} onClick={async () => {
                if (!fTitle.trim()) return setErr('Title is required')
                await save(() => api.proposedLawAdd({ title: fTitle, status: fStatus, measure_type: fType, summary: fSummary, source_url: fUrl }).then(() => setShowAdd(false)))
                setFTitle(''); setFSummary(''); setFUrl('')
                const d: any = await api.proposedLawList(); const its = d?.items || []
                setItems(its.map((x: any) => ({ acts: [], commentary: '', ...x })))
                if (its.length) setSelId(its[0].id)
              }}>Save item</button>
            </div>
          </div>
        )}
        <div style={{ display: 'grid', gap: 8 }}>
          {(items || []).map(it => (
            <div key={it.id} onClick={() => setSelId(it.id)}
                 style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: '10px 12px', cursor: 'pointer' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <div style={{ fontWeight: 600, color: COLORS.heading, fontSize: 15 }}>{it.title}</div>
                <span style={{ background: STATUS_COLORS[it.status] || '#666', color: '#fff', borderRadius: 999, padding: '2px 10px', fontSize: 12 }}>
                  {it.status.replace('_', ' ')}</span>
              </div>
              {it.summary && <div style={{ color: COLORS.textMuted, fontSize: 13, marginTop: 4 }}>{it.summary.slice(0, 220)}</div>}
              <div style={{ display: 'flex', gap: 14, marginTop: 6, color: COLORS.textMuted, fontSize: 12, flexWrap: 'wrap' }}>
                <span>{TYPE_LABEL[it.measure_type] || it.measure_type}</span>
                {it.announced_date && <span>Announced {it.announced_date}</span>}
                <span>{it.acts.length} act{it.acts.length === 1 ? '' : 's'} · {it.commentary ? 'commentary ✓' : 'no commentary'}</span>
              </div>
            </div>
          ))}
          {!items?.length && <div style={{ color: COLORS.textMuted, padding: 20, textAlign: 'center' }}>Nothing here yet — add the first proposed measure.</div>}
        </div>
      </div>
    )
  }

  // ---------- item detail: header + tree/content ----------
  const body = nodeContent()
  return (
    <div style={{ padding: 16 }}>
      <div style={{ marginBottom: 10, display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <button style={button} onClick={() => { setSelId(null); setSelNode('commentary') }}>← All items</button>
        {!isMobile && <span style={{ color: COLORS.textMuted, fontSize: 13 }}>/</span>}
        <span style={{ color: COLORS.heading, fontWeight: 600 }}>{sel.title}</span>
      </div>
      <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: '10px 14px', marginBottom: 12, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <select style={{ ...input, width: 'auto' }} value={sel.status} onChange={e => save(() => api.proposedLawUpdate(sel.id, { status: e.target.value }))}>
          {STATUSES.map(s => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
        </select>
        <span style={{ fontSize: 13, color: COLORS.textMuted }}>{TYPE_LABEL[sel.measure_type] || sel.measure_type}</span>
        {sel.source_url && <a href={sel.source_url} target="_blank" rel="noreferrer" style={{ color: COLORS.accent, fontSize: 13 }}>Source ↗</a>}
        <button style={dangerButton} onClick={async () => {
          if (!confirm(`Delete "${sel.title}"?`)) return
          await api.proposedLawDelete(sel.id); setSelId(null)
          const d: any = await api.proposedLawList(); setItems((d?.items || []).map((x: any) => ({ acts: [], commentary: '', ...x })))
        }}>Delete item</button>
      </div>
      {sel.summary && <div style={{ color: COLORS.textMuted, fontSize: 14, marginBottom: 10 }}>{sel.summary}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '300px 1fr', gap: 12, alignItems: 'start' }}>
        {/* tree pane */}
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: 10, fontSize: 14 }}>
          <div style={{ fontWeight: 600, color: COLORS.textMuted, fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.4, margin: '2px 4px 8px' }}>Contents</div>
          <div onClick={() => setSelNode('commentary')} style={{ cursor: 'pointer', padding: '5px 8px', borderRadius: 6, color: selNode === 'commentary' ? '#fff' : COLORS.text, background: selNode === 'commentary' ? COLORS.accent : 'transparent' }}>
            Commentary</div>
          <div style={{ height: 1, background: COLORS.border, margin: '8px 4px' }} />
          {sel.acts.map((act, ai) => {
            const k = `a${ai}`; const open = !!expanded[k]
            return (
              <div key={k}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 8px', borderRadius: 6, cursor: 'pointer' }}
                     onClick={() => toggle(k)}>
                  <span style={{ color: COLORS.heading, fontWeight: 600 }}>{open ? '▾' : '▸'} {act.name}</span>
                  <span style={{ color: COLORS.textMuted, fontSize: 11 }}>{act.relation === 'introduced' ? 'new' : 'amend'}</span>
                </div>
                {open && (
                  <div style={{ paddingLeft: 14 }}>
                    {act.sections.map((sec, si) => {
                      const node = `a${ai}s${si}`; const active = selNode === node
                      return <div key={node} onClick={() => setSelNode(node)} style={{ cursor: 'pointer', padding: '4px 8px', borderRadius: 6, color: active ? '#fff' : COLORS.text, background: active ? COLORS.accent : 'transparent', fontSize: 13 }}>
                        {sec.title}</div>
                    })}
                    {!act.sections.length && <div style={{ color: COLORS.textMuted, fontSize: 12, padding: '4px 8px' }}>No sections yet</div>}
                    {!addingSec && <button style={{ ...button, fontSize: 12, margin: '6px 8px' }} onClick={() => { setAddingSec(true); setAddingAct(false) }}>+ Add section</button>}
                    {addingSec && (
                      <div style={{ padding: '6px 8px', display: 'grid', gap: 6 }}>
                        <input style={input} placeholder="Proposed section title (e.g. s 100A — amendments)" value={aSecTitle} onChange={e => setASecTitle(e.target.value)} />
                        <div style={{ display: 'flex', gap: 6 }}>
                          <button style={accentButton} onClick={async () => {
                            if (!aSecTitle.trim()) return
                            await save(() => api.proposedLawAddSection(sel.id, ai, { title: aSecTitle }))
                            setASecTitle(''); setAddingSec(false)
                          }}>Save</button>
                          <button style={button} onClick={() => setAddingSec(false)}>Cancel</button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
          {!sel.acts.length && <div style={{ color: COLORS.textMuted, fontSize: 12, padding: '4px 8px' }}>No acts yet</div>}
          {!addingAct && <button style={{ ...button, fontSize: 12, margin: '8px' }} onClick={() => { setAddingAct(true); setAddingSec(false) }}>+ Add act to amend / introduce</button>}
          {addingAct && (
            <div style={{ padding: '6px 8px', display: 'grid', gap: 6 }}>
              <input style={input} placeholder="Act name (e.g. Income Tax Assessment Act 1997)" value={aActName} onChange={e => setAActName(e.target.value)} />
              <select style={input} value={aActRel} onChange={e => setAActRel(e.target.value)}>
                <option value="amended">Amended</option>
                <option value="introduced">New Act introduced</option>
              </select>
              <div style={{ display: 'flex', gap: 6 }}>
                <button style={accentButton} onClick={async () => {
                  if (!aActName.trim()) return
                  await save(() => api.proposedLawAddAct(sel.id, { name: aActName, relation: aActRel }))
                  setAActName(''); setAddingAct(false)
                }}>Save</button>
                <button style={button} onClick={() => setAddingAct(false)}>Cancel</button>
              </div>
            </div>
          )}
        </div>

        {/* content pane */}
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: '12px 16px', minHeight: 320 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' }}>
            <div style={{ fontWeight: 600, color: COLORS.heading }}>{body.title}</div>
            {!(selNode === 'commentary' && !sel.commentary) && (
              <div style={{ display: 'flex', gap: 6 }}>
                {editText === null
                  ? <button style={button} onClick={() => setEditText(body.body)}>Edit</button>
                  : <><button style={accentButton} onClick={async () => {
                      if (selNode === 'commentary') await save(() => api.proposedLawSetCommentary(sel.id, editText))
                      else await save(() => api.proposedLawUpdateSection(sel.id, actIdx, secIdx, { title: body.title, content: editText }))
                      setEditText(null)
                    }}>Save</button>
                    <button style={button} onClick={() => setEditText(null)}>Cancel</button></>}
              </div>
            )}
          </div>
          {editText !== null
            ? <textarea style={{ ...textarea, width: '100%' }} value={editText} onChange={e => setEditText(e.target.value)} />
            : (secIdx >= 0 && !sel.acts[actIdx]?.sections[secIdx]
                ? <Markdown md={''} />
                : <Markdown md={body.body} />)}
        </div>
      </div>
    </div>
  )
}
