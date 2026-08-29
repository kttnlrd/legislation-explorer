import React, { useEffect, useState, useRef, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import { api } from './api'
import { Tree, PinItem, COLORS } from './components/common/types'
import { TreeNode, findExpandedIds } from './components/TreeNode'
import MCPModal from './components/MCPModal'
import KeyboardShortcuts from './components/KeyboardShortcuts'
import PinnedTabs from './components/PinnedTabs'
import SmartLinkPanel from './components/SmartLinkPanel'
import DefinitionPopover from './components/DefinitionPopover'
import DefinitionsBrowser from './components/DefinitionsBrowser'
import SectionContent from './components/SectionContent'
import RulingContent from './components/RulingContent'
import PrivateRulingsBrowser from './components/PrivateRulingsBrowser'
import PrivateRulingContent from './components/PrivateRulingContent'
import RegulatoryGuideContent from './components/RegulatoryGuideContent'
import TaxCaseContent from './components/TaxCaseContent'
import SettingsPanel from './components/SettingsPanel'
import GraphModal from './components/GraphModal'
import MapView from './components/MapView'
import IssuesModal from './components/IssuesModal'
import SearchPanel from './components/SearchPanel'
import TreatyContent from './components/TreatyContent'
import { ThemeProvider } from './ThemeContext'
import { shortActName } from './utils/display'

// Domain groupings for the act picker
// All individual treaty country slugs — kept for isTreaty() / routing
const TREATY_SLUGS = [
  'argentina', 'austria', 'belgium', 'canada', 'chile', 'china', 'czech-republic',
  'denmark', 'fiji', 'finland', 'france', 'hungary', 'iceland', 'india', 'indonesia',
  'ireland', 'israel', 'italy', 'kiribati', 'korea', 'malaysia', 'malta', 'mexico',
  'netherlands', 'new-zealand', 'norway', 'papua-new-guinea', 'philippines', 'poland',
  'romania', 'russia', 'singapore', 'slovakia', 'south-africa', 'spain', 'sri-lanka',
  'sweden', 'taipei', 'thailand', 'turkey', 'usa', 'vietnam',
  'treaties',  // meta-act: shows country list in the tree
]
const TREATY_SET = new Set(TREATY_SLUGS)
const isTreaty = (id: string) => TREATY_SET.has(id) && id !== 'treaties'

const DOMAINS: { label: string; ids: string[] }[] = [
  { label: 'Australian Tax', ids: ['itaa-1997', 'itaa-1936', 'gst-1999', 'taa-1953', 'fbt-1986', 'sis-1993', 'master-tax-guide', 'master-tax-examples', 'master-gst-guide', 'rulings', 'tax-cases', 'private-rulings'] },
  { label: 'International Tax', ids: ['treaties'] },
  { label: 'New Zealand Tax', ids: ['nz-it-2007'] },
  { label: 'Corporate Law', ids: ['corporations-act-2001', 'regulatory-guides'] },
  { label: 'Corporate Insolvency', ids: ['insolvency-keays'] },
  { label: 'AML/CTF', ids: ['aml-ctf-2006', 'aml-ctf-rules-2007'] },
  { label: 'System', ids: ['spec'] },
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const DICT_SECTIONS = new Set(['995-1', '195-1', '6'])

function isDefinitionLink(href?: string) {
  if (!href) return false
  const m = href.match(/\/([a-z0-9-]+)\/s([^#]+)(?:#(.+))?/)
  if (!m) return false
  return DICT_SECTIONS.has(m[2])
}

// ---------------------------------------------------------------------------
// Error boundary — a render-phase crash must never blank the whole screen
// ---------------------------------------------------------------------------
class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) { return { error } }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 40, fontFamily: "'Montserrat', sans-serif", color: COLORS.text, background: COLORS.bg, minHeight: '100vh' }}>
          <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 8 }}>Something went wrong</div>
          <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 16, fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>{this.state.error.message}</div>
          <button
            onClick={() => { this.setState({ error: null }); window.location.reload() }}
            style={{ padding: '6px 14px', borderRadius: 6, border: '1px solid ' + COLORS.border, background: COLORS.surface, color: COLORS.text, cursor: 'pointer', fontFamily: "'Montserrat', sans-serif" }}
          >Reload</button>
        </div>
      )
    }
    return this.props.children
  }
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  const [act, setAct] = useState('itaa-1997')
  const [tree, setTree] = useState<Tree | null>(null)
  const [acts, setActs] = useState<any[]>([])
  const [activeSection, setActiveSection] = useState('')
  const [sectionData, setSectionData] = useState<any>(null)
  const [search, setSearch] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [error, setError] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const [browsingAct, setBrowsingAct] = useState(false)

  // Sidebar width with localStorage persistence
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    try {
      const saved = localStorage.getItem('legislation-sidebar-width')
      return saved ? Math.max(280, Math.min(600, parseInt(saved, 10))) : 400
    } catch { return 400 }
  })
  const [isResizing, setIsResizing] = useState(false)

  const [activeRuling, setActiveRuling] = useState<string | null>(null)
  const [rulingData, setRulingData] = useState<any>(null)
  const [activePrivateRuling, setActivePrivateRuling] = useState<string | null>(null)
  const [privateRulingData, setPrivateRulingData] = useState<any>(null)
  const [privateRulingsYear, setPrivateRulingsYear] = useState<number | 'undated' | null>(null)
  // Lazy month → ruling sections injected into the sidebar tree for private rulings
  const [prMonthSections, setPrMonthSections] = useState<Record<string, { id: string; title: string; path: string }[]>>({})
  const [prExpanded, setPrExpanded] = useState<Set<string>>(new Set())
  const [commentaryData, setCommentaryData] = useState<any>(null)
  const [casesData, setCasesData] = useState<any>(null)
  const [rulingsForSectionData, setRulingsForSectionData] = useState<any>(null)

  const [mcpOpen, setMcpOpen] = useState(false)
  const [searchPage, setSearchPage] = useState(false)
  const [showShortcuts, setShowShortcuts] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [searchResultsCount, setSearchResultsCount] = useState(0)
  const pickerRef = useRef<HTMLDivElement>(null)
  const [pins, setPins] = useState<PinItem[]>(() => {
    try { return JSON.parse(localStorage.getItem('legislation-pins') || '[]') }
    catch { return [] }
  })

  const [appInfo, setAppInfo] = useState<any>(null)
  const [user, setUser] = useState<any>(null)
  const [authLoading, setAuthLoading] = useState(true)

  useEffect(() => {
    api.info().then(setAppInfo).catch(() => {})
  }, [])

  useEffect(() => {
    fetch('/auth/me')
      .then(r => r.ok ? r.json() : null)
      .then(u => { setUser(u); setAuthLoading(false) })
      .catch(() => { setUser(null); setAuthLoading(false) })
  }, [])

  const [settingsOpen, setSettingsOpen] = useState(false)
  const [issuesOpen, setIssuesOpen] = useState(false)
  const [changelogOpen, setChangelogOpen] = useState(false)
  const [graphOpen, setGraphOpen] = useState<{
    type: 'section' | 'ruling' | 'case' | 'private-ruling'
    act?: string
    section?: string
    citation?: string
    label: string
  } | null>(null)
  const [activeMap, setActiveMap] = useState<string | null>(null)
  // Definitions browser: null = off, '' = act picker, 'itaa-1936' = act view
  const [activeDefinitions, setActiveDefinitions] = useState<string | null>(null)
  const [mapsList, setMapsList] = useState<any[] | null>(null)
  const settingsRef = useRef<HTMLDivElement>(null)
  const [selectedRulingSection, setSelectedRulingSection] = useState<string | null>(null)

  // Pins
  const togglePin = () => {
    if (!activeSection || !sectionData) return
    const newPin = { act, section: activeSection, title: sectionData.frontmatter?.title || activeSection }
    const exists = pins.some(p => p.act === act && p.section === activeSection)
    const nextPins = exists
      ? pins.filter(p => !(p.act === act && p.section === activeSection))
      : [...pins, newPin]
    setPins(nextPins)
    localStorage.setItem('legislation-pins', JSON.stringify(nextPins))
  }
  const unpin = (pin: PinItem) => {
    const nextPins = pins.filter(p => !(p.act === pin.act && p.section === pin.section))
    setPins(nextPins)
    localStorage.setItem('legislation-pins', JSON.stringify(nextPins))
  }
  const isPinned = pins.some(p => p.act === act && p.section === activeSection)

  // Definition link popover
  const renderLink = (href?: string, children?: React.ReactNode) => {
    if (!isDefinitionLink(href)) return null
    const m = href!.match(/\/([a-z0-9-]+)\/s([^#]+)(?:#(.+))?/)
    const linkAct = m ? m[1] : act
    return (
      <DefinitionPopover
        act={linkAct}
        href={href}
        onNavigate={(section, anchor) => {
          if (linkAct === act) {
            setActiveSection(section)
            setActiveRuling(null)
            if (anchor) {
              setTimeout(() => {
                const el = document.getElementById(anchor)
                if (el) el.scrollIntoView({ behavior: 'smooth' })
              }, 150)
            }
          }
        }}
      >
        {children}
      </DefinitionPopover>
    )
  }

  // Navigation wrappers for child components
  const onNavigate = (targetAct: string, section: string, anchor?: string) => {
    setAct(targetAct)
    setActiveSection(section)
    setActiveRuling(null)
    setActivePrivateRuling(null)
    setSearchPage(false)
    if (anchor) {
      setTimeout(() => {
        const el = document.getElementById(anchor)
        if (el) el.scrollIntoView({ behavior: 'smooth' })
      }, 150)
    }
  }
  const onNavigateRuling = (citation: string) => {
    setActiveRuling(citation)
    setActiveSection('')
    setActivePrivateRuling(null)
    setSearchPage(false)
  }
  const onNavigateCase = (citation: string) => {
    window.history.pushState(null, '', `/tax-cases/${encodeURIComponent(citation)}`)
    setAct('tax-cases')
    setActiveSection(citation)
    setActiveRuling(null)
    setActivePrivateRuling(null)
    setSearchPage(false)
    setActiveMap(null)
  }

  // Close picker on click outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node))
        setPickerOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === '?' && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault()
        setShowShortcuts(s => !s)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // Mobile detection
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768)
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  // Load acts list
  useEffect(() => {
    api.acts().then(data => setActs(data)).catch(() => setActs([]))
  }, [])

  // Load procedural maps list (for the act picker domain)
  useEffect(() => {
    fetch('/api/maps')
      .then(r => (r.ok ? r.json() : []))
      .then(setMapsList)
      .catch(() => setMapsList([]))
  }, [])

  // Load tree when act changes — use ref to avoid stale-race from default act
  const treeGenRef = useRef(0)
  useEffect(() => {
    const gen = ++treeGenRef.current
    setTree(null)

    // Treaties hub: nested country -> article tree (countries expandable)
    if (act === 'treaties') {
      api.treatyFullTree().then(data => {
        if (gen !== treeGenRef.current) return
        setTree({
          act: 'treaties',
          parts: [{
            id: 'treaties',
            title: 'Double Tax Agreements',
            divisions: (data.countries || []).map((c: any) => ({
              id: c.slug,
              title: c.treaty,
              subdivisions: [],
              sections: (c.articles || []).map((a: any) => ({
                id: `${c.slug}/${a.article}`,
                title: a.title,
                path: a.slug,
              })),
            })),
            sections: [],
          }],
        } as Tree)
        setError('')
      }).catch(e => {
        if (gen === treeGenRef.current) setError(e.message)
      })
      setDrawerOpen(false)
      return
    }

    // Maps hub: handled by its own effect (needs mapsList)
    if (act === 'maps') {
      setTree(null)
      setDrawerOpen(false)
      return
    }

    const load = isTreaty(act) ? api.treatyTree(act) : api.tree(act)
    load.then(data => {
      if (gen !== treeGenRef.current) return
      if (isTreaty(act)) {
        setTree({
          act,
          parts: [{
            id: act,
            title: data.treaty,
            divisions: [],
            sections: (data.articles || []).map((a: any) => ({ id: String(a.article), title: a.title, path: a.slug })),
          }],
        } as Tree)
      } else {
        setTree(data)
      }
      setError('')
    }).catch(e => {
      if (gen === treeGenRef.current) setError(e.message)
    })
    setDrawerOpen(false)
  }, [act])

  // -------------------------------------------------------------------------
  // Private rulings tree: year → month → lazy ruling list
  // -------------------------------------------------------------------------
  const PR_MONTH_RE = /^(\d{4})-(\d{1,2})$/
  const PR_MORE_RE = /^__more__:(.+):(\d+)$/
  const PR_PAGE = 200

  const loadPrivateRulingsMonth = (monthId: string, offset = 0) => {
    let req: Promise<any>
    if (monthId === 'undated-all') {
      req = api.privateRulingsUndated(PR_PAGE, offset)
    } else {
      const m = PR_MONTH_RE.exec(monthId)
      if (!m) return
      req = api.privateRulingsByMonth(Number(m[1]), Number(m[2]), PR_PAGE, offset)
    }
    req.then(d => {
      const rulings = d.rulings || []
      const sections = rulings.map((r: any) => ({
        id: r.authnum,
        title: `${r.name || 'Untitled ruling'} — EV/${String(r.authnum).slice(-6)}`,
        path: r.authnum,
      }))
      const total = d.total || 0
      const next = offset + rulings.length
      if (next < total) {
        const moreId = `__more__:${monthId}:${next}`
        sections.push({ id: moreId, title: `Load more (${(total - next).toLocaleString()} remaining)`, path: moreId })
      }
      setPrMonthSections(prev => {
        const existing = (prev[monthId] || []).filter(s => !s.id.startsWith('__more__:'))
        return { ...prev, [monthId]: [...existing, ...sections] }
      })
      setPrExpanded(prev => new Set(prev).add(monthId))
      setError('')
    }).catch(e => setError(e.message))
  }

  // Inject loaded month sections into the tree for rendering
  const treeForRender = useMemo(() => {
    if (act !== 'private-rulings' || !tree || Object.keys(prMonthSections).length === 0) return tree
    const clone: Tree = JSON.parse(JSON.stringify(tree))
    for (const part of clone.parts) {
      for (const div of (part as any).divisions || []) {
        for (const sub of (div as any).subdivisions || []) {
          if (prMonthSections[sub.id]) {
            (sub as any).sections = prMonthSections[sub.id]
          }
        }
      }
    }
    return clone
  }, [tree, prMonthSections, act])

  // Merge auto-expanded ancestors with manually expanded private-ruling months
  const expandedIds = useMemo(() => {
    const s = activeSection ? findExpandedIds(treeForRender, activeSection) : new Set<string>()
    prExpanded.forEach(x => s.add(x))
    return s
  }, [treeForRender, activeSection, prExpanded])

  const handleTreeSelect = (e: string) => {
    setSearchPage(false)
    if (act === 'maps') {
      setActiveSection(''); setActiveRuling(null); setSectionData(null); setActiveMap(e)
      window.history.pushState(null, '', `/maps/${e}`)
    } else if (act === 'treaties') {
      const s = e.indexOf('/')
      if (s > -1) { setAct(e.slice(0, s)); setActiveSection(e.slice(s + 1)) } else { setAct(e); setActiveSection('') }
    } else if (act === 'rulings') {
      setActiveRuling(e)
    } else if (act === 'private-rulings') {
      if (e.startsWith('__more__:')) {
        const mm = PR_MORE_RE.exec(e)
        if (mm) loadPrivateRulingsMonth(mm[1], Number(mm[2]))
      } else if (PR_MONTH_RE.test(e) || e === 'undated-all') {
        loadPrivateRulingsMonth(e)
      } else if (e === 'undated' || /^\d{4}$/.test(e)) {
        setPrivateRulingsYear(e === 'undated' ? 'undated' : Number(e))
        setActivePrivateRuling(null)
      } else {
        setActivePrivateRuling(e)
      }
      setActiveSection('')
    } else {
      setActiveSection(e)
    }
    if (isMobile) setDrawerOpen(false)
  }

  // Maps hub tree: act-grouped map list, same navigation pattern as any act
  useEffect(() => {
    if (act !== 'maps') return
    const MAP_ACT_LABELS: Record<string, string> = {
      'itaa-1997': 'Income Tax Assessment Act 1997',
      'itaa-1936': 'Income Tax Assessment Act 1936',
      'gst-1999': 'GST Act 1999',
      'taa-1953': 'Taxation Administration Act 1953',
      'fbt-1986': 'FBT Assessment Act 1986',
      'sis-1993': 'Superannuation Industry (Supervision) Act 1993',
    }
    const grouped = new Map<string, any[]>()
    for (const m of (mapsList || [])) {
      if (!grouped.has(m.act)) grouped.set(m.act, [])
      grouped.get(m.act)!.push(m)
    }
    setTree({
      act: 'maps',
      parts: [...grouped.entries()].map(([mapAct, ms]) => ({
        id: mapAct,
        title: MAP_ACT_LABELS[mapAct] || shortActName(mapAct),
        divisions: [],
        sections: ms.map(m => ({
          id: m.id,
          title: m.short ? (m.refs ? `${m.short} — ${m.refs}` : m.short) : m.title,
          path: m.id,
        })),
      })),
    } as Tree)
    setError('')
    setDrawerOpen(false)
  }, [act, mapsList])

  // Load section / ruling content
  useEffect(() => {
    if (!activeSection && !activeRuling && !activePrivateRuling) {
      setSectionData(null)
      setRulingData(null)
      setPrivateRulingData(null)
      setCommentaryData(null)
      setCasesData(null)
      setRulingsForSectionData(null)
      return
    }

    // Navigating into a section/ruling leaves the map page
    setActiveMap(null)

    if (activePrivateRuling) {
      api.privateRuling(activePrivateRuling)
        .then(data => { setPrivateRulingData(data); setError('') })
        .catch(e => { setPrivateRulingData(null); setError(e.message) })
      window.history.pushState(null, '', `/private-rulings/${activePrivateRuling}`)
    } else if (activeRuling) {
      api.ruling(activeRuling)
        .then(data => { setRulingData(data); setError('') })
        .catch(e => { setRulingData(null); setError(e.message) })
      window.history.pushState(null, '', `/rulings/${activeRuling}`)
    } else if (activeSection && isTreaty(act)) {
      api.treatyArticle(act, activeSection)
        .then(data => { setSectionData(data); setError('') })
        .catch(e => {
          if (e.message?.includes('404')) {
            setActiveSection('')
            setSectionData(null)
          } else {
            setError(e.message)
          }
        })
      window.history.pushState(null, '', `/${act}/${activeSection}`)
    } else if (activeSection) {
      api.section(act, activeSection)
        .then(data => { setSectionData(data); setError('') })
        .catch(e => {
          if (e.message?.includes('404')) {
            setActiveSection('')
            setSectionData(null)
          } else {
            setError(e.message)
          }
        })
      api.commentary(act, activeSection).then(setCommentaryData).catch(() => {})
      api.cases(act, activeSection).then(setCasesData).catch(() => {})
      api.rulings(act, activeSection).then(setRulingsForSectionData).catch(() => {})
      window.history.pushState(null, '', `/${act}/${activeSection}`)
    }
    if (isMobile) setDrawerOpen(false)
  }, [act, activeSection, activeRuling, activePrivateRuling, isMobile])

  // URL → state sync
  useEffect(() => {
    const handler = () => {
      // Map routes take priority: /maps/{id} and /maps (index)
      const mapMatch = window.location.pathname.match(/^\/maps\/(.+)$/)
      const mapsIndex = window.location.pathname === '/maps'
      const isSearch = window.location.pathname === '/search'
      // Definitions routes must match before sectionMatch/actOnlyMatch so
      // /definitions/itaa-1936 isn't swallowed by the generic matchers.
      const defsMatch = window.location.pathname.match(/^\/definitions(?:\/([a-z0-9-]+))?$/)
      const privateRulingMatch = window.location.pathname.match(/^\/private-rulings\/(.+)$/)
      const sectionMatch = window.location.pathname.match(/\/([a-z0-9-]+)\/(.+)/)
      const rulingMatch = window.location.pathname.match(/\/rulings\/(.+)/)
      const actOnlyMatch = window.location.pathname.match(/^\/([a-z0-9-]+)$/)

      if (!defsMatch) setActiveDefinitions(null)

      if (isSearch) {
        setActiveMap(null)
        setActiveSection('')
        setActiveRuling(null)
        setActivePrivateRuling(null)
        setSearchPage(true)
      } else if (defsMatch) {
        setActiveDefinitions(defsMatch[1] || '')
        setActiveMap(null)
        setActiveSection('')
        setActiveRuling(null)
        setActivePrivateRuling(null)
        setSearchPage(false)
      } else if (mapMatch) {
        setActiveMap(decodeURIComponent(mapMatch[1]))
        setActiveSection('')
        setActiveRuling(null)
      } else if (mapsIndex) {
        setActiveMap(null)
        setActiveSection('')
        setActiveRuling(null)
        setAct('maps')
        setBrowsingAct(true)
      } else if (privateRulingMatch) {
        setActiveMap(null)
        setAct('private-rulings')
        setActivePrivateRuling(decodeURIComponent(privateRulingMatch[1]))
        setActiveSection('')
        setActiveRuling(null)
        setBrowsingAct(true)
      } else if (rulingMatch) {
        setActiveMap(null)
        setAct('rulings')
        setActiveRuling(decodeURIComponent(rulingMatch[1]))
        setActiveSection('')
        setActivePrivateRuling(null)
      } else if (sectionMatch) {
        setActiveMap(null)
        setAct(sectionMatch[1])
        // Strip leading 's' prefix from section id for defense-in-depth (ROUTE-001)
        // Backend also strips this, but frontend-only entry points benefit too.
        const rawSection = sectionMatch[2]
        const cleanedSection = rawSection.replace(/^s(?=\d)/, '')
        setActiveSection(decodeURIComponent(cleanedSection))
        setActiveRuling(null)
        setActivePrivateRuling(null)
      } else if (actOnlyMatch) {
        setActiveMap(null)
        setAct(actOnlyMatch[1])
        setActiveSection('')
        setActiveRuling(null)
        setActivePrivateRuling(null)
        setBrowsingAct(true)
      } else {
        setActiveMap(null)
        setActiveSection('')
        setActiveRuling(null)
        setActivePrivateRuling(null)
      }
    }
    handler()
    window.addEventListener('popstate', handler)
    return () => window.removeEventListener('popstate', handler)
  }, [])

  // Leaving the definitions browser: any in-app navigation to a section,
  // ruling or map closes it (URL changes are handled by the popstate sync).
  useEffect(() => {
    if (activeDefinitions !== null && (activeSection || activeRuling || activePrivateRuling || activeMap)) {
      setActiveDefinitions(null)
    }
  }, [activeDefinitions, activeSection, activeRuling, activePrivateRuling, activeMap])

  // Resize handlers
  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!isResizing) return
      const newWidth = Math.max(280, Math.min(600, e.clientX))
      setSidebarWidth(newWidth)
      localStorage.setItem('legislation-sidebar-width', String(newWidth))
    }
    const onMouseUp = () => setIsResizing(false)
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [isResizing])

  const doSearch = async () => {
    if (!search.trim()) return
    const data = await api.search(search, act)
    setSearchResults(data.results)
  }

  if (error) return <div style={{ padding: 20, color: '#ef4444' }}>Error: {error}</div>
  if (!tree) return <div style={{ padding: 20, color: COLORS.textMuted }}>Loading...</div>

  const mobileSidebarWidth = isMobile ? Math.min(window.innerWidth * 0.85, 380) : sidebarWidth
  const hasContent = !!(activeSection || activeRuling || activePrivateRuling || browsingAct || activeMap || activeDefinitions !== null)

  return (
    <ErrorBoundary>
    <ThemeProvider>
      <style>{`
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: ${COLORS.border}; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: ${COLORS.textMuted}; }
        * { scrollbar-width: thin; scrollbar-color: ${COLORS.border} transparent; }
      `}</style>
      <div style={{ display: 'flex', height: '100vh', background: COLORS.bg }}>

      {/* Mobile close button — inside sidebar header (absolute positioned) */}
      {/* Mobile backdrop */}
      {isMobile && drawerOpen && (
        <div
          onClick={() => setDrawerOpen(false)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 90 }}
        />
      )}

      {/* Sidebar */}
      <div style={{
        width: mobileSidebarWidth,
        background: COLORS.surface,
        borderRight: `1px solid ${COLORS.border}`,
        display: 'flex', flexDirection: 'column',
        position: isMobile ? 'fixed' : 'relative',
        transform: isMobile
          ? (drawerOpen ? 'translateX(0)' : 'translateX(-101%)')
          : undefined,
        top: 0, bottom: 0, zIndex: 100,
        willChange: isMobile ? 'transform' : undefined,
        transition: isMobile ? 'transform 0.15s ease' : 'none',
      }}>
        {/* Sidebar header: act picker + mobile close button */}
        <div style={{ padding: isMobile ? '12px 14px' : '12px 14px', borderBottom: `1px solid ${COLORS.border}`, position: 'relative' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingRight: isMobile && drawerOpen ? 36 : 0 }}>
            {(() => {
              const currentLabel = shortActName(act)
              return (
                <div ref={pickerRef} style={{ position: 'relative' }}>
                  <button onClick={() => { setPickerOpen(!pickerOpen) }} style={{
                    width: '100%', padding: isMobile ? '8px 10px' : '6px 10px', borderRadius: 6,
                    background: COLORS.bg, color: COLORS.heading,
                    border: `1px solid ${COLORS.border}`, fontSize: 12,
                    fontFamily: "'Montserrat', sans-serif", cursor: 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 4,
                  }}>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>{currentLabel}</span>
                    <span style={{ fontSize: 9, opacity: 0.6 }}>{pickerOpen ? '▲' : '▼'}</span>
                  </button>
                  {pickerOpen && (
                    <div style={{
                      position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 201,
                      marginTop: 4, background: COLORS.surface,
                      border: `1px solid ${COLORS.border}`,
                      borderRadius: 8, padding: '6px 0', maxHeight: 'min(72vh, 560px)', overflow: 'auto',
                      boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                    }}>
                      {(acts.length > 0 ? acts : [{ id: 'itaa-1997', name: 'ITAA 1997' }, { id: 'itaa-1936', name: 'ITAA 1936' }, { id: 'corporations-act-2001', name: 'Corporations Act 2001' }, { id: 'regulatory-guides', name: 'ASIC Regulatory Guides' }]).length > 0 ? (() => {
                      const actList = (acts.length > 0 ? acts : [{ id: 'itaa-1997', name: 'ITAA 1997' }, { id: 'itaa-1936', name: 'ITAA 1936' }, { id: 'corporations-act-2001', name: 'Corporations Act 2001' }, { id: 'regulatory-guides', name: 'ASIC Regulatory Guides' }])
                      const allActs = actList
                      const actById = Object.fromEntries(allActs.map(a => [a.id, a]))
                      return DOMAINS.map(domain => {
                        const domainActs = domain.ids.filter(id => actById[id]).map(id => actById[id])
                        if (domainActs.length === 0) return null
                        return (
                          <div key={domain.label}>
                            <div style={{ fontSize: 10, fontWeight: 600, color: COLORS.textMuted, padding: '4px 12px 2px', textTransform: 'uppercase', letterSpacing: 0.5, fontFamily: "'Montserrat', sans-serif" }}>{domain.label}</div>
                            {domainActs.map(a => (
                              <button key={a.id} onClick={() => { setPickerOpen(false); setAct(a.id); setActiveSection(''); setActiveRuling(null); setActivePrivateRuling(null); setSearchPage(false); setSectionData(null); setActiveMap(null); setBrowsingAct(true); window.history.pushState(null, '', `/${a.id}`); if (isMobile) setDrawerOpen(false) }} style={{
                                display: 'block', width: '100%', padding: '6px 12px',
                                background: 'transparent', border: 'none',
                                color: act === a.id ? COLORS.accent : COLORS.text,
                                fontSize: 12, cursor: 'pointer',
                                fontFamily: "'Montserrat', sans-serif", textAlign: 'left',
                              }}
                                onMouseEnter={e => e.currentTarget.style.background = COLORS.bg}
                                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                              >{shortActName(a.id)}</button>
                            ))}
                          </div>
                        )
                      })
                    })() : null}
                    {/* Procedural Maps — same navigation as any act: tree in the sidebar */}
                    {mapsList && mapsList.length > 0 && (
                      <div>
                        <div style={{ fontSize: 10, fontWeight: 600, color: COLORS.textMuted, padding: '4px 12px 2px', textTransform: 'uppercase', letterSpacing: 0.5, fontFamily: "'Montserrat', sans-serif" }}>Procedural Maps</div>
                        <button onClick={() => { setPickerOpen(false); setAct('maps'); setActiveSection(''); setActiveRuling(null); setActivePrivateRuling(null); setSearchPage(false); setSectionData(null); setActiveMap(null); setBrowsingAct(true); window.history.pushState(null, '', '/maps'); if (isMobile) setDrawerOpen(false) }} style={{
                          display: 'block', width: '100%', padding: '6px 12px',
                          background: 'transparent', border: 'none',
                          color: act === 'maps' ? COLORS.accent : COLORS.text,
                          fontSize: 12, cursor: 'pointer',
                          fontFamily: "'Montserrat', sans-serif", textAlign: 'left',
                        }}
                          onMouseEnter={e => e.currentTarget.style.background = COLORS.bg}
                          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                        >Maps ({mapsList.length})</button>
                      </div>
                    )}
                    <div>
                      <div style={{ fontSize: 10, fontWeight: 600, color: COLORS.textMuted, padding: '4px 12px 2px', textTransform: 'uppercase', letterSpacing: 0.5, fontFamily: "'Montserrat', sans-serif" }}>References</div>
                      <button onClick={() => { setPickerOpen(false); setActiveDefinitions(''); setSearchPage(false); setActiveSection(''); setActiveRuling(null); setActivePrivateRuling(null); setActiveMap(null); setBrowsingAct(false); window.history.pushState(null, '', '/definitions'); if (isMobile) setDrawerOpen(false) }} style={{
                        display: 'block', width: '100%', padding: '6px 12px',
                        background: 'transparent', border: 'none',
                        color: activeDefinitions !== null ? COLORS.accent : COLORS.text,
                        fontSize: 12, cursor: 'pointer',
                        fontFamily: "'Montserrat', sans-serif", textAlign: 'left',
                      }}
                        onMouseEnter={e => e.currentTarget.style.background = COLORS.bg}
                        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                      >Definitions</button>
                    </div>
                    </div>
                  )}
                </div>
              )
            })()}
          </div>
          {isMobile && drawerOpen && (
            <button
              onClick={() => setDrawerOpen(false)}
              style={{
                position: 'absolute', top: 12, right: 14, zIndex: 200,
                background: 'transparent', color: COLORS.heading,
                border: 'none',
                fontSize: 20, cursor: 'pointer', lineHeight: 1,
                width: 36, height: 36,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              {'\u2715'}
            </button>
          )}
        </div>

        {/* Tree */}
        <div style={{ flex: 1, overflow: 'auto', padding: isMobile ? '6px 8px' : 8 }}>
          {(treeForRender?.parts || []).map(p => (
            <TreeNode key={p.id} node={p} level={0} activeSection={act === 'maps' ? (activeMap || '') : activeSection} onSelect={handleTreeSelect} isMobile={isMobile} expandedIds={expandedIds} act={act} />
          ))}
        </div>

        {/* Sidebar bottom: settings, bug report, sign in/user */}
        <div style={{
          borderTop: `1px solid ${COLORS.border}`,
          padding: isMobile ? '10px 12px' : '8px 12px',
          display: 'flex', gap: 6, alignItems: 'center',
        }}>
          <div style={{ position: 'relative' }}>
            <button
              onClick={() => { setSearchPage(true); window.history.pushState(null, '', '/search'); if (isMobile) setDrawerOpen(false) }}
              title="Search with advanced filters"
              style={{
                padding: isMobile ? '7px 9px' : '6px 8px', borderRadius: 6,
                background: COLORS.bg,
                color: COLORS.text,
                border: `1px solid ${COLORS.border}`, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
                fontSize: 11, fontFamily: "'Montserrat', sans-serif", fontWeight: 500,
              }}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
              Search
            </button>
          </div>
          <div ref={settingsRef} style={{ position: 'relative' }}>
            <button
              onClick={() => setSettingsOpen(true)}
              title="Settings & Tools"
              style={{
                padding: isMobile ? '7px 9px' : '6px 8px', borderRadius: 6,
                background: COLORS.bg,
                color: COLORS.text,
                border: `1px solid ${COLORS.border}`, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
                fontSize: 11, fontFamily: "'Montserrat', sans-serif", fontWeight: 500,
              }}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
              </svg>
              Settings
            </button>
          </div>
          <button
            onClick={() => setIssuesOpen(true)}
            title="View known bugs"
            style={{
              padding: isMobile ? '7px 9px' : '6px 8px', borderRadius: 6,
              background: COLORS.bg, color: COLORS.textMuted,
              border: `1px solid ${COLORS.border}`, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
              fontSize: 11, fontFamily: "'Montserrat', sans-serif", fontWeight: 500,
            }}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            Bugs
          </button>
          <div style={{ flex: 1, minWidth: 0 }} />
          {user ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, minWidth: 0 }}>
              <div style={{
                fontSize: 10, color: COLORS.accent, fontFamily: "'Montserrat', sans-serif",
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {user.name || user.email}
              </div>
              <button
                onClick={() => window.location.href = '/auth/logout'}
                title="Sign out"
                style={{
                  padding: '4px 6px', borderRadius: 4,
                  background: COLORS.bg, color: COLORS.textMuted,
                  border: `1px solid ${COLORS.border}`, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 10, fontFamily: "'Montserrat', sans-serif", flexShrink: 0,
                }}
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
                </svg>
              </button>
            </div>
          ) : (
            <button
              onClick={() => window.location.href = '/auth/login'}
              title="Sign in"
              style={{
                padding: isMobile ? '7px 9px' : '6px 8px', borderRadius: 6,
                background: COLORS.accent, color: '#fff',
                border: 'none', cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
                fontSize: 11, fontFamily: "'Montserrat', sans-serif", fontWeight: 500,
              }}
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/>
              </svg>
              Sign in
            </button>
          )}
        </div>
      </div>

      {/* Resize handle */}
      {!isMobile && (
        <div
          className={`resize-handle${isResizing ? ' dragging' : ''}`}
          onMouseDown={() => setIsResizing(true)}
          style={{
            width: 4,
            background: isResizing ? '#279e88' : 'transparent',
            position: 'relative',
            zIndex: 101,
            flexShrink: 0,
          }}
        />
      )}

      {/* Main content */}
      <div style={{
        flex: 1, overflow: 'auto',
        padding: isMobile ? '16px 12px 24px' : '20px 40px',
        paddingTop: isMobile ? (hasContent ? 12 : 16) : (hasContent ? 12 : 20),
        maxWidth: activeMap ? 1400 : 960, margin: '0 auto',
        fontFamily: "'Lora', serif",
        color: COLORS.text,
        display: 'flex', flexDirection: 'column',
        position: 'relative',
      }}>
        {isMobile && !drawerOpen && (
          <button
            onClick={() => setDrawerOpen(true)}
            title="Open sidebar"
            style={{
              position: 'absolute', top: 4, left: 4, zIndex: 60,
              background: COLORS.surface, color: COLORS.heading,
              border: `1px solid ${COLORS.border}`,
              borderRadius: 6, padding: '7px 10px',
              cursor: 'pointer', lineHeight: 1, fontSize: 13,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
        )}
        {/* Sticky search bar — removed in v3.0: search lives on /search with advanced filters */}
        {pins.length > 0 && (
          <PinnedTabs
            pins={pins}
            act={act}
            activeSection={activeSection}
            isMobile={isMobile}
            setAct={setAct}
            setActiveSection={setActiveSection}
            unpin={unpin}
          />
        )}

        {hasContent && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <button
              onClick={() => {
                navigator.clipboard.writeText(window.location.href).catch(() => {})
              }}
              title="Copy link"
              style={{
                padding: '6px 8px', borderRadius: 6,
                background: COLORS.surface, color: COLORS.textMuted,
                border: `1px solid ${COLORS.border}`, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
                <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
              </svg>
            </button>
            <button
              onClick={() => {
                const isRuling = activeRuling && rulingData
                const isPrivateRuling = activePrivateRuling && privateRulingData
                const isCase = window.location.pathname.startsWith('/tax-cases/')
                if (isPrivateRuling) {
                  setGraphOpen({ type: 'private-ruling', citation: activePrivateRuling!, label: `EV/${activePrivateRuling}` })
                } else if (isRuling) {
                  setGraphOpen({ type: 'ruling', citation: activeRuling!, label: activeRuling! })
                } else if (isCase) {
                  const citation = window.location.pathname.replace('/tax-cases/', '')
                  setGraphOpen({ type: 'case', citation: decodeURIComponent(citation), label: decodeURIComponent(citation) })
                } else if (activeSection) {
                  setGraphOpen({ type: 'section', act, section: activeSection, label: `${act}/${activeSection}` })
                }
              }}
              aria-label="Knowledge graph"
              style={{
                padding: '6px 8px', borderRadius: 6,
                background: COLORS.surface, color: COLORS.textMuted,
                border: `1px solid ${COLORS.border}`, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3"/>
                <circle cx="19" cy="5" r="2"/>
                <circle cx="5" cy="19" r="2"/>
                <line x1="12" y1="9" x2="19" y2="7"/>
                <line x1="5" y1="17" x2="12" y2="15"/>
                <line x1="7" y1="19" x2="17" y2="7"/>
              </svg>
              <span style={{ fontSize: 11 }}>Graph</span>
            </button>
            <button
              onClick={() => { setAct('maps'); setActiveSection(''); setActiveRuling(null); setActivePrivateRuling(null); setSearchPage(false); setSectionData(null); setActiveMap(null); setBrowsingAct(true); window.history.pushState(null, '', '/maps'); if (isMobile) setDrawerOpen(true) }}
              aria-label="Procedural maps"
              title="Procedural knowledge maps"
              style={{
                padding: '6px 8px', borderRadius: 6,
                background: COLORS.surface, color: COLORS.textMuted,
                border: `1px solid ${COLORS.border}`, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21 3 6"/>
                <line x1="9" y1="3" x2="9" y2="18"/>
                <line x1="15" y1="6" x2="15" y2="21"/>
              </svg>
              <span style={{ fontSize: 11 }}>Maps</span>
            </button>
            <button
              onClick={() => {
                setActiveDefinitions(act && ['itaa-1997','itaa-1936','gst-1999','corporations-act-2001','fbt-1986','taa-1953','sis-1993','aml-ctf-2006','nz-it-2007'].includes(act) ? act : '')
                setSearchPage(false)
                setActiveSection('')
                setActiveRuling(null)
                setActivePrivateRuling(null)
                setActiveMap(null)
                window.history.pushState(null, '', '/definitions')
                if (isMobile) setDrawerOpen(false)
              }}
              aria-label="Definitions"
              title="Browse defined terms"
              style={{
                padding: '6px 8px', borderRadius: 6,
                background: activeDefinitions !== null ? COLORS.accent : COLORS.surface,
                color: activeDefinitions !== null ? '#fff' : COLORS.textMuted,
                border: `1px solid ${COLORS.border}`, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="4" y1="9" x2="20" y2="9"/>
                <line x1="4" y1="15" x2="20" y2="15"/>
                <line x1="10" y1="3" x2="8" y2="21"/>
                <line x1="16" y1="3" x2="14" y2="21"/>
              </svg>
              <span style={{ fontSize: 11 }}>Definitions</span>
            </button>
          </div>
        )}

        {searchPage ? (
          <div style={{ marginTop: 4 }}>
            <SearchPanel
              acts={acts}
              onNavigate={(targetAct, section) => {
                if (targetAct === 'tax-cases') {
                  onNavigateCase(section)
                } else if (targetAct === 'private-rulings') {
                  setAct(targetAct)
                  setSearchPage(false)
                  setActivePrivateRuling(section)
                  setActiveSection('')
                  setActiveRuling(null)
                } else {
                  setAct(targetAct)
                  setSearchPage(false)
                  if (targetAct === 'rulings') {
                    setActiveRuling(section)
                    setActiveSection('')
                  } else {
                    setActiveSection(section)
                    setActiveRuling(null)
                  }
                }
              }}
              isMobile={isMobile}
              onResultsChange={setSearchResultsCount}
            />
          </div>
        ) : activeDefinitions !== null ? (
          <DefinitionsBrowser
            act={activeDefinitions}
            onSelectAct={(a) => {
              setActiveDefinitions(a)
              window.history.pushState(null, '', a ? `/definitions/${a}` : '/definitions')
            }}
            onNavigate={(a, s, anchor) => {
              setActiveDefinitions(null)
              onNavigate(a, s, anchor)
            }}
          />
        ) : activeMap ? (
          <MapView
            mapId={activeMap}
            onClose={() => {
              const back = act === 'maps' ? '/maps' : (act ? `/${act}` : '/itaa-1997')
              setActiveMap(null)
              window.history.pushState(null, '', back)
            }}
            onOpenSection={(a, s) => {
              setActiveMap(null)
              if (a === 'rulings') {
                onNavigateRuling(s)
              } else {
                onNavigate(a, s)
              }
            }}
            height="calc(100vh - 150px)"
            isMobile={isMobile}
          />
        ) : activePrivateRuling && privateRulingData ? (
          <PrivateRulingContent
            data={privateRulingData}
            isMobile={isMobile}
            renderLink={renderLink}
            onNavigate={onNavigate}
            onNavigateRuling={onNavigateRuling}
            onNavigateCase={onNavigateCase}
          />
        ) : activeRuling && rulingData ? (
          <RulingContent
            rulingData={rulingData}
            isMobile={isMobile}
            renderLink={renderLink}
            onNavigate={onNavigate}
            onNavigateRuling={onNavigateRuling}
          />
        ) : act === 'regulatory-guides' && sectionData ? (
          <RegulatoryGuideContent
            sectionData={sectionData}
            isMobile={isMobile}
          />
        ) : act === 'tax-cases' && sectionData ? (
          <TaxCaseContent
            caseData={sectionData}
            isMobile={isMobile}
            onNavigate={onNavigate}
            onNavigateRuling={onNavigateRuling}
          />
        ) : isTreaty(act) && sectionData ? (
          <TreatyContent
            country={sectionData.country || shortActName(act)}
            articleData={sectionData}
            isMobile={isMobile}
            onNavigate={onNavigate}
            onNavigateRuling={onNavigateRuling}
          />
        ) : sectionData ? (
          <SectionContent
            act={act}
            sectionData={sectionData}
            isMobile={isMobile}
            isPinned={isPinned}
            togglePin={togglePin}
            renderLink={renderLink}
            onNavigate={onNavigate}
            onNavigateRuling={onNavigateRuling}
            onNavigateCase={onNavigateCase}
          />
        ) : act === 'private-rulings' && browsingAct ? (
          <PrivateRulingsBrowser
            year={privateRulingsYear}
            onYearChange={setPrivateRulingsYear}
            isMobile={isMobile}
            onOpen={(authnum) => { setActivePrivateRuling(authnum); setActiveSection(''); setActiveRuling(null); if (isMobile) setDrawerOpen(false) }}
          />
        ) : browsingAct && tree && act !== 'rulings' && act !== 'tax-cases' && act !== 'private-rulings' ? (
          <div style={{ fontFamily: "'Montserrat', sans-serif" }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <span style={{ fontSize: 14, fontWeight: 600, color: COLORS.heading }}>
                {shortActName(act)}
              </span>
              {act !== 'maps' && act !== 'treaties' && (
                <button
                  onClick={() => {
                    setActiveDefinitions(act)
                    window.history.pushState(null, '', `/definitions/${act}`)
                  }}
                  style={{
                    background: 'none', border: `1px solid ${COLORS.border}`, borderRadius: 6,
                    padding: '3px 10px', cursor: 'pointer', color: COLORS.accent, fontSize: 12,
                  }}
                >
                  Definitions
                </button>
              )}
            </div>
            <div style={{ borderTop: `1px solid ${COLORS.border}`, paddingTop: 8 }}>
              {(() => {
                // Collect all parent IDs to expand everything
                const allIds = new Set<string>()
                const collectIds = (parts: any[]) => {
                  for (const p of parts) {
                    allIds.add(p.id)
                    if (p.divisions) {
                      for (const d of p.divisions) {
                        allIds.add(d.id)
                        if (d.subdivisions) {
                          for (const s of d.subdivisions) {
                            allIds.add(s.id)
                          }
                        }
                      }
                    }
                  }
                }
                collectIds(tree.parts || [])
                return (tree.parts || []).map(p => (
                  <TreeNode key={p.id} node={p} level={0} activeSection={act === 'maps' ? (activeMap || '') : activeSection} onSelect={e => { setSearchPage(false); if (act === 'maps') { setActiveSection(''); setActiveRuling(null); setSectionData(null); setActiveMap(e); window.history.pushState(null, '', `/maps/${e}`) } else if (act === 'treaties') { const s = e.indexOf('/'); if (s > -1) { setAct(e.slice(0, s)); setActiveSection(e.slice(s + 1)); } else { setAct(e); setActiveSection(''); } } else if (act === 'rulings') { setActiveRuling(e); } else if (act === 'private-rulings') { if (e === 'undated' || /^\d{4}$/.test(e)) { setPrivateRulingsYear(e === 'undated' ? 'undated' : Number(e)); setActivePrivateRuling(null); } else { setActivePrivateRuling(e); } setActiveSection(''); } else { setActiveSection(e); } if (isMobile) setDrawerOpen(false) }} isMobile={isMobile} expandedIds={allIds} act={act} />
                ))
              })()}
            </div>
          </div>
        ) : (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            textAlign: 'center',
            fontFamily: "'Montserrat', sans-serif",
            padding: '0 16px',
            minHeight: '60vh',
            justifyContent: 'center',
          }}>
            <div style={{ fontSize: 20, fontWeight: 700, color: COLORS.heading, marginBottom: 6 }}>
              Legislation Explorer
            </div>
            <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 20, maxWidth: 420, lineHeight: 1.6 }}>
              Browse acts, rulings, private rulings, tax cases, treaties and maps from the sidebar.
              Use Search for full-text search with advanced filters.
            </div>
            <button
              onClick={() => { setSearchPage(true); window.history.pushState(null, '', '/search') }}
              style={{
                padding: '10px 22px', borderRadius: 6,
                background: COLORS.accent, color: '#fff',
                border: 'none', fontSize: 13, cursor: 'pointer',
                fontWeight: 600, fontFamily: "'Montserrat', sans-serif",
              }}
            >
              Search
            </button>
            <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 20 }}>
              Legislation Explorer <span style={{ opacity: 0.5 }}>{appInfo?.version || ''}</span>
            </div>
            <div style={{ display: 'flex', gap: 12, marginTop: 8, flexWrap: 'wrap', justifyContent: 'center', alignItems: 'center' }}>
              <a
                onClick={() => setChangelogOpen(true)}
                style={{ fontSize: 11, color: COLORS.accent, background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'Montserrat', sans-serif", textDecoration: 'underline' }}
              >
                v{appInfo?.version || '2.7.0'}
              </a>
            </div>
          </div>
        )}
      </div>

      <MCPModal open={mcpOpen} onClose={() => setMcpOpen(false)} />
      {settingsOpen && <SettingsPanel onClose={() => setSettingsOpen(false)} />}
      <KeyboardShortcuts showShortcuts={showShortcuts} setShowShortcuts={setShowShortcuts} />

      {/* Knowledge graph modal */}
      {graphOpen && (
        <GraphModal
          type={graphOpen.type}
          act={graphOpen.act}
          section={graphOpen.section}
          citation={graphOpen.citation}
          label={graphOpen.label}
          onClose={() => setGraphOpen(null)}
        />
      )}

      {/* Issues modal */}
      {issuesOpen && (
        <IssuesModal onClose={() => setIssuesOpen(false)} />
      )}

      {/* Changelog modal */}
      {changelogOpen && appInfo?.changelog && (
        <ModalOverlay onClose={() => setChangelogOpen(false)}>
          <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.heading, marginBottom: 16, fontFamily: "'Montserrat', sans-serif" }}>
            Changelog
          </div>
          <div style={{ maxHeight: '60vh', overflow: 'auto' }}>
            {appInfo.changelog.map((entry: any, i: number) => (
              <div key={i} style={{ marginBottom: 16, paddingBottom: 16, borderBottom: i < appInfo.changelog.length - 1 ? `1px solid ${COLORS.border}` : 'none' }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.accent, marginBottom: 2, fontFamily: "'Montserrat', sans-serif" }}>
                  v{entry.version} — {entry.date}
                </div>
                <div style={{ fontSize: 11, color: COLORS.textMuted, marginBottom: 6, fontFamily: "'Montserrat', sans-serif" }}>
                  {entry.title}
                </div>
                <ul style={{ margin: 0, paddingLeft: 16, fontSize: 11, color: COLORS.text, fontFamily: "'Montserrat', sans-serif", lineHeight: 1.6 }}>
                  {entry.changes.map((c: string, j: number) => (
                    <li key={j}>{c}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </ModalOverlay>
      )}

    </div>
    </ThemeProvider>
    </ErrorBoundary>
  )
}

// ---------------------------------------------------------------------------
// ModalOverlay — shared backdrop + container
// ---------------------------------------------------------------------------

function ModalOverlay({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: COLORS.surface, borderRadius: 12,
          padding: 24, width: '90%', maxWidth: 520,
          boxShadow: '0 16px 48px rgba(0,0,0,0.5)',
        }}
      >
        {children}
      </div>
    </div>
  )
}

