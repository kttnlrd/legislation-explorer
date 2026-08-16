import React, { useEffect, useMemo, useState } from 'react'
import { COLORS } from './common/types'

const API = ''

interface MapMeta {
  id: string
  title: string
  short?: string
  refs?: string
  act: string
  division: string
  subdivision: string
  summary: string
  node_count: number
  edge_count: number
}

const ACT_LABELS: Record<string, string> = {
  'itaa-1997': 'Income Tax Assessment Act 1997',
  'itaa-1936': 'Income Tax Assessment Act 1936',
  'gst-1999': 'GST Act 1999',
  'taa-1953': 'Taxation Administration Act 1953',
  'fbt-1986': 'FBT Assessment Act 1986',
  'sis-1993': 'Superannuation Industry (Supervision) Act 1993',
}

interface Props {
  onClose: () => void
  onOpen: (mapId: string) => void
}

export default function MapBrowser({ onClose, onOpen }: Props) {
  const [maps, setMaps] = useState<MapMeta[] | null>(null)
  const [query, setQuery] = useState('')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${API}/api/maps`)
      .then(r => { if (!r.ok) throw new Error('failed to load maps'); return r.json() })
      .then((data: MapMeta[]) => {
        setMaps(data)
        // auto-expand all acts by default
        const acts = new Set(data.map(m => m.act))
        setExpanded(acts)
      })
      .catch(e => setError(e.message))
  }, [])

  const grouped = useMemo(() => {
    if (!maps) return []
    const q = query.trim().toLowerCase()
    const filtered = q ? maps.filter(m =>
      (m.title || '').toLowerCase().includes(q) ||
      (m.subdivision || '').toLowerCase().includes(q) ||
      (m.summary || '').toLowerCase().includes(q) ||
      (m.id || '').toLowerCase().includes(q)
    ) : maps
    const byAct = new Map<string, MapMeta[]>()
    for (const m of filtered) {
      if (!byAct.has(m.act)) byAct.set(m.act, [])
      byAct.get(m.act)!.push(m)
    }
    return [...byAct.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [maps, query])

  const toggle = (act: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(act)) next.delete(act); else next.add(act)
      return next
    })
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={onClose}>
      <div style={{ width: 720, maxWidth: '92vw', maxHeight: '80vh', display: 'flex', flexDirection: 'column', background: COLORS.surface, border: '1px solid ' + COLORS.border, borderRadius: 12, overflow: 'hidden' }} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px 10px' }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: COLORS.heading, fontFamily: "'Montserrat', sans-serif" }}>Procedural knowledge maps</div>
            <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 2 }}>
              {maps ? `${maps.length} map${maps.length === 1 ? '' : 's'} — decision flows through a provision, with statute, commentary, cases and definitions at each step` : 'Loading…'}
            </div>
          </div>
          <button onClick={onClose} aria-label="Close" style={{ background: 'none', border: 'none', color: COLORS.textMuted, fontSize: 22, cursor: 'pointer', lineHeight: 1 }}>✕</button>
        </div>

        {/* Search */}
        <div style={{ padding: '0 20px 12px' }}>
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search maps (e.g. roll-over, 122-A, restructure)…"
            style={{
              width: '100%', padding: '9px 12px', borderRadius: 8,
              background: COLORS.bg, color: COLORS.text,
              border: `1px solid ${COLORS.border}`, fontSize: 13,
              outline: 'none',
            }}
          />
        </div>

        {/* Tree */}
        <div style={{ flex: 1, overflow: 'auto', padding: '0 12px 16px' }}>
          {error ? (
            <div style={{ color: COLORS.textMuted, fontSize: 13, padding: 20 }}>{error}</div>
          ) : !maps ? (
            <div style={{ color: COLORS.textMuted, fontSize: 13, padding: 20 }}>Loading maps…</div>
          ) : grouped.length === 0 ? (
            <div style={{ color: COLORS.textMuted, fontSize: 13, padding: 20 }}>No maps match "{query}".</div>
          ) : (
            grouped.map(([act, actMaps]) => (
              <div key={act} style={{ marginBottom: 6 }}>
                {/* Act header */}
                <button onClick={() => toggle(act)} style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '9px 10px', borderRadius: 8, background: 'transparent', border: 'none', cursor: 'pointer', textAlign: 'left', color: COLORS.text }}>
                  <span style={{ fontSize: 11, color: COLORS.textMuted, width: 12, display: 'inline-block', textAlign: 'center' }}>
                    {expanded.has(act) ? '▾' : '▸'}
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: COLORS.heading }}>{ACT_LABELS[act] || act}</span>
                  <span style={{ fontSize: 11, color: COLORS.textMuted }}>({actMaps.length})</span>
                </button>
                {expanded.has(act) && (
                  <div style={{ marginLeft: 30, marginTop: 2 }}>
                    {actMaps.map(m => (
                      <button key={m.id} onClick={() => onOpen(m.id)}
                              style={{ display: 'block', width: '100%', textAlign: 'left', padding: '8px 10px', borderRadius: 8, background: COLORS.bg, border: '1px solid ' + COLORS.border, cursor: 'pointer', marginBottom: 4 }}>
                        <div style={{ fontSize: 12.5, fontWeight: 600, color: COLORS.text }}>
                          {m.refs ? `${m.refs} — ` : ''}{m.short || m.title}
                        </div>
                        {m.summary && (
                          <div style={{ fontSize: 11.5, color: COLORS.textMuted, marginTop: 2, lineHeight: 1.45 }}>{m.summary}</div>
                        )}
                        <div style={{ fontSize: 10.5, color: '#279e88', marginTop: 4 }}>
                          {m.node_count} steps · {m.edge_count} paths
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
