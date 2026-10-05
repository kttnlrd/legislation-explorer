import React, { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { shortActName, rulingSlug, actTitleName, normalizeCaseCitation } from '../utils/display'

const PAGE_SIZE = 25

// Snippets are FTS5 snippet() output: plain text with each match wrapped in
// <mark>. Render those matches as React <mark> elements and everything else as
// text — never as raw HTML (L9). Anything that looks like a tag is shown literally.
const SNIPPET_MARK_RE = /(<mark>[\s\S]*?<\/mark>)/

function renderSnippet(snippet: string) {
  return snippet.split(SNIPPET_MARK_RE).map((part, i) => {
    if (i % 2 === 1) {
      const inner = part.replace(/^<mark>/, '').replace(/<\/mark>$/, '')
      return <mark key={i}>{inner}</mark>
    }
    return <React.Fragment key={i}>{part}</React.Fragment>
  })
}

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
  outcome?: string
  qa?: { q: string; a: string }[]
}

interface SearchPanelProps {
  acts: { id: string; name: string }[]
  onNavigate: (act: string, section: string) => void
  isMobile: boolean
  onResultsChange?: (count: number) => void
}

// Practice areas → backend search scope + the sources searched within each.
// Row 1 of the search filter is the area (maps to a backend `scope`); row 2 is
// the togglable sources for the selected area (narrows to a single `act`).
const PRACTICE_AREAS: { label: string; scope: string; ids: string[] }[] = [
  { label: 'Tax', scope: 'au-tax', ids: ['itaa-1997','itaa-1936','gst-1999','fbt-1986','sis-1993','taa-1953','tax-cases','rulings','private-rulings','treaties'] },
  { label: 'Corporate', scope: 'corporate-asic', ids: ['corporations-act-2001','regulatory-guides'] },
  { label: 'Bankruptcy', scope: 'bankruptcy', ids: ['bankruptcy-act-1966','afsa-guides'] },
  { label: 'AML/CTF', scope: 'aml-ctf', ids: ['aml-ctf-2006','aml-ctf-rules-2007'] },
  { label: 'NZ Tax', scope: 'nz-tax', ids: ['nz-it-2007'] },
]

// Result-type chips per practice-area scope. Only au-tax has public/private
// rulings; corporate/bankruptcy surface legislation + guides + cases. Keys are
// the backend `type` filter values.
const TYPE_CHIPS: Record<string, { key: string; label: string }[]> = {
  'au-tax': [
    { key: '', label: 'All' },
    { key: 'section', label: 'Sections' },
    { key: 'ruling', label: 'Public rulings' },
    { key: 'private_ruling', label: 'Private rulings' },
    { key: 'case', label: 'Cases' },
  ],
  'corporate-asic': [
    { key: '', label: 'All' },
    { key: 'section', label: 'Sections' },
    { key: 'regulatory_guide', label: 'Guides (RGs)' },
    { key: 'case', label: 'Cases' },
  ],
  'bankruptcy': [
    { key: '', label: 'All' },
    { key: 'section', label: 'Sections' },
    { key: 'afsa_guide', label: 'Guides' },
    { key: 'case', label: 'Cases' },
  ],
  'aml-ctf': [
    { key: '', label: 'All' },
    { key: 'section', label: 'Sections' },
  ],
  'nz-tax': [
    { key: '', label: 'All' },
    { key: 'section', label: 'Sections' },
  ],
}

export default function SearchPanel({ acts, onNavigate, isMobile, onResultsChange }: SearchPanelProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<FlatResult[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [unfilteredResults, setUnfilteredResults] = useState<FlatResult[]>([])
  const [filterOpen, setFilterOpen] = useState(false)
  const [sortMode, setSortMode] = useState<'bestmatch' | 'bysection' | 'byact'>('bestmatch')
  const [loading, setLoading] = useState(false)
  const [hasSearched, setHasSearched] = useState(false)
  const [selectedActs, setSelectedActs] = useState<Set<string>>(new Set())
  const [selectedArea, setSelectedArea] = useState<string>(PRACTICE_AREAS[0].label)
  const [currentPage, setCurrentPage] = useState(0)
  const [typeFilter, setTypeFilter] = useState<string>('')
  const [operator, setOperator] = useState<'AND' | 'OR'>('AND')
  const [rtype, setRtype] = useState<string>('')
  const [outcome, setOutcome] = useState<string>('')
  // The term the current results were fetched for (header shows it even while the box is edited)
  const [searchedTerm, setSearchedTerm] = useState('')
  const firstRun = useRef(true)
  // Live autocomplete: top-5 matches shown inline in the main results area while typing.
  const [suggestions, setSuggestions] = useState<FlatResult[]>([])
  const suggestSeq = useRef(0)

  const activeArea = PRACTICE_AREAS.find(a => a.label === selectedArea) || PRACTICE_AREAS[0]
  const activeAreaActs = acts.filter(a => activeArea.ids.includes(a.id))

  // Re-run the search when the practice-area slicer changes (skip the mount)
  useEffect(() => {
    if (firstRun.current) { firstRun.current = false; return }
    if (query.trim()) doSearch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedActs, selectedArea])

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

  // Live autocomplete (CDN-0099): ≥2 chars, 250 ms debounce, top-5 matches rendered
  // inline in the main results area — not a dropdown. Committing (Enter / Pounce)
  // runs the full search and replaces these.
  useEffect(() => {
    const term = query.trim()
    const seq = ++suggestSeq.current
    if (term.length < 2) { setSuggestions([]); return }
    const t = setTimeout(async () => {
      try {
        const data = await api.suggest(term, 5)
        if (seq !== suggestSeq.current) return
        setSuggestions((data.suggestions || []).map((r: any) => ({
          act: r.act || '',
          act_name: '',
          section: r.section || '',
          title: r.title || '',
          headline: '',
          match_type: '',
          score: 0,
          type: r.type || 'section',
        })))
      } catch {
        if (seq === suggestSeq.current) setSuggestions([])
      }
    }, 250)
    return () => clearTimeout(t)
  }, [query])

  const doSearch = async (q?: string, filterOverride?: string) => {
    const term = (q || query).trim()
    if (!term) return

    setLoading(true)
    setHasSearched(true)
    setSearchedTerm(term)
    try {
      // Keep the query in the URL so direct loads / back-nav restore it
      window.history.replaceState(null, '', '/search?q=' + encodeURIComponent(term))
      const activeFilter = filterOverride !== undefined ? filterOverride : typeFilter
      const activeRtype = activeFilter === 'ruling' ? (rtype || undefined) : undefined
      const activeOutcome = activeFilter === 'private_ruling' ? (outcome || undefined) : undefined
      const singleAct = selectedActs.size === 1 ? [...selectedActs][0] : undefined
      if (sortMode === 'bestmatch') {
        const data = await api.searchHybrid(term, activeFilter || undefined, 200, {
          operator,
          rtype: activeRtype,
          outcome: activeOutcome,
          act: singleAct,
          scope: activeArea.scope,
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
          outcome: r.outcome || '',
          qa: r.qa || undefined,
        }))
        setUnfilteredResults(allResults)
        setTotalCount(typeof data.total === 'number' ? data.total : allResults.length)
        if (selectedActs.size > 0) {
          setResults(allResults.filter(r => selectedActs.has(r.act)))
        } else {
          setResults(allResults)
        }
      } else {
        // Per-act search, scoped to the selected area (or narrowed chips)
        const targets = selectedActs.size > 0
          ? acts.filter(a => selectedActs.has(a.id))
          : acts.filter(a => activeArea.ids.includes(a.id))
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
    } catch { setUnfilteredResults([]); setResults([]) }
    setLoading(false)
    setCurrentPage(0)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      doSearch()
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

  // Canonical href for a result row, mirroring handleSelect's act resolution,
  // so the row can render as a real <Link> (F-15).
  const hrefForResult = (r: FlatResult): string | null => {
    if (!r.section) return null
    const targetAct = r.type === 'case' ? 'tax-cases' : r.act
    if (targetAct === 'tax-cases') return `/tax-cases/${encodeURIComponent(r.section)}`
    if (targetAct === 'private-rulings') return `/private-rulings/${encodeURIComponent(r.section)}`
    if (targetAct === 'rulings') return `/rulings/${rulingSlug(r.section)}`
    return `/${targetAct}/${r.section}`
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

  // Document-type badge: label + lk-badge modifier for every result type we render.
  const badgeFor = (r: FlatResult): { label: string; cls: string } => {
    if (r.type === 'case' || r.act === 'tax-cases') return { label: 'Case', cls: 'case' }
    if (r.type === 'private_ruling' || r.act === 'private-rulings') return { label: 'Private ruling', cls: 'private-ruling' }
    if (r.type === 'ruling' || r.act === 'rulings') return { label: 'Ruling', cls: 'ruling' }
    if (r.act === 'treaties' || /treaty|convention|double tax/i.test(r.act_name)) return { label: 'Treaty', cls: 'treaty' }
    if (r.act === 'regulatory-guides') return { label: 'Guide', cls: 'act' }
    if (r.act === 'afsa-guides') return { label: 'AFSA', cls: 'act' }
    return { label: 'Section', cls: 'section' }
  }

  // Answer-pill classification for private-ruling Q&A. Collapses OCR spacing
  // and punctuation ("Ye s" → "Yes", ": No" → "No") so classification is robust
  // to ingest artefacts; "not…" stays Qualified.
  const answerPill = (a: string): { label: string; cls: string } => {
    const v = (a || '').toLowerCase().replace(/[^a-z]/g, '')
    if (v.startsWith('yes')) return { label: 'Yes', cls: 'yes' }
    if (v.startsWith('no') && !v.startsWith('not')) return { label: 'No', cls: 'no' }
    return { label: 'Qualified', cls: 'qualified' }
  }
  const truncate = (s: string, n: number): string =>
    s.length > n ? s.slice(0, n - 1).trimEnd() + '…' : s

  const chevronSvg = (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M6 9l6 6 6-6" />
    </svg>
  )

  const filterButtonSvg = (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 6h16M7 12h10M10 18h4" />
    </svg>
  )

  const anyQueryFilter = !!(typeFilter || rtype || outcome || selectedActs.size > 0)
  const sourcesEmptied = !loading && hasSearched && results.length === 0 && unfilteredResults.length > 0
    && selectedActs.size > 0 && !unfilteredResults.some(r => selectedActs.has(r.act))
  const showTypeTabs = !loading && hasSearched && (results.length > 0 || typeFilter !== '')
  // Live autocomplete is "live" while the box differs from the committed term.
  const isSuggesting = !loading && suggestions.length > 0 && query.trim() !== searchedTerm

  // Shared result-card renderer (used for both live suggestions and full results).
  const renderCard = (r: FlatResult, key: string) => {
    const badge = badgeFor(r)
    const isCase = badge.cls === 'case'
    const isPrivate = badge.cls === 'private-ruling'
    const isSection = badge.cls === 'section'

    // Title — identify the document first, then the heading.
    let title: string
    if (isCase) {
      title = r.title || normalizeCaseCitation(r.section) || ''
    } else if (isPrivate) {
      // "Private ruling 1051476678819 — Fringe benefits tax" → "1051476678819: Fringe benefits tax"
      let t = (r.title || r.section || '')
      t = t.replace(/^Private ruling\s+\S+\s*[—–-]\s*/i, '')
      t = t.replace(/\s*[—–]\s*/g, ': ')
      title = t.trim() || r.section || ''
    } else if (isSection && r.section) {
      const heading = r.title && r.title !== r.section ? r.title : ''
      title = `s ${r.section} ${actTitleName(r.act)}${heading ? `: ${heading}` : ''}`
    } else {
      title = r.title || ''
    }

    const resultHref = hrefForResult(r)
    const RowTag: any = resultHref ? Link : 'div'
    const rowProps: any = resultHref
      ? {
          to: resultHref,
          onClick: (e: React.MouseEvent) => {
            if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return
            e.preventDefault()
            handleSelect(r)
          },
        }
      : {
          onClick: () => handleSelect(r),
          role: 'button',
          tabIndex: 0,
          onKeyDown: (e: React.KeyboardEvent) => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleSelect(r) }
          },
        }

    const qaItems = isPrivate && r.qa && r.qa.length ? r.qa : []
    const qaShown = qaItems.slice(0, 3)
    const qaMore = qaItems.length - qaShown.length

    return (
      <RowTag key={key} className="lk-result-card" {...rowProps}>
        <div className="lk-result-card__head">
          <span className={`lk-badge lk-badge--${badge.cls}`}>{badge.label}</span>
          <span className="lk-result-card__title">{title}</span>
          {isPrivate && r.outcome && (
            <span
              className={`lk-outcome lk-outcome--${r.outcome === 'yes' ? 'yes' : r.outcome === 'no' ? 'no' : 'mixed'}`}
              title={r.outcome === 'mixed' ? 'Some answers favourable, some not' : undefined}
            >
              {r.outcome === 'yes' ? 'Yes' : r.outcome === 'no' ? 'No' : 'Mixed'}
            </span>
          )}
        </div>
        {!isPrivate && r.snippet && (
          <div className="lk-result-card__snippet">{renderSnippet(r.snippet)}</div>
        )}
        {isPrivate && qaShown.length > 0 && (
          <div className="lk-result-card__qa">
            {qaShown.map((qa, qi) => (
              <div key={qi} className="lk-result-card__qa-row">
                <span className="lk-result-card__q">{truncate(qa.q, 120)}</span>
                <span className={`lk-answer lk-answer--${answerPill(qa.a).cls}`}>{answerPill(qa.a).label}</span>
              </div>
            ))}
            {qaMore > 0 && <span className="lk-result-card__qa-more">+{qaMore} more</span>}
          </div>
        )}
      </RowTag>
    )
  }

  const filtersAside = filterOpen && (
    <aside className="lk-filters" aria-label="Search filters">
      <span className="lk-filters__caption">Filters</span>
      <div className="lk-filters__field">
        <label htmlFor="lk-fmatch" className="lk-filters__label">Match</label>
        <select
          id="lk-fmatch"
          className="lk-filters__select"
          value={operator}
          onChange={e => setOperator(e.target.value as 'AND' | 'OR')}
        >
          <option value="AND">All terms (AND)</option>
          <option value="OR">Any term (OR)</option>
        </select>
      </div>
      <div className="lk-filters__field">
        <label htmlFor="lk-fsort" className="lk-filters__label">Sort</label>
        <select
          id="lk-fsort"
          className="lk-filters__select"
          value={sortMode}
          onChange={e => setSortMode(e.target.value as 'bestmatch' | 'bysection' | 'byact')}
        >
          <option value="bestmatch">Best match</option>
          <option value="bysection">By section</option>
          <option value="byact">By act</option>
        </select>
      </div>
    </aside>
  )

  return (
    <div className={'lk-search' + (isMobile ? ' lk-search--mobile' : '')}>
      {/* Search input row */}
      <div className="lk-search__bar">
        <div className="lk-search__form" role="search">
          <svg className="lk-search__icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>
          </svg>
          <label htmlFor="lk-search-q" className="lk-sr-only">Search legislation</label>
          <input
            id="lk-search-q"
            className="lk-search__input"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search legislation, rulings, cases…"
            autoComplete="off"
          />
          <button
            type="button"
            className="lk-search__submit"
            onClick={() => doSearch()}
            onMouseDown={e => e.preventDefault()}
          >
            Pounce
          </button>
        </div>
        <button
          type="button"
          className="lk-search__filters-btn"
          onClick={() => setFilterOpen(!filterOpen)}
          title="Filters"
          aria-label={isMobile ? 'Filters' : undefined}
          aria-expanded={filterOpen}
        >
          {filterButtonSvg}
          {!isMobile && <span className="lk-search__filters-label">Filters</span>}
        </button>
      </div>

      {/* Practice-area selector: row 1 = areas, row 2 = sources for the area */}
      <div className="lk-practice" role="group" aria-label="Practice areas">
        <div className="lk-practice__areas">
          {PRACTICE_AREAS.map(a => (
            <button
              key={a.label}
              type="button"
              className="lk-practice__area"
              aria-pressed={selectedArea === a.label}
              onClick={() => { setSelectedArea(a.label); setSelectedActs(new Set()) }}
            >
              {a.label}
            </button>
          ))}
        </div>
        <div className="lk-practice__items" role="group" aria-label={`${selectedArea} sources`}>
          {activeAreaActs.map(a => (
            <button
              key={a.id}
              type="button"
              className="lk-practice__item"
              aria-pressed={selectedActs.has(a.id)}
              onClick={() => toggleAct(a.id)}
            >
              {shortActName(a.id)}
            </button>
          ))}
        </div>
      </div>

      {/* Results header */}
      {results.length > 0 && !loading && (
        <div className="lk-search-header">
          <h1 className="lk-search-header__count">{totalCount > results.length ? `${results.length}+` : results.length} sniffed out</h1>
          {searchedTerm && (
            <span className="lk-search-header__query">for &#8220;{searchedTerm}&#8221;</span>
          )}
          {totalPages > 1 && (
            <span className="lk-search-header__page">Page {currentPage + 1} of {totalPages}</span>
          )}
        </div>
      )}

      <div className="lk-search__body">
        <div className="lk-search__main">
          {/* Type filter tabs */}
          {showTypeTabs && (
            <div className="lk-chips" role="group" aria-label="Result type">
              {(TYPE_CHIPS[activeArea.scope] || TYPE_CHIPS['au-tax']).map(t => (
                <button
                  key={t.key}
                  type="button"
                  className="lk-chip"
                  aria-pressed={typeFilter === t.key}
                  onClick={() => { setTypeFilter(t.key); setCurrentPage(0); doSearch(undefined, t.key) }}
                >
                  {t.label}
                </button>
              ))}
            </div>
          )}
          {/* Ruling-series chips */}
          {showTypeTabs && typeFilter === 'ruling' && (
            <div className="lk-chips lk-chips--sub" role="group" aria-label="Ruling series">
              {[
                { key: '', label: 'All' },
                { key: 'TR', label: 'TR' },
                { key: 'TD', label: 'TD' },
                { key: 'AID', label: 'ATOID' },
                { key: 'PS LA', label: 'PS LA' },
                { key: 'GSTR', label: 'GSTR' },
                { key: 'PCG', label: 'PCG' },
                { key: 'CR', label: 'CR' },
                { key: 'IT', label: 'IT' },
                { key: 'TA', label: 'TA' },
              ].map(c => (
                <button
                  key={c.key}
                  type="button"
                  className="lk-chip"
                  aria-pressed={rtype === c.key}
                  onClick={() => { setRtype(c.key); setCurrentPage(0); doSearch(undefined, 'ruling') }}
                >
                  {c.label}
                </button>
              ))}
            </div>
          )}
          {/* Private-ruling outcome chips */}
          {showTypeTabs && typeFilter === 'private_ruling' && (
            <div className="lk-chips lk-chips--sub" role="group" aria-label="Private ruling outcome">
              {[
                { key: '', label: 'Any outcome' },
                { key: 'yes', label: '✓ ATO said Yes' },
                { key: 'no', label: '✗ ATO said No' },
                { key: 'mixed', label: 'Mixed' },
              ].map(c => (
                <button
                  key={c.key}
                  type="button"
                  className="lk-chip"
                  aria-pressed={outcome === c.key}
                  onClick={() => { setOutcome(c.key); setCurrentPage(0); doSearch(undefined, 'private_ruling') }}
                >
                  {c.label}
                </button>
              ))}
            </div>
          )}

          {loading && (
            <div className="lk-search-loading" role="status">
              <img src="/favicon.png" alt="" />
              Sniffing through the ITAA…
            </div>
          )}
          {isSuggesting && (
            <div className="lk-results">
              <div className="lk-search-header">
                <h1 className="lk-search-header__count">{suggestions.length} quick match{suggestions.length === 1 ? '' : 'es'}</h1>
                <span className="lk-search-header__query">keep typing, or press Enter to search everything</span>
              </div>
              {suggestions.map((r, i) => renderCard(r, `sug-${r.act}-${r.section}-${i}`))}
            </div>
          )}
          {!loading && !isSuggesting && hasSearched && results.length === 0 && unfilteredResults.length === 0 && (
            <div className="lk-empty-state" role="status">
              <p className="lk-empty-state__title">Nothing sniffed out.</p>
              <span>{anyQueryFilter ? 'Try fewer filters or different words.' : 'Try different words.'}</span>
            </div>
          )}
          {!isSuggesting && sourcesEmptied && (
            <div className="lk-empty-state" role="status">
              <p className="lk-empty-state__title">Nothing sniffed out.</p>
              <span>No results in the selected sources. Tick more sources or clear them.</span>
            </div>
          )}

          {!isSuggesting && results.length > 0 && !loading && (
            <>
              {/* Results list */}
              <div className="lk-results">
                {pageResults.map((r, i) => renderCard(r, `${r.act}-${r.section}-${pageStart + i}`))}
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <nav className="lk-pager" aria-label="Results pages">
                  <button
                    type="button"
                    className="lk-pager__btn"
                    onClick={() => setCurrentPage(p => Math.max(0, p - 1))}
                    disabled={currentPage === 0}
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
                        type="button"
                        className="lk-pager__btn"
                        aria-current={pageNum === currentPage ? 'page' : undefined}
                        onClick={() => setCurrentPage(pageNum)}
                      >
                        {pageNum + 1}
                      </button>
                    )
                  })}
                  <button
                    type="button"
                    className="lk-pager__btn"
                    onClick={() => setCurrentPage(p => Math.min(totalPages - 1, p + 1))}
                    disabled={currentPage >= totalPages - 1}
                  >
                    Next →
                  </button>
                </nav>
              )}
            </>
          )}
        </div>
        {filtersAside}
      </div>
    </div>
  )
}
