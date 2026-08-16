import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import dagre from 'dagre'
import { COLORS } from './common/types'

const API = ''

interface MapNode {
  id: string
  type: 'start' | 'event' | 'decision' | 'action' | 'outcome' | 'end'
  label: string
  body: string
  statute?: { act: string; section: string; title?: string }[]
  commentary?: string[]
  cases?: { citation: string; note?: string }[]
  definitions?: string[]
}

interface MapEdge {
  from: string
  to: string
  label?: string
}

interface ProceduralMap {
  id: string
  title: string
  short?: string
  refs?: string
  act: string
  division: string
  subdivision: string
  summary: string
  nodes: MapNode[]
  edges: MapEdge[]
}

const NODE_STYLES: Record<string, { fill: string; stroke: string; text: string; shape: 'rect' | 'diamond' | 'ellipse' }> = {
  start:     { fill: '#1a3d2e', stroke: '#279e88', text: '#e8f5f0', shape: 'ellipse' },
  event:     { fill: '#2a3b5c', stroke: '#4a6fd4', text: '#e8edf8', shape: 'rect' },
  decision:  { fill: '#3a2f14', stroke: '#d4a72c', text: '#faf3dd', shape: 'diamond' },
  action:    { fill: '#23324a', stroke: '#4a90d9', text: '#e8f0fa', shape: 'rect' },
  outcome:   { fill: '#143d33', stroke: '#27ae60', text: '#e6f7ef', shape: 'rect' },
  end:       { fill: '#3a1a1a', stroke: '#c0392b', text: '#faeaea', shape: 'rect' },
}

function computeLayout(map: ProceduralMap) {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'TB', nodesep: 30, ranksep: 55, marginx: 20, marginy: 20 })
  for (const n of map.nodes) {
    const style = NODE_STYLES[n.type] || NODE_STYLES.start
    const w = style.shape === 'diamond' ? 200 : 240
    const h = style.shape === 'diamond' ? 110 : 64
    g.setNode(n.id, { width: w, height: h })
  }
  for (const e of map.edges) g.setEdge(e.from, e.to, { label: e.label || '' })
  dagre.layout(g)
  const positions = new Map<string, { x: number; y: number }>()
  for (const n of map.nodes) {
    const p = g.node(n.id)
    if (p) positions.set(n.id, { x: p.x, y: p.y })
  }
  return positions
}

interface Props {
  mapId: string
  onClose?: () => void
  onOpenSection: (act: string, section: string) => void
  height?: string
  isMobile?: boolean
}

export default function MapView({ mapId, onClose, onOpenSection, height, isMobile }: Props) {
  const [map, setMap] = useState<ProceduralMap | null>(null)
  const [selected, setSelected] = useState<MapNode | null>(null)
  const [error, setError] = useState<string | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const [view, setView] = useState({ scale: 0.9, x: 0, y: 0 })
  const dragRef = useRef<{ startX: number; startY: number; viewX: number; viewY: number; moved: boolean } | null>(null)
  const pointersRef = useRef(new Map<number, { x: number; y: number }>())
  const pinchRef = useRef<{ dist: number; midX: number; midY: number; scale: number; x: number; y: number } | null>(null)

  // Mobile detection — falls back to self-detect when prop not passed (MapModal)
  const [isMobileState, setIsMobileState] = useState(false)
  useEffect(() => {
    const check = () => setIsMobileState(window.innerWidth < 768)
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])
  const mobile = isMobile ?? isMobileState

  useEffect(() => {
    setMap(null)
    setSelected(null)
    setError(null)
    fetch(`${API}/api/maps/${mapId}`)
      .then(r => { if (!r.ok) throw new Error('map not found'); return r.json() })
      .then(setMap)
      .catch(e => setError(e.message))
  }, [mapId])

  const layout = useMemo(() => (map ? computeLayout(map) : null), [map])

  const fitView = useCallback(() => {
    if (!map || !layout) return
    const minX = Math.min(...map.nodes.map(n => layout.get(n.id)!.x))
    const maxX = Math.max(...map.nodes.map(n => layout.get(n.id)!.x))
    const minY = Math.min(...map.nodes.map(n => layout.get(n.id)!.y))
    const maxY = Math.max(...map.nodes.map(n => layout.get(n.id)!.y))
    const containerW = svgRef.current?.parentElement?.clientWidth || 800
    const containerH = svgRef.current?.parentElement?.clientHeight || 600
    const pad = 60
    const scale = Math.min((containerW - pad) / (maxX - minX + 240), (containerH - pad) / (maxY - minY + 130), 1.1)
    const s = Math.max(scale, 0.2)
    setView({
      scale: s,
      x: containerW / 2 - s * (minX + (maxX - minX) / 2),
      y: containerH / 2 - s * (minY + (maxY - minY) / 2),
    })
  }, [map, layout])

  useEffect(() => {
    if (map && layout) {
      const t = setTimeout(fitView, 60)
      return () => clearTimeout(t)
    }
  }, [map, layout, fitView])

  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault()
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15
    setView(v => {
      const ns = Math.min(Math.max(v.scale * factor, 0.15), 3)
      const k = ns / v.scale
      return {
        scale: ns,
        x: mx - (mx - v.x) * k,
        y: my - (my - v.y) * k,
      }
    })
  }, [])

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    // Don't capture when the press starts on an interactive element (node or
    // button) — capture would swallow the subsequent click event.
    const t = e.target as Element
    if (t.closest('button') || t.closest('[data-node]')) return
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    pointersRef.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    if (pointersRef.current.size === 2) {
      const pts = [...pointersRef.current.values()]
      const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y)
      pinchRef.current = { dist, midX: (pts[0].x + pts[1].x) / 2, midY: (pts[0].y + pts[1].y) / 2, scale: view.scale, x: view.x, y: view.y }
      dragRef.current = null
    } else {
      dragRef.current = { startX: e.clientX, startY: e.clientY, viewX: view.x, viewY: view.y, moved: false }
    }
  }, [view])

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!pointersRef.current.has(e.pointerId)) return
    pointersRef.current.set(e.pointerId, { x: e.clientX, y: e.clientY })
    const pts = [...pointersRef.current.values()]
    // Two-finger pinch zoom
    if (pts.length === 2 && pinchRef.current) {
      const p = pinchRef.current
      const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y)
      const midX = (pts[0].x + pts[1].x) / 2
      const midY = (pts[0].y + pts[1].y) / 2
      const ns = Math.min(Math.max(p.scale * (dist / p.dist), 0.15), 3)
      const k = ns / p.scale
      setView({
        scale: ns,
        x: midX - (p.midX - p.x) * k,
        y: midY - (p.midY - p.y) * k,
      })
      if (dragRef.current) dragRef.current.moved = true
      return
    }
    if (!dragRef.current) return
    // Snapshot the drag state — the setView updater runs async (React batches
    // pointermove updates) and pointerup may have nulled dragRef by then.
    // Reading the ref inside the updater crashes the render phase (blank screen).
    const d = dragRef.current
    const dx = e.clientX - d.startX
    const dy = e.clientY - d.startY
    if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true
    setView(v => ({ ...v, x: d.viewX + dx, y: d.viewY + dy }))
  }, [])

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    pointersRef.current.delete(e.pointerId)
    if (pointersRef.current.size < 2) pinchRef.current = null
    if (pointersRef.current.size === 0) dragRef.current = null
  }, [])

  if (error) {
    return (
      <div style={{ background: COLORS.surface, color: COLORS.text, padding: 24, borderRadius: 10, maxWidth: 420, border: '1px solid ' + COLORS.border }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Map unavailable</div>
        <div style={{ fontSize: 13, color: COLORS.textMuted }}>{error}</div>
        {onClose && (
          <button onClick={onClose} style={{ marginTop: 16, padding: '6px 14px', borderRadius: 6, border: '1px solid ' + COLORS.border, background: COLORS.bg, color: COLORS.text, cursor: 'pointer' }}>Close</button>
        )}
      </div>
    )
  }

  if (!map || !layout) {
    return (
      <div style={{ height: height || '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: COLORS.textMuted, fontSize: 14 }}>
        Loading map…
      </div>
    )
  }

  const nodeById = new Map(map.nodes.map(n => [n.id, n]))
  const edgesByNode = new Map<string, MapEdge[]>()
  for (const e of map.edges) {
    if (!edgesByNode.has(e.from)) edgesByNode.set(e.from, [])
    edgesByNode.get(e.from)!.push(e)
  }

  const viewW = Math.max(900, ...map.nodes.map(n => (layout.get(n.id)?.x || 0) + 260))
  const viewH = Math.max(600, ...map.nodes.map(n => (layout.get(n.id)?.y || 0) + 120))

  const zoomIn = () => setView(v => ({ ...v, scale: Math.min(v.scale * 1.2, 3) }))
  const zoomOut = () => setView(v => ({ ...v, scale: Math.max(v.scale / 1.2, 0.15) }))

  const detailBody = selected ? (
    <>
      <div style={{ fontSize: 14, fontWeight: 600, color: COLORS.text, marginBottom: 10, lineHeight: 1.4 }}>
        {selected.label}
      </div>
      {selected.body && (
        <div style={{ fontSize: 12.5, color: COLORS.textMuted, lineHeight: 1.55, marginBottom: 12 }}>
          {selected.body}
        </div>
      )}
      {selected.statute && selected.statute.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 10.5, fontWeight: 700, color: '#279e88', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>Statute</div>
          {selected.statute.map((s, i) => (
            <button key={i} onClick={() => onOpenSection(s.act, s.section.split('(')[0].trim())}
                    style={{ display: 'block', width: '100%', textAlign: 'left', padding: '7px 10px', marginBottom: 5, borderRadius: 6, border: '1px solid ' + COLORS.border, background: COLORS.bg, color: '#279e88', cursor: 'pointer', fontSize: 12.5 }}>
              <span style={{ fontWeight: 700 }}>{s.section}</span>
              {s.title ? <span style={{ color: COLORS.textMuted }}> — {s.title}</span> : null}
            </button>
          ))}
        </div>
      )}
      {selected.cases && selected.cases.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 10.5, fontWeight: 700, color: '#3498db', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>Cases</div>
          {selected.cases.map((c, i) => (
            <div key={i} style={{ fontSize: 12.5, color: '#3498db', marginBottom: 4 }}>
              {c.citation}
              {c.note ? <div style={{ color: COLORS.textMuted, fontSize: 11.5 }}>{c.note}</div> : null}
            </div>
          ))}
        </div>
      )}
      {selected.definitions && selected.definitions.length > 0 && (
        <div>
          <div style={{ fontSize: 10.5, fontWeight: 700, color: '#9b59b6', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>Defined terms</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {selected.definitions.map((d, i) => (
              <span key={i} style={{ padding: '3px 8px', borderRadius: 20, background: 'rgba(155,89,182,0.15)', color: '#c39bd3', fontSize: 11.5 }}>{d}</span>
            ))}
          </div>
        </div>
      )}
    </>
  ) : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: height || '100%', minHeight: height ? 480 : 0, maxWidth: 1400, width: '100%' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 8, gap: 8 }}>
        <div>
          <div style={{ fontSize: mobile ? 15 : 16, fontWeight: 700, color: COLORS.heading, fontFamily: "'Montserrat', sans-serif" }}>
            {map.short || map.title}
          </div>
          {map.refs && (
            <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4, maxWidth: 900 }}>
              {map.refs}
            </div>
          )}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: mobile ? 10 : 14, marginTop: 8, fontSize: 11, color: COLORS.textMuted }}>
            <span style={{ color: '#279e88' }}>● start</span>
            <span style={{ color: '#4a6fd4' }}>■ event</span>
            <span style={{ color: '#d4a72c' }}>◇ decision</span>
            <span style={{ color: '#4a90d9' }}>▭ action</span>
            <span style={{ color: '#27ae60' }}>▭ outcome</span>
            <span style={{ color: '#c0392b' }}>▭ no relief / end</span>
          </div>
        </div>
        {onClose && (
          <button onClick={onClose} aria-label="Close map" style={{ background: 'none', border: 'none', color: COLORS.textMuted, fontSize: 22, cursor: 'pointer', lineHeight: 1, flexShrink: 0, width: mobile ? 40 : 32, height: mobile ? 40 : 32, display: 'flex', alignItems: 'center', justifyContent: 'center', marginRight: mobile ? -8 : 0 }}>✕</button>
        )}
      </div>

      <div style={{ position: 'relative', display: 'flex', flex: 1, minHeight: 0, gap: 12, flexDirection: mobile ? 'column' : 'row' }}>
        {/* Flowchart */}
        <div
          style={{ flex: 1, minHeight: 0, background: COLORS.bg, border: '1px solid ' + COLORS.border, borderRadius: 10, overflow: 'hidden', position: 'relative', touchAction: 'none' }}
          onWheel={onWheel}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          <svg ref={svgRef} width="100%" height="100%" style={{ display: 'block' }}>
            <g transform={`translate(${view.x}, ${view.y}) scale(${view.scale})`}>
              {/* edges */}
              {map.edges.map((e, i) => {
                const a = layout.get(e.from)!
                const b = layout.get(e.to)!
                const dx = b.x - a.x
                const dy = b.y - a.y
                const len = Math.sqrt(dx * dx + dy * dy) || 1
                const ux = dx / len, uy = dy / len
                const sx = a.x + ux * 32, sy = a.y + uy * 32
                const tx = b.x - ux * 32, ty = b.y - uy * 32
                const mx = (sx + tx) / 2, my = (sy + ty) / 2
                return (
                  <g key={i}>
                    <line x1={sx} y1={sy} x2={tx} y2={ty} stroke="#556" strokeWidth={1.4} markerEnd="url(#map-arrow)" />
                    {e.label && (
                      <text x={mx} y={my - 5} textAnchor="middle" fontSize={10} fill={COLORS.textMuted}
                            style={{ paintOrder: 'stroke', stroke: COLORS.bg, strokeWidth: 3 }}>
                        {e.label}
                      </text>
                    )}
                  </g>
                )
              })}
              <defs>
                <marker id="map-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#667" />
                </marker>
              </defs>
              {/* nodes */}
              {map.nodes.map(n => {
                const p = layout.get(n.id)!
                const style = NODE_STYLES[n.type] || NODE_STYLES.start
                const w = style.shape === 'diamond' ? 200 : 240
                const h = style.shape === 'diamond' ? 110 : 64
                const isSel = selected?.id === n.id
                const words = n.label.split(' ')
                const lineLen = Math.max(20, Math.min(34, Math.floor(w / 7.2)))
                const lines: string[] = []
                let cur = ''
                for (const word of words) {
                  if ((cur + ' ' + word).trim().length > lineLen && cur) { lines.push(cur.trim()); cur = word }
                  else cur = (cur + ' ' + word).trim()
                }
                if (cur) lines.push(cur)
                const shown = lines.slice(0, 3)
                const truncated = lines.length > 3
                return (
                  <g key={n.id} data-node onClick={() => { if (!dragRef.current?.moved) setSelected(n) }}
                     style={{ cursor: 'pointer' }}
                     transform={`translate(${p.x - w / 2}, ${p.y - h / 2})`}>
                    {style.shape === 'diamond' ? (
                      <polygon points={`${w / 2},0 ${w},${h / 2} ${w / 2},${h} 0,${h / 2}`}
                               fill={style.fill} stroke={isSel ? '#fff' : style.stroke} strokeWidth={isSel ? 2 : 1.4} />
                    ) : style.shape === 'ellipse' ? (
                      <ellipse cx={w / 2} cy={h / 2} rx={w / 2} ry={h / 2}
                               fill={style.fill} stroke={isSel ? '#fff' : style.stroke} strokeWidth={isSel ? 2 : 1.4} />
                    ) : (
                      <rect x={2} y={2} width={w - 4} height={h - 4} rx={8}
                            fill={style.fill} stroke={isSel ? '#fff' : style.stroke} strokeWidth={isSel ? 2 : 1.4} />
                    )}
                    <text x={w / 2} y={h / 2 - ((shown.length - 1) * 7) / 2} textAnchor="middle" fontSize={10.5} fill={style.text} style={{ pointerEvents: 'none' }}>
                      {shown.map((ln, li) => (
                        <tspan key={li} x={w / 2} dy={li === 0 ? 0 : 14}>{ln}</tspan>
                      ))}
                      {truncated && <tspan x={w / 2} dy={14} fill="#aaa">…</tspan>}
                    </text>
                  </g>
                )
              })}
            </g>
          </svg>
          {/* Zoom controls */}
          <div style={{ position: 'absolute', right: 12, top: 12, display: 'flex', flexDirection: 'column', gap: 6, zIndex: 20 }}>
            <button onClick={zoomIn} aria-label="Zoom in" style={{ width: mobile ? 40 : 32, height: mobile ? 40 : 32, borderRadius: 8, background: COLORS.surface, color: COLORS.text, border: '1px solid ' + COLORS.border, cursor: 'pointer', fontSize: mobile ? 20 : 16, lineHeight: 1 }}>+</button>
            <button onClick={zoomOut} aria-label="Zoom out" style={{ width: mobile ? 40 : 32, height: mobile ? 40 : 32, borderRadius: 8, background: COLORS.surface, color: COLORS.text, border: '1px solid ' + COLORS.border, cursor: 'pointer', fontSize: mobile ? 20 : 16, lineHeight: 1 }}>−</button>
            <button onClick={fitView} aria-label="Fit to view" title="Fit to view" style={{ width: mobile ? 40 : 32, height: mobile ? 40 : 32, borderRadius: 8, background: COLORS.surface, color: COLORS.text, border: '1px solid ' + COLORS.border, cursor: 'pointer', fontSize: mobile ? 16 : 13, lineHeight: 1 }}>⤢</button>
          </div>
          <div style={{ position: 'absolute', left: 12, bottom: 12, fontSize: 10.5, color: COLORS.textMuted, background: 'rgba(0,0,0,0.5)', padding: '4px 8px', borderRadius: 6, pointerEvents: 'none' }}>
            {mobile ? 'drag to pan · pinch to zoom · tap a node' : 'scroll to zoom · drag to pan · click a node for details'}
          </div>
        </div>

        {/* Detail panel (desktop side panel) */}
        {!mobile && (
          <div style={{ width: 360, background: COLORS.surface, border: '1px solid ' + COLORS.border, borderRadius: 10, overflow: 'auto', padding: 16, flexShrink: 0 }}>
            {!selected ? (
              <div style={{ color: COLORS.textMuted, fontSize: 13, lineHeight: 1.5 }}>
                Click a node to see the statute, commentary, cases and definitions behind that step.
              </div>
            ) : (
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: COLORS.heading, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.4 }}>
                  {selected.type}
                </div>
                {detailBody}
              </div>
            )}
          </div>
        )}

        {/* Detail sheet (mobile bottom sheet) */}
        {mobile && selected && (
          <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, maxHeight: '55%', overflow: 'auto', background: COLORS.surface, borderTop: '1px solid ' + COLORS.border, borderRadius: '12px 12px 0 0', padding: '12px 14px 14px', boxShadow: '0 -10px 30px rgba(0,0,0,0.4)', WebkitOverflowScrolling: 'touch' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: COLORS.heading, textTransform: 'uppercase', letterSpacing: 0.4 }}>{selected.type}</div>
              <button onClick={() => setSelected(null)} aria-label="Close details" style={{ background: 'none', border: 'none', color: COLORS.textMuted, fontSize: 20, cursor: 'pointer', lineHeight: 1, width: 40, height: 40, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginRight: -6 }}>✕</button>
            </div>
            {detailBody}
          </div>
        )}
      </div>
    </div>
  )
}
