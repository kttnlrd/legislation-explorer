import React, { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import { COLORS } from './common/types'
import { shortActName } from '../utils/display'

// ---------------------------------------------------------------- types

interface GraphItem {
  key: string
  label: string
  node_type: string
  url: string | null
}

interface GraphGroup {
  edge_type: string
  display: string
  total: number
  items: GraphItem[]
}

interface RelatedSection {
  id: string
  act: string
  title: string
}

interface DefinedTerm {
  term: string
  section: string
  anchor: string
  title: string
}

interface SmartLinkPanelProps {
  act: string
  section: string
  /** Override the graph key (e.g. "private_ruling:EV/123") — when set,
   *  only the graph-driven groups render (no Sections/Definitions). */
  graphKey?: string
  onNavigate?: (act: string, section: string, anchor?: string) => void
  onNavigateRuling?: (citation: string) => void
  onNavigateCase?: (citation: string) => void
}

const PREVIEW_ITEMS = 5
const EXPAND_LIMIT = 100

// Collapsible dropdown group
function CollapsibleGroup({
  title, count, open, setOpen, children, footer,
}: {
  title: string; count: number; open: boolean; setOpen: (v: boolean) => void
  children: React.ReactNode; footer?: React.ReactNode
}) {
  return (
    <div style={{
      background: COLORS.surface, borderRadius: 6, border: `1px solid ${COLORS.border}`,
      overflow: 'hidden',
    }}>
      <div
        style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '8px 12px', cursor: 'pointer',
          fontSize: 13, fontWeight: 600, color: COLORS.heading,
        }}
        onClick={() => setOpen(!open)}
      >
        <span>{title} <span style={{ color: COLORS.textMuted, fontWeight: 400 }}>({count})</span></span>
        <span style={{ color: COLORS.textMuted, fontSize: 14 }}>{open ? '\u25b2' : '\u25bc'}</span>
      </div>
      {open && (
        <div style={{ padding: '4px 10px 10px', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {children}
          {footer}
        </div>
      )}
    </div>
  )
}

// Clickable item style
function itemStyle(clickable: boolean): React.CSSProperties {
  const base: React.CSSProperties = {
    padding: '6px 10px', borderRadius: 4, fontSize: 13,
    background: COLORS.surface, border: `1px solid ${COLORS.border}`,
  }
  if (clickable) {
    return { ...base, cursor: 'pointer', color: COLORS.accent }
  }
  return base
}

const SmartLinkPanel: React.FC<SmartLinkPanelProps> = ({
  act, section, graphKey, onNavigate, onNavigateRuling, onNavigateCase,
}) => {
  const [graphGroups, setGraphGroups] = useState<GraphGroup[]>([])
  const [relatedSections, setRelatedSections] = useState<RelatedSection[]>([])
  const [definedTerms, setDefinedTerms] = useState<DefinedTerm[]>([])
  const [loading, setLoading] = useState<boolean>(true)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [expanding, setExpanding] = useState<Record<string, boolean>>({})

  // Dropdown open states — all default closed
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({})
  const toggleOpen = (key: string) => setOpenGroups(o => ({ ...o, [key]: !o[key] }))

  const graphKeyResolved = graphKey || `section:${act}:${section}`
  const isGraphOnly = !!graphKey

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      setGraphGroups([])
      setExpanded({})
      try {
        const rel = await api.graphRelated(graphKeyResolved, PREVIEW_ITEMS).catch(() => ({ groups: [] }))
        setGraphGroups(rel.groups || [])
        if (!isGraphOnly) {
          const refs = await api.sectionRefs(act, section).catch(() => ({ sections: [], definitions: [] }))
          setRelatedSections(refs.sections || [])

          const refDefs: DefinedTerm[] = (refs.definitions || []).map((d: any) => ({
            term: d.term || d.id || '',
            section: d.section || '',
            anchor: d.anchor || '',
            title: d.title || `s ${d.section}`,
          }))
          const seen = new Set<string>()
          setDefinedTerms(refDefs.filter(d => {
            if (seen.has(d.term.toLowerCase())) return false
            seen.add(d.term.toLowerCase())
            return true
          }))
        }
      } catch {
        // partial data still better than nothing
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [act, section, graphKeyResolved, isGraphOnly])

  const handleSectionClick = (link: RelatedSection) => {
    if (onNavigate) onNavigate(link.act, link.id)
  }

  const handleDefinitionClick = (def: DefinedTerm) => {
    if (onNavigate) onNavigate(act, def.section, def.anchor)
  }

  const handleGraphItemClick = (item: GraphItem) => {
    if ((item.node_type === 'section' || item.node_type === 'commentary') && item.url) {
      const parts = item.url.split('/').filter(Boolean)
      if (parts.length >= 2 && onNavigate) onNavigate(parts[0], parts[1])
    } else if (item.node_type === 'public_ruling' && onNavigateRuling) {
      onNavigateRuling(item.label)
    } else if (item.node_type === 'case' && onNavigateCase) {
      onNavigateCase(item.label)
    } else if (item.node_type === 'private_ruling' && item.url) {
      window.location.assign(item.url)
    }
  }

  const expandGroup = useCallback(async (group: GraphGroup) => {
    setExpanding(e => ({ ...e, [group.edge_type]: true }))
    try {
      const rel = await api.graphRelated(graphKeyResolved, EXPAND_LIMIT, group.edge_type)
      const g = (rel.groups || []).find((x: GraphGroup) => x.edge_type === group.edge_type)
      if (g) {
        setGraphGroups(prev => prev.map(p => p.edge_type === g.edge_type ? g : p))
        setExpanded(e => ({ ...e, [group.edge_type]: true }))
      }
    } catch {
      // leave as-is on failure
    } finally {
      setExpanding(e => ({ ...e, [group.edge_type]: false }))
    }
  }, [graphKeyResolved])

  const hasContent = graphGroups.length > 0 || relatedSections.length > 0 || definedTerms.length > 0

  if (loading) {
    return <div style={{ padding: '12px 0', color: COLORS.textMuted, fontSize: 13 }}>Loading related information...</div>
  }

  if (!hasContent) {
    return null
  }

  const sameActSections = relatedSections.filter(s => s.act === act)
  const crossActSections = relatedSections.filter(s => s.act !== act)
  const showSectionRefs = !isGraphOnly && (sameActSections.length > 0 || crossActSections.length > 0)

  return (
    <div style={{
      background: COLORS.surface, borderRadius: 8, padding: 12,
      border: `1px solid ${COLORS.border}`, boxShadow: `0 2px 4px rgba(0,0,0,0.2)`,
    }}>
      <h3 style={{ color: COLORS.heading, fontSize: 14, fontWeight: 600, margin: '0 0 12px' }}>Related</h3>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {/* Sections — from in-text references (not graph: no section→section edges) */}
        {showSectionRefs && (
          <CollapsibleGroup
            title="Sections"
            count={sameActSections.length + crossActSections.length}
            open={!!openGroups.sections}
            setOpen={() => toggleOpen('sections')}
          >
            {sameActSections.length > 0 && (
              <>
                <div style={{ color: COLORS.textMuted, fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4, marginTop: 2 }}>
                  Same Act
                </div>
                {sameActSections.slice(0, PREVIEW_ITEMS).map((link) => (
                  <div
                    key={'sa-' + link.id}
                    style={itemStyle(true)}
                    onClick={() => handleSectionClick(link)}
                    onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.background = COLORS.surfaceHover }}
                    onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = COLORS.surface }}
                  >
                    s{link.id}{link.title ? ` \u2014 ${link.title}` : ''}
                  </div>
                ))}
                {sameActSections.length > PREVIEW_ITEMS && (
                  <div style={{ color: COLORS.textMuted, fontSize: 12, padding: '4px 10px' }}>
                    … and {sameActSections.length - PREVIEW_ITEMS} more
                  </div>
                )}
              </>
            )}
            {crossActSections.length > 0 && (
              <>
                <div style={{ color: COLORS.textMuted, fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4, marginTop: sameActSections.length > 0 ? 8 : 2 }}>
                  Cross-Act
                </div>
                {crossActSections.slice(0, PREVIEW_ITEMS).map((link) => (
                  <div
                    key={'ca-' + link.act + '-' + link.id}
                    style={itemStyle(true)}
                    onClick={() => handleSectionClick(link)}
                    onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.background = COLORS.surfaceHover }}
                    onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = COLORS.surface }}
                  >
                    {shortActName(link.act)} s{link.id}{link.title ? ` \u2014 ${link.title}` : ''}
                  </div>
                ))}
                {crossActSections.length > PREVIEW_ITEMS && (
                  <div style={{ color: COLORS.textMuted, fontSize: 12, padding: '4px 10px' }}>
                    … and {crossActSections.length - PREVIEW_ITEMS} more
                  </div>
                )}
              </>
            )}
          </CollapsibleGroup>
        )}

        {/* Definitions — from section-refs scan */}
        {!isGraphOnly && definedTerms.length > 0 && (
          <CollapsibleGroup
            title="Definitions"
            count={definedTerms.length}
            open={!!openGroups.definitions}
            setOpen={() => toggleOpen('definitions')}
          >
            {definedTerms.slice(0, PREVIEW_ITEMS).map((def) => (
              <div
                key={'def-' + def.term}
                style={itemStyle(true)}
                onClick={() => handleDefinitionClick(def)}
                onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.background = COLORS.surfaceHover }}
                onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = COLORS.surface }}
              >
                {def.term}{def.section ? ` \u2014 s ${def.section}` : ''}
              </div>
            ))}
            {definedTerms.length > PREVIEW_ITEMS && (
              <div style={{ color: COLORS.textMuted, fontSize: 12, padding: '4px 10px' }}>
                … and {definedTerms.length - PREVIEW_ITEMS} more
              </div>
            )}
          </CollapsibleGroup>
        )}

        {/* Graph-driven groups: Rulings, Private Rulings, Cases, Commentary */}
        {graphGroups.map((group) => (
          <CollapsibleGroup
            key={group.edge_type}
            title={group.display}
            count={group.total}
            open={!!openGroups[group.edge_type]}
            setOpen={() => toggleOpen(group.edge_type)}
            footer={
              !expanded[group.edge_type] && group.total > group.items.length ? (
                <button
                  style={{
                    marginTop: 4, padding: '6px 10px', borderRadius: 4, fontSize: 12,
                    background: COLORS.surfaceHover, color: COLORS.accent,
                    border: `1px solid ${COLORS.border}`, cursor: 'pointer',
                  }}
                  disabled={!!expanding[group.edge_type]}
                  onClick={(e) => { e.stopPropagation(); expandGroup(group) }}
                >
                  {expanding[group.edge_type] ? 'Loading…' : `Show all (${group.total})`}
                </button>
              ) : undefined
            }
          >
            {group.items.map((item) => {
              const clickable = !!item.url
              return (
                <div
                  key={item.key}
                  style={itemStyle(clickable)}
                  onClick={() => clickable && handleGraphItemClick(item)}
                  onMouseEnter={e => {
                    if (clickable) (e.currentTarget as HTMLDivElement).style.background = COLORS.surfaceHover
                  }}
                  onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = COLORS.surface }}
                >
                  {item.label}
                  {item.node_type === 'private_ruling' && (
                    <span style={{ color: COLORS.textMuted, fontSize: 11 }}> (private)</span>
                  )}
                </div>
              )
            })}
          </CollapsibleGroup>
        ))}
      </div>
    </div>
  )
}

export default SmartLinkPanel
