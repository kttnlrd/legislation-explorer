import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { COLORS } from './common/types'

// ---------------------------------------------------------------------------
// Private rulings browser — year grid + per-year list (57,608 rulings).
// Controlled: `year` lives in App so the sidebar tree can drive it too.
// year: number = a year, 'undated' = undated bucket, null = nothing selected.
// ---------------------------------------------------------------------------

type YearEntry = { year: number; count: number }
type RulingItem = { authnum: string; name: string; date_of_advice: string }
export type PrivateRulingsYear = number | 'undated' | null

const PAGE = 50

export default function PrivateRulingsBrowser({
  year,
  onYearChange,
  isMobile,
  onOpen,
}: {
  year: PrivateRulingsYear
  onYearChange: (y: PrivateRulingsYear) => void
  isMobile: boolean
  onOpen: (authnum: string) => void
}) {
  const [years, setYears] = useState<YearEntry[]>([])
  const [undated, setUndated] = useState(0)
  const [total, setTotal] = useState(0)
  const [rulings, setRulings] = useState<RulingItem[]>([])
  const [listTotal, setListTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loadingList, setLoadingList] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api.privateRulingsTree()
      .then(d => {
        setYears(d.years || [])
        setUndated(d.undated || 0)
        setTotal(d.total || 0)
        setError('')
      })
      .catch(e => setError(e.message))
  }, [])

  useEffect(() => {
    if (year === null) return
    setLoadingList(true)
    setRulings([])
    setOffset(0)
    const fetchList = year === 'undated'
      ? api.privateRulingsUndated(PAGE, 0)
      : api.privateRulingsByYear(year, PAGE, 0)
    fetchList
      .then(d => {
        setRulings(d.rulings || [])
        setListTotal(d.total || 0)
        setLoadingList(false)
        setError('')
      })
      .catch(e => { setLoadingList(false); setError(e.message) })
  }, [year])

  const loadMore = () => {
    if (year === null) return
    const next = offset + PAGE
    setLoadingList(true)
    const fetchList = year === 'undated'
      ? api.privateRulingsUndated(PAGE, next)
      : api.privateRulingsByYear(year, PAGE, next)
    fetchList
      .then(d => {
        setRulings(prev => [...prev, ...(d.rulings || [])])
        setOffset(next)
        setLoadingList(false)
      })
      .catch(e => { setLoadingList(false); setError(e.message) })
  }

  const yearChip = (y: YearEntry) => {
    const active = year === y.year
    return (
      <button
        key={y.year}
        onClick={() => onYearChange(y.year)}
        style={{
          padding: '8px 12px',
          borderRadius: 6,
          border: `1px solid ${active ? COLORS.accent : COLORS.border}`,
          background: active ? COLORS.surfaceHover : COLORS.surface,
          color: active ? COLORS.accent : COLORS.text,
          cursor: 'pointer',
          fontSize: 13,
          fontWeight: active ? 600 : 400,
          fontFamily: "'Montserrat', sans-serif",
        }}
      >
        {y.year} <span style={{ opacity: 0.6 }}>({y.count})</span>
      </button>
    )
  }

  return (
    <div style={{ fontFamily: "'Montserrat', sans-serif", padding: isMobile ? 0 : '0 4px' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: COLORS.heading }}>Private Rulings</span>
        <span style={{ fontSize: 12, color: COLORS.textMuted }}>
          {total.toLocaleString()} rulings
          {undated > 0 && ` · ${undated} undated`}
        </span>
      </div>
      <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 12 }}>
        ATO private rulings are confidential advice — access is restricted to authorised users.
      </div>

      {error && (
        <div style={{ color: '#e5484d', fontSize: 12, marginBottom: 12 }}>{error}</div>
      )}

      <div style={{
        display: 'flex', flexWrap: 'wrap', gap: 6,
        marginBottom: 16, maxHeight: 220, overflowY: 'auto',
      }}>
        {years.map(yearChip)}
        {undated > 0 && (
          <button
            onClick={() => onYearChange('undated')}
            style={{
              padding: '8px 12px', borderRadius: 6,
              border: `1px solid ${year === 'undated' ? COLORS.accent : COLORS.border}`,
              background: year === 'undated' ? COLORS.surfaceHover : COLORS.surface,
              color: year === 'undated' ? COLORS.accent : COLORS.text,
              cursor: 'pointer', fontSize: 13,
              fontFamily: "'Montserrat', sans-serif",
            }}
          >
            Undated <span style={{ opacity: 0.6 }}>({undated})</span>
          </button>
        )}
      </div>

      {year === null ? (
        <div style={{
          borderTop: `1px solid ${COLORS.border}`, paddingTop: 12,
          color: COLORS.textMuted, fontSize: 13,
        }}>
          Pick a year to browse its rulings.
        </div>
      ) : (
        <div style={{ borderTop: `1px solid ${COLORS.border}`, paddingTop: 8 }}>
          <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 6 }}>
            {listTotal.toLocaleString()} rulings · {year === 'undated' ? 'undated' : year}
          </div>
          {loadingList && rulings.length === 0 ? (
            <div style={{ color: COLORS.textMuted, fontSize: 13, padding: '16px 0' }}>Loading…</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {rulings.map(r => (
                <button
                  key={r.authnum}
                  onClick={() => onOpen(r.authnum)}
                  style={{
                    textAlign: 'left', cursor: 'pointer',
                    padding: '8px 4px', border: 'none', borderBottom: `1px solid ${COLORS.border}`,
                    background: 'transparent', color: COLORS.text,
                    fontFamily: "'Montserrat', sans-serif", fontSize: 13,
                    display: 'flex', justifyContent: 'space-between', gap: 12,
                  }}
                >
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {r.name || 'Untitled ruling'}
                  </span>
                  <span style={{ color: COLORS.textMuted, fontSize: 12, whiteSpace: 'nowrap', flexShrink: 0 }}>
                    {r.date_of_advice || '—'} · EV/{r.authnum.slice(-6)}
                  </span>
                </button>
              ))}
              {rulings.length < listTotal && (
                <button
                  onClick={loadMore}
                  disabled={loadingList}
                  style={{
                    marginTop: 10, padding: '8px 0', borderRadius: 6,
                    border: `1px solid ${COLORS.border}`, background: COLORS.surface,
                    color: COLORS.text, cursor: 'pointer', fontSize: 13,
                    fontFamily: "'Montserrat', sans-serif",
                  }}
                >
                  {loadingList ? 'Loading…' : `Load more (${(listTotal - rulings.length).toLocaleString()} remaining)`}
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
