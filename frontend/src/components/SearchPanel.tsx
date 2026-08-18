import React, { useEffect, useRef, useState } from 'react'
import { COLORS } from './common/types'
import { api } from '../api'
import { shortActName } from '../utils/display'

const PAGE_SIZE = 25

interface FlatResult {
  act: string
  act_name: string
  section: string
  title: string
  headline: string
  match_type: string
  score: number
  snippet?: string
  type?: string
}

interface SearchPanelProps {
  acts: { id: string; name: string }[]
  onNavigate: (act: string, section: string) => void
  isMobile: boolean
  onResultsChange?: (count: number) => void
  onAtoSearch?: () => void
}

export default function SearchPanel({ acts, onNavigate, isMobile, onResultsChange, onAtoSearch }: SearchPanelProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<FlatResult[]>([])
  const [unfilteredResults, setUnfilteredResults] = useState<FlatResult[]>([])
  const [filterOpen, setFilterOpen] = useState(false)
  const [sortMode, setSortMode] = useState<'bestmatch' | 'bysection' | 'byact'>('bestmatch')
  const [loading, setLoading] = useState(false)
  const [selectedActs, setSelectedActs] = useState<Set<string>>(new Set())
  const [currentPage, setCurrentPage] = useState(0)
  const [typeFilter, setTypeFilter] = useState<string>('')
  const [operator, setOperator] = useState<'AND' | 'OR'>('AND')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const [suggestions, setSuggestions] = useState<{ act: string; section: string; title: string; type: string }[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [highlightIdx, setHighlightIdx] = useState(-1)
  const containerRef = useRef<HTMLDivElement>(null)

  const SUGGEST_LIMIT = 8

  // Re-filter results when source selection changes
  useEffect(() => {
    if (unfilteredResults.length === 0) return
    const filtered = selectedActs.size > 0
      ? unfilteredResults.filter(r => selectedActs.has(r.act))
      : unfilteredResults
    setResults(filtered)
    setCurrentPage(0)
  }, [selectedActs, unfilteredResults])

  // Notify parent of results count
  useEffect(() => {
    onResultsChange?.(results.length)
  }, [results.length, onResultsChange])

  // Restore query from URL on direct load / back-nav (e.g. /search?q=...)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const q = params.get('q')
    if (q) {
      setQuery(q)
      doSearch(q)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Suggestions are only fetched when the user presses Search — no live
  // typing dropdown. They act as instant quick-nav while the full search runs.

  const runSearchWithSuggestions = async () => {
    const term = query.trim()
    if (!term) return
    setShowSuggestions(false)
    setSuggestions([])
    setHighlightIdx(-1)
    // Fast suggest endpoint gives immediate navigation options during the slow hybrid search
    try {
      const data = await api.suggest(term, SUGGEST_LIMIT)
      if (data.suggestions && data.suggestions.length > 0) {
        setSuggestions(data.suggestions)
        setShowSuggestions(true)
      }
    } catch { /* ignore */ }
    doSearch()
  }

  const doSearch = async (q?: string, filterOverride?: string) => {
    const term = (q || query).trim()
    if (!term) return

    setLoading(true)
    try {
      // Keep the query in the URL so direct loads / back-nav restore it
      window.history.replaceState(null, '', '/search?q=' + encodeURIComponent(term))
      const activeFilter = filterOverride !== undefined ? filterOverride : typeFilter
      if (sortMode === 'bestmatch') {
        const data = await api.searchHybrid(term, activeFilter || undefined, 200, {
          operator,
          dateFrom: dateFrom || undefined,
          dateTo: dateTo || undefined,
        })
        const allResults: FlatResult[] = (data.results || data || []).map((r: any) => ({
          act: r.act || '',
          act_name: r.act_name || '',
          section: r.section || '',
          title: r.title || '',
          headline: '',
          match_type: '',
          score: r.fusion_score || r.score || 0,
          snippet: r.snippet || '',
          type: r.source_type || r.type || 'section',
        }))
        setUnfilteredResults(allResults)
        if (selectedActs.size > 0) {
          setResults(allResults.filter(r => selectedActs.has(r.act)))
        } else {
          setResults(allResults)
        }
      } else {
        // Per-act search
        const targets = selectedActs.size > 0
          ? acts.filter(a => selectedActs.has(a.id))
          : acts
        const all: FlatResult[] = []
        for (const a of targets) {
          try {
            const data = await api.search(term, a.id)
            if (data.results) {
              all.push(...data.results.map((r: any) => ({
                act: a.id,
                act_name: a.name,
                section: r.section,
                title: r.title,
                headline: '',
                match_type: '',
                score: 0,
              })))
            }
          } catch { /* skip */ }
        }
        setUnfilteredResults(all)
        setResults(all)
      }
    } catch { setResults([]) }
    setLoading(false)
    setCurrentPage(0)
    // Results are ready — drop the quick-nav dropdown so it doesn't cover them
    setShowSuggestions(false)
    setSuggestions([])
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (showSuggestions && suggestions.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setHighlightIdx(i => Math.min(i + 1, suggestions.length - 1))
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setHighlightIdx(i => Math.max(i - 1, -1))
        return
      }
      if (e.key === 'Escape') {
        setShowSuggestions(false)
        setHighlightIdx(-1)
        return
      }
      if (e.key === 'Enter' && highlightIdx >= 0) {
        e.preventDefault()
        pickSuggestion(suggestions[highlightIdx])
        return
      }
    }
    if (e.key === 'Enter') {
      setShowSuggestions(false)
      runSearchWithSuggestions()
    }
  }

  const pickSuggestion = (s: { act: string; section: string; title: string; type: string }) => {
    setShowSuggestions(false)
    setSuggestions([])
    setQuery('')
    if (s.type === 'ruling') {
      onNavigate('rulings', s.section)
    } else {
      onNavigate(s.act, s.section)
    }
  }

  const handleSelect = (r: FlatResult) => {
    setQuery('')
    setResults([])
    if (r.type === 'case' && r.section) {
      onNavigate('tax-cases', r.section)
    } else if (r.section) {
      onNavigate(r.act, r.section)
    }
  }

  const toggleAct = (id: string) => {
    const next = new Set(selectedActs)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedActs(next)
  }

  // Pagination calculations
  const totalPages = Math.max(1, Math.ceil(results.length / PAGE_SIZE))
  const pageStart = currentPage * PAGE_SIZE
  const pageResults = results.slice(pageStart, pageStart + PAGE_SIZE)

  const filterButtonSvg = (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <line x1="2" y1="3" x2="14" y2="3" />
      <line x1="2" y1="8" x2="14" y2="8" />
      <line x1="2" y1="13" x2="14" y2="13" />
    </svg>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%', position: 'relative' }}>
      <style>{`@keyframes hermes-spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
      {/* Search input row */}
      <div style={{ display: 'flex', gap: 6, alignItems: 'stretch' }}>
        <div style={{ position: 'relative', flex: 1 }}>
          <input
            ref={inputRef}
            value={query}
            onChange={e => {
              setQuery(e.target.value)
              if (!e.target.value.trim()) {
                setShowSuggestions(false)
                setSuggestions([])
              }
            }}
            onKeyDown={handleKeyDown}
            onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
            placeholder="Search legislation..."
            style={{
              width: '100%',
              padding: isMobile ? '10px 10px' : '8px 10px',
              borderRadius: 6,
              background: COLORS.bg,
              color: COLORS.heading,
              border: `1px solid ${COLORS.border}`,
              fontSize: 13,
              fontFamily: "'Montserrat', sans-serif",
              outline: 'none',
            }}
          />
        </div>
        <button
          onClick={() => runSearchWithSuggestions()}
          onMouseDown={e => e.preventDefault()}
          style={{
            padding: isMobile ? '10px 14px' : '8px 14px', borderRadius: 6,
            background: COLORS.accent, color: '#fff',
            border: 'none', fontSize: 13, cursor: 'pointer',
            fontWeight: 600, fontFamily: "'Montserrat', sans-serif",
            whiteSpace: 'nowrap',
          }}
        >
          Search
        </button>
        {onAtoSearch && (
          <button
            onClick={onAtoSearch}
            title="Search the ATO Legal Database (live)"
            style={{
              padding: isMobile ? '10px 12px' : '8px 12px', borderRadius: 6,
              background: COLORS.surface, color: COLORS.textMuted,
              border: `1px solid ${COLORS.border}`,
              fontSize: 13, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontWeight: 600, fontFamily: "'Montserrat', sans-serif",
              whiteSpace: 'nowrap',
            }}
          >
            ATO
          </button>
        )}
        <button
          onClick={() => setFilterOpen(!filterOpen)}
          title="Filters"
          style={{
            padding: isMobile ? '10px 12px' : '8px 12px', borderRadius: 6,
            background: filterOpen ? COLORS.accent : COLORS.surface,
            color: filterOpen ? '#fff' : COLORS.textMuted,
            border: `1px solid ${filterOpen ? COLORS.accent : COLORS.border}`,
            fontSize: 13, cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontFamily: "'Montserrat', sans-serif",
          }}
        >
          {filterButtonSvg}
        </button>
      </div>

      {/* Autocomplete suggestions dropdown */}
      {showSuggestions && (
        <div
          style={{
            position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 400,
            marginTop: 2, background: COLORS.bg, borderRadius: 6,
            border: `1px solid ${COLORS.border}`, overflow: 'hidden',
            boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
          }}
        >
          {suggestions.map((s, i) => (
            <div
              key={`${s.act}-${s.section}`}
              onClick={() => pickSuggestion(s)}
              onMouseEnter={() => setHighlightIdx(i)}
              style={{
                padding: '8px 10px', cursor: 'pointer',
                fontSize: 12, fontFamily: "'Montserrat', sans-serif",
                color: COLORS.text,
                background: i === highlightIdx ? COLORS.accent + '18' : 'transparent',
                borderBottom: i < suggestions.length - 1 ? `1px solid ${COLORS.border}` : 'none',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                <span style={{ color: COLORS.accent, fontWeight: 600, whiteSpace: 'nowrap' }}>
                  {shortActName(s.act)} {s.section}
                </span>
                <span style={{ color: COLORS.textMuted, fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.title}
                </span>
              </div>
              <div style={{ fontSize: 9, color: COLORS.textMuted, opacity: 0.6, marginTop: 2 }}>
                {s.type === 'ruling' ? 'Ruling' : 'Section'}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Filters panel — absolutely positioned dropdown */}
      {filterOpen && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 300,
          marginTop: 2, background: COLORS.bg, borderRadius: 6,
          border: `1px solid ${COLORS.border}`,
          padding: 10,
          display: 'flex', flexDirection: 'column', gap: 8,
          boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
        }}>
          <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'Montserrat', sans-serif" }}>Match:</div>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {(['AND', 'OR'] as const).map(op => (
              <label
                key={op}
                style={{
                  fontSize: 11, color: COLORS.text, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 4,
                  padding: '3px 6px', borderRadius: 4,
                  background: operator === op ? COLORS.accent + '22' : 'transparent',
                  fontFamily: "'Montserrat', sans-serif",
                }}
              >
                <input
                  type="radio"
                  name="operator"
                  checked={operator === op}
                  onChange={() => setOperator(op)}
                  style={{ margin: 0 }}
                />
                {op === 'AND' ? 'All terms (AND)' : 'Any term (OR)'}
              </label>
            ))}
          </div>
          <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'Montserrat', sans-serif" }}>Date between:</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              type="date"
              value={dateFrom}
              onChange={e => setDateFrom(e.target.value)}
              style={{
                flex: 1, minWidth: 120, padding: '5px 6px', borderRadius: 4,
                background: COLORS.bg, color: COLORS.text,
                border: `1px solid ${COLORS.border}`,
                fontSize: 11, fontFamily: "'Montserrat', sans-serif",
              }}
            />
            <span style={{ fontSize: 11, color: COLORS.textMuted }}>to</span>
            <input
              type="date"
              value={dateTo}
              onChange={e => setDateTo(e.target.value)}
              style={{
                flex: 1, minWidth: 120, padding: '5px 6px', borderRadius: 4,
                background: COLORS.bg, color: COLORS.text,
                border: `1px solid ${COLORS.border}`,
                fontSize: 11, fontFamily: "'Montserrat', sans-serif",
              }}
            />
          </div>
          <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'Montserrat', sans-serif" }}>Sort:</div>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {(['bestmatch', 'bysection', 'byact'] as const).map(mode => (
              <label
                key={mode}
                style={{
                  fontSize: 11, color: COLORS.text, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 4,
                  padding: '3px 6px', borderRadius: 4,
                  background: sortMode === mode ? COLORS.accent + '22' : 'transparent',
                  fontFamily: "'Montserrat', sans-serif",
                }}
              >
                <input
                  type="radio"
                  name="sortMode"
                  checked={sortMode === mode}
                  onChange={() => setSortMode(mode)}
                  style={{ margin: 0 }}
                />
                {mode === 'bestmatch' ? 'Best match' : mode === 'bysection' ? 'By section' : 'By act'}
              </label>
            ))}
          </div>
          <div style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'Montserrat', sans-serif" }}>Sources:</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {acts.map(a => (
              <label
                key={a.id}
                style={{
                  fontSize: 11, color: COLORS.text, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 4,
                  padding: '3px 6px', borderRadius: 4,
                  background: selectedActs.has(a.id) ? COLORS.accent + '22' : 'transparent',
                  fontFamily: "'Montserrat', sans-serif",
                }}
              >
                <input
                  type="checkbox"
                  checked={selectedActs.has(a.id)}
                  onChange={() => toggleAct(a.id)}
                  style={{ margin: 0 }}
                />
                {shortActName(a.id)}
              </label>
            ))}
          </div>
        </div>
      )}

      {/* Results */}
      {loading && (
        <div style={{
          padding: '8px 4px', fontSize: 12, color: COLORS.textMuted,
          fontFamily: "'Montserrat', sans-serif",
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <img
            src="/favicon.png"
            alt=""
            style={{ width: 16, height: 16, animation: 'hermes-spin 1s linear infinite' }}
          />
          Searching...
        </div>
      )}
      {results.length > 0 && !loading && (
        <>
          {/* Type filter tabs */}
          <div style={{
            display: 'flex', gap: 4, padding: '4px 0',
            borderBottom: `1px solid ${COLORS.border}`,
            flexWrap: 'wrap',
          }}>
            {[
              { key: '', label: 'All' },
              { key: 'section', label: 'Sections' },
              { key: 'ruling', label: 'Rulings' },
              { key: 'case', label: 'Cases' },
              { key: 'commentary', label: 'Commentary' },
            ].map(t => (
              <button
                key={t.key}
                onClick={() => { setTypeFilter(t.key); setCurrentPage(0); doSearch(undefined, t.key) }}
                style={{
                  fontSize: 10, padding: '3px 8px', borderRadius: 4,
                  background: typeFilter === t.key ? COLORS.accent : COLORS.surface,
                  color: typeFilter === t.key ? '#fff' : COLORS.textMuted,
                  border: `1px solid ${typeFilter === t.key ? COLORS.accent : COLORS.border}`,
                  cursor: 'pointer', fontFamily: "'Montserrat', sans-serif",
                  fontWeight: typeFilter === t.key ? 600 : 400,
                }}
              >
                {t.label}
              </button>
            ))}
          </div>
          {/* Results header */}
          <div style={{
            fontSize: 10, color: COLORS.textMuted, fontFamily: "'Montserrat', sans-serif",
            padding: '4px 2px', borderBottom: `1px solid ${COLORS.border}`,
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          }}>
            <span>{results.length} result{results.length !== 1 ? 's' : ''} — Page {currentPage + 1} of {totalPages}</span>
          </div>

          {/* Results list */}
          <div style={{
            background: COLORS.bg, borderRadius: 6,
            border: `1px solid ${COLORS.border}`,
            textAlign: 'left',
          }}>
            {pageResults.map((r, i) => {
              const badgeBg = r.type === 'case' ? '#8B5CF6' :
                r.type === 'ruling' ? '#F59E0B' :
                r.type === 'commentary' ? '#10B981' :
                COLORS.accent
              const badgeLabel = r.type === 'case' ? 'Case' :
                r.type === 'ruling' ? 'Ruling' :
                r.type === 'commentary' ? 'Comm' :
                'Sec'
              const isRuling = r.type === 'ruling' || r.act === 'rulings'
              const isCchGuide = r.act.startsWith('master-')
              const isCase = r.type === 'case'
              const sectionDisplay = isCase
                ? r.title || r.section
                : isRuling
                  ? r.section
                  : isCchGuide
                    ? shortActName(r.act)
                    : `${shortActName(r.act)} ${r.section}`
              return (
              <div
                key={`${r.act}-${r.section}-${pageStart + i}`}
                onClick={() => handleSelect(r)}
                style={{
                  padding: isMobile ? '10px 12px' : '8px 12px', cursor: 'pointer', fontSize: 12,
                  color: COLORS.text, borderBottom: `1px solid ${COLORS.border}`,
                  fontFamily: "'Montserrat', sans-serif",
                }}
                onMouseEnter={e => e.currentTarget.style.background = COLORS.accent + '11'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, flexWrap: 'wrap' }}>
                  <span style={{
                    fontSize: 11, color: COLORS.accent, fontWeight: 600,
                    whiteSpace: 'nowrap', flexShrink: 0,
                  }}>
                    {sectionDisplay}
                  </span>
                  {r.title && r.title !== r.section && (
                    <span style={{
                      color: COLORS.textMuted,
                      wordBreak: 'break-word', overflowWrap: 'break-word',
                    }}>
                      {r.title}
                    </span>
                  )}
                </div>
                {r.snippet && (
                  <div style={{
                    fontSize: 11, color: COLORS.textMuted, opacity: 0.7,
                    marginTop: 3, paddingLeft: 2,
                    fontFamily: "'Lora', serif",
                    lineHeight: 1.4, textAlign: 'left',
                  }}
                    dangerouslySetInnerHTML={{ __html: r.snippet }}
                  />
                )}
                <div style={{ fontSize: 9, color: COLORS.textMuted, opacity: 0.5, marginTop: 2, textAlign: 'left', display: 'flex', gap: 4, alignItems: 'center' }}>
                  <span style={{
                    background: badgeBg, color: '#fff', borderRadius: 3,
                    padding: '1px 5px', fontSize: 8, fontWeight: 600,
                    fontFamily: "'Montserrat', sans-serif",
                  }}>{badgeLabel}</span>
                  <span>{sectionDisplay}</span>
                </div>
              </div>
            )})}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{
              display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 8,
              padding: '8px 0',
            }}>
              <button
                onClick={() => setCurrentPage(p => Math.max(0, p - 1))}
                disabled={currentPage === 0}
                style={{
                  padding: '6px 12px', borderRadius: 6,
                  background: currentPage === 0 ? COLORS.bg : COLORS.surface,
                  color: currentPage === 0 ? COLORS.textMuted : COLORS.text,
                  border: `1px solid ${COLORS.border}`,
                  cursor: currentPage === 0 ? 'default' : 'pointer',
                  fontSize: 11, fontFamily: "'Montserrat', sans-serif",
                }}
              >
                ← Previous
              </button>
              {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
                // Show pages around current
                const start = Math.max(0, Math.min(currentPage - 3, totalPages - 7))
                const pageNum = start + i
                if (pageNum >= totalPages) return null
                return (
                  <button
                    key={pageNum}
                    onClick={() => setCurrentPage(pageNum)}
                    style={{
                      width: 28, height: 28, borderRadius: 4,
                      background: pageNum === currentPage ? COLORS.accent : 'transparent',
                      color: pageNum === currentPage ? '#fff' : COLORS.textMuted,
                      border: pageNum === currentPage ? 'none' : `1px solid ${COLORS.border}`,
                      cursor: 'pointer', fontSize: 11,
                      fontFamily: "'Montserrat', sans-serif",
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}
                  >
                    {pageNum + 1}
                  </button>
                )
              })}
              <button
                onClick={() => setCurrentPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={currentPage >= totalPages - 1}
                style={{
                  padding: '6px 12px', borderRadius: 6,
                  background: currentPage >= totalPages - 1 ? COLORS.bg : COLORS.surface,
                  color: currentPage >= totalPages - 1 ? COLORS.textMuted : COLORS.text,
                  border: `1px solid ${COLORS.border}`,
                  cursor: currentPage >= totalPages - 1 ? 'default' : 'pointer',
                  fontSize: 11, fontFamily: "'Montserrat', sans-serif",
                }}
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}