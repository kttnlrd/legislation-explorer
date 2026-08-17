import React, { useEffect, useRef, useState, useCallback } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import dagre from 'dagre'
import * as d3Force from 'd3-force'
import { COLORS } from './common/types'

const API = ''

interface GraphNode {
  id: string
  label: string
  short_label: string
  group: string
  url: string | null
}

interface GraphEdge {
  source: string
  target: string
  label: string
  weight?: number
  type?: string
}

interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  meta: { type: string; node_count: number; edge_count: number }
}

const GROUP_COLORS: Record<string, string> = {
  section: '#279e88',
  ruling: '#e67e22',
  case: '#3498db',
  definition: '#9b59b6',
  commentary: '#7f8c8d',
  private_ruling: '#e84393',
}

type LayoutMode = 'force' | 'radial' | 'tree'

const LAYOUT_LABELS: Record<LayoutMode, string> = {
  force: 'Force',
  radial: 'Radial',
  tree: 'Tree',
}

interface Props {
  type: 'section' | 'ruling' | 'case'
  act?: string
  section?: string
  citation?: string
  label: string
  onClose: () => void
}

// Dagre hierarchical layout
function computeDagrePositions(nodes: GraphNode[], edges: GraphEdge[]): Map<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 100, marginx: 40, marginy: 40 })

  for (const n of nodes) g.setNode(n.id, { width: 80, height: 30 })
  for (const e of edges) g.setEdge(e.source, e.target)

  dagre.layout(g)
  const positions = new Map<string, { x: number; y: number }>()
  for (const n of nodes) {
    const dagNode = g.node(n.id)
    if (dagNode) positions.set(n.id, { x: dagNode.x, y: dagNode.y })
  }
  return positions
}

// Radial layout: concentric rings by group type
const RADIAL_RADIUS: Record<string, number> = { section: 60, commentary: 120, definition: 120, ruling: 200, case: 280 }

function computeRadialPositions(nodes: GraphNode[]): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>()
  const rings: Record<string, GraphNode[]> = {}
  for (const n of nodes) {
    const g = n.group || 'section'
    if (!rings[g]) rings[g] = []
    rings[g].push(n)
  }
  for (const [group, groupNodes] of Object.entries(rings)) {
    const radius = RADIAL_RADIUS[group] || 180
    const count = groupNodes.length
    for (let i = 0; i < count; i++) {
      const angle = (2 * Math.PI * i) / count - Math.PI / 2
      positions.set(groupNodes[i].id, {
        x: radius * Math.cos(angle),
        y: radius * Math.sin(angle),
      })
    }
  }
  return positions
}

export default function GraphModal({ type, act, section, citation, label, onClose }: Props) {
  const [data, setData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null)
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('tree')
  const fgRef = useRef<any>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    let url = `${API}/api/graph/data?type=${type}`
    if (type === 'section' && act && section) {
      url += `&act=${encodeURIComponent(act)}&section=${encodeURIComponent(section)}`
    } else if (citation) {
      url += `&citation=${encodeURIComponent(citation)}`
    }
    fetch(url)
      .then(r => r.json())
      .then(d => {
        if (d.error) { setError(d.error); setLoading(false); return }
        setData(d)
        setLoading(false)
      })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [type, act, section, citation])

  // Apply custom forces when layout mode changes
  useEffect(() => {
    const fg = fgRef.current
    if (!fg || !data) return

    // Reset all custom forces first
    fg.d3Force('x', null)
    fg.d3Force('y', null)
    fg.d3Force('radial', null)

    if (layoutMode === 'force') {
      // High friction so it settles fast
      fg.d3Force('charge', d3Force.forceManyBody().strength(-120))
      fg.d3ReheatSimulation()
      return
    }

    if (layoutMode === 'radial') {
      fg.d3Force('charge', d3Force.forceManyBody().strength(-30))
      fg.d3Force('radial', d3Force.forceRadial((d: any) => RADIAL_RADIUS[d.group as string] || 180, 0, 0).strength(1))
      fg.d3ReheatSimulation()
      return
    }

    if (layoutMode === 'tree') {
      // Dagre hierarchical: pin nodes to pre-computed positions
      const positions = computeDagrePositions(data.nodes, data.edges)
      const cx = 300
      const cy = 300
      fg.d3Force('x', d3Force.forceX((d: any) => {
        const p = positions.get(d.id)
        return p ? p.x - cx : 0
      }).strength(1))
      fg.d3Force('y', d3Force.forceY((d: any) => {
        const p = positions.get(d.id)
        return p ? p.y - cy : 0
      }).strength(1))
      fg.d3Force('charge', d3Force.forceManyBody().strength(-50))
      fg.d3ReheatSimulation()
    }
  }, [layoutMode, data])

  const handleNodeClick = useCallback((node: GraphNode) => {
    if (node.url) {
      window.location.href = node.url
    }
  }, [])

  const graphData = data ? { nodes: data.nodes, links: data.edges } : { nodes: [], links: [] }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 10000,
      background: 'rgba(0,0,0,0.7)', display: 'flex',
      flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
    }} onClick={onClose}>
      <div style={{
        width: '90vw', height: '85vh', maxWidth: 1200,
        background: COLORS?.surface || '#1a1a2e', borderRadius: 12,
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
        border: '1px solid ' + (COLORS?.border || '#333'),
      }} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '12px 20px', borderBottom: '1px solid ' + (COLORS?.border || '#333'),
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <span style={{ fontSize: 14, color: COLORS?.heading || '#fff', fontWeight: 600 }}>
              Knowledge Graph: {label}
            </span>
            {data && (
              <span style={{ fontSize: 11, color: COLORS?.textMuted || '#888' }}>
                {data.meta.node_count} nodes · {data.meta.edge_count} edges
              </span>
            )}
            {hoveredNode && (
              <span style={{ fontSize: 11, color: GROUP_COLORS[hoveredNode.group] || '#888' }}>
                {hoveredNode.short_label}
              </span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {/* Layout switcher */}
            <div style={{
              display: 'flex', borderRadius: 6, overflow: 'hidden',
              border: '1px solid ' + (COLORS?.border || '#444'),
            }}>
              {(Object.keys(LAYOUT_LABELS) as LayoutMode[]).map(mode => (
                <button
                  key={mode}
                  onClick={() => setLayoutMode(mode)}
                  style={{
                    background: layoutMode === mode ? '#279e88' : 'transparent',
                    color: layoutMode === mode ? '#fff' : COLORS?.textMuted || '#888',
                    border: 'none', padding: '4px 12px', cursor: 'pointer',
                    fontSize: 11, fontWeight: layoutMode === mode ? 600 : 400,
                    transition: 'all 0.15s',
                  }}
                >
                  {LAYOUT_LABELS[mode]}
                </button>
              ))}
            </div>
            <button onClick={onClose} style={{
              background: 'none', border: 'none', color: COLORS?.textMuted || '#888',
              cursor: 'pointer', fontSize: 20, lineHeight: 1, padding: '4px 8px',
            }}>✕</button>
          </div>
        </div>

        {/* Legend */}
        <div style={{
          display: 'flex', gap: 16, padding: '6px 20px',
          borderBottom: '1px solid ' + (COLORS?.border || '#333'),
          fontSize: 11, color: COLORS?.textMuted || '#888',
        }}>
          {Object.entries(GROUP_COLORS).map(([g, c]) => (
            <span key={g} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: c, display: 'inline-block' }} />
              {g}
            </span>
          ))}
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 12, height: 2, background: 'rgba(39,158,136,0.4)', display: 'inline-block' }} />
            similarity
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 12, height: 2, background: 'rgba(255,255,255,0.15)', display: 'inline-block' }} />
            reference
          </span>
          <span style={{ marginLeft: 'auto' }}>
            Click a node to navigate · Drag to move · Scroll to zoom
          </span>
        </div>

        {/* Graph */}
        <div style={{ flex: 1, position: 'relative' }}>
          {loading && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex',
              alignItems: 'center', justifyContent: 'center',
              color: COLORS?.textMuted || '#888', fontSize: 13,
            }}>Loading graph...</div>
          )}
          {error && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex',
              alignItems: 'center', justifyContent: 'center',
              color: '#e74c3c', fontSize: 13,
            }}>Error: {error}</div>
          )}
          {data && !loading && (
            <ForceGraph2D
              ref={fgRef}
              graphData={graphData}
              nodeId="id"
              nodeColor={n => GROUP_COLORS[(n as GraphNode).group] || '#888'}
              nodeVal={n => (n as GraphNode).group === 'section' ? 3 : 2}
              linkLabel={e => (e as any).label}
              linkColor={e => {
                const edge = e as any
                return edge.type === 'similarity'
                  ? 'rgba(39,158,136,0.4)'
                  : 'rgba(255,255,255,0.15)'
              }}
              linkWidth={e => {
                const edge = e as any
                return edge.weight ? Math.max(0.3, edge.weight * 2) : 0.5
              }}
              linkDirectionalParticles={1}
              linkDirectionalParticleSpeed={0.005}
              linkDirectionalArrowLength={4}
              onNodeClick={handleNodeClick}
              onNodeHover={n => setHoveredNode(n as GraphNode | null)}
              width={undefined}
              height={undefined}
              backgroundColor={COLORS?.surface || '#1a1a2e'}
              d3VelocityDecay={0.9}
              warmupTicks={40}
              cooldownTicks={0}
              enableNodeDrag={true}
              enableZoomInteraction={true}
              minZoom={0.5}
              maxZoom={8}
              // Render permanent labels on every node
              nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
                const n = node as GraphNode
                const label = n.short_label
                const fontSize = Math.max(8, 11 / globalScale)
                const nodeR = n.group === 'section' ? 4 : 3
                ctx.beginPath()
                ctx.arc(node.x, node.y, nodeR, 0, 2 * Math.PI, false)
                ctx.fillStyle = GROUP_COLORS[n.group] || '#888'
                ctx.fill()
                // Draw label
                ctx.font = `${fontSize}px Inter, -apple-system, sans-serif`
                ctx.textAlign = 'center'
                ctx.textBaseline = 'top'
                const textWidth = ctx.measureText(label).width
                const padding = 2
                const boxX = node.x - textWidth / 2 - padding
                const boxY = node.y + nodeR + 2
                const boxW = textWidth + padding * 2
                const boxH = fontSize + padding * 2
                // Background pill for readability
                ctx.fillStyle = 'rgba(26, 26, 46, 0.8)'
                ctx.beginPath()
                ctx.roundRect(boxX, boxY, boxW, boxH, 3)
                ctx.fill()
                ctx.fillStyle = '#e0e0e0'
                ctx.fillText(label, node.x, boxY + padding - 1)
              }}
              // Highlight hovered node
              nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
                const n = node as GraphNode
                const nodeR = n.group === 'section' ? 10 : 8
                ctx.beginPath()
                ctx.arc(node.x, node.y, nodeR, 0, 2 * Math.PI, false)
                ctx.fillStyle = color
                ctx.fill()
              }}
            />
          )}
        </div>
      </div>
    </div>
  )
}