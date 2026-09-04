import React, { useEffect, useState } from 'react'
import { api } from '../api'
import { COLORS } from './common/types'

const STATUS_COLORS: Record<string, string> = {
  announced: '#b8860b',
  exposure_draft: '#007AFF',
  before_parliament: '#5856d6',
  passed: '#2e7d32',
  enacted: '#1b5e20',
  withdrawn: '#9e9e9e',
}
const STATUS_LABELS: Record<string, string> = {
  announced: 'Announced',
  exposure_draft: 'Exposure draft',
  before_parliament: 'Before Parliament',
  passed: 'Passed',
  enacted: 'Enacted',
  withdrawn: 'Withdrawn',
}
const TYPE_LABELS: Record<string, string> = {
  bill: 'Bill',
  exposure_draft: 'Exposure draft',
  announcement: 'Announcement',
  ato_draft: 'ATO draft',
  other: 'Other',
}

interface Item {
  id: string
  title: string
  measure_type: string
  status: string
  summary: string
  announced_date?: string | null
  source_url?: string | null
  notes: string
  added_at: string
}

const emptyForm = {
  title: '',
  measure_type: 'bill',
  status: 'announced',
  summary: '',
  announced_date: '',
  source_url: '',
  notes: '',
}

export default function ProposedLawBrowser({ isMobile }: { isMobile: boolean }) {
  const [items, setItems] = useState<Item[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(emptyForm)
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState('')

  const load = () => {
    setLoading(true)
    api
      .proposedLawList()
      .then((d: any) => {
        setItems((d.items || []).sort((a: Item, b: Item) => (a.added_at < b.added_at ? 1 : -1)))
        setError('')
      })
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const submit = () => {
    if (!form.title.trim()) return
    setSaving(true)
    setSaveMsg('')
    const body: any = { ...form }
    if (!body.announced_date) delete body.announced_date
    if (!body.source_url) delete body.source_url
    api
      .proposedLawAdd(body)
      .then(() => {
        setForm(emptyForm)
        setShowForm(false)
        setSaveMsg('Added')
        load()
      })
      .catch((e: any) => setSaveMsg(`Error: ${e.message}`))
      .finally(() => setSaving(false))
  }

  const changeStatus = (id: string, status: string) => {
    api.proposedLawUpdate(id, { status }).then(load).catch((e: any) => setError(e.message))
  }

  const remove = (id: string) => {
    if (!window.confirm('Delete this item?')) return
    api.proposedLawDelete(id).then(load).catch((e: any) => setError(e.message))
  }

  const label = (map: Record<string, string>, key: string) => map[key] || key

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '6px 9px',
    border: `1px solid ${COLORS.border}`,
    borderRadius: 6,
    fontSize: 13,
    background: COLORS.surface,
    color: COLORS.text,
    fontFamily: "'Inter', sans-serif",
    boxSizing: 'border-box',
  }

  return (
    <div style={{ fontFamily: "'Inter', sans-serif", padding: isMobile ? 10 : 4 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14, flexWrap: 'wrap', gap: 8 }}>
        <span style={{ fontSize: 17, fontWeight: 700, color: COLORS.heading }}>Proposed Law</span>
        <button
          onClick={() => {
            setShowForm(!showForm)
            setSaveMsg('')
          }}
          style={{
            background: COLORS.accent,
            color: '#fff',
            border: 'none',
            borderRadius: 6,
            padding: '7px 14px',
            fontSize: 13,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          {showForm ? 'Cancel' : '+ Add item'}
        </button>
      </div>

      {showForm && (
        <div style={{ border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: 12, marginBottom: 16, background: COLORS.surface }}>
          <div style={{ display: 'grid', gap: 8, gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr' }}>
            <input style={{ ...inputStyle, gridColumn: isMobile ? '1' : '1 / -1' }} placeholder="Title — e.g. Treasury Laws Amendment (X) Bill 2026"
              value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} />
            <select style={inputStyle} value={form.measure_type} onChange={e => setForm({ ...form, measure_type: e.target.value })}>
              {Object.entries(TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <select style={inputStyle} value={form.status} onChange={e => setForm({ ...form, status: e.target.value })}>
              {Object.entries(STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <input style={inputStyle} placeholder="Announced date (YYYY-MM-DD)" value={form.announced_date}
              onChange={e => setForm({ ...form, announced_date: e.target.value })} />
            <input style={inputStyle} placeholder="Source URL" value={form.source_url}
              onChange={e => setForm({ ...form, source_url: e.target.value })} />
            <textarea style={{ ...inputStyle, gridColumn: isMobile ? '1' : '1 / -1', minHeight: 54, resize: 'vertical' }}
              placeholder="Summary — what the measure does"
              value={form.summary} onChange={e => setForm({ ...form, summary: e.target.value })} />
            <textarea style={{ ...inputStyle, gridColumn: isMobile ? '1' : '1 / -1', minHeight: 40, resize: 'vertical' }}
              placeholder="Notes (optional)" value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} />
          </div>
          <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 10 }}>
            <button onClick={submit} disabled={saving || !form.title.trim()}
              style={{ background: COLORS.accent, color: '#fff', border: 'none', borderRadius: 6, padding: '7px 16px', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
              {saving ? 'Saving…' : 'Save item'}
            </button>
            {saveMsg && <span style={{ fontSize: 12.5, color: saveMsg.startsWith('Error') ? '#c62828' : '#2e7d32' }}>{saveMsg}</span>}
          </div>
        </div>
      )}

      {error && <div style={{ color: '#c62828', fontSize: 13, marginBottom: 10 }}>{error}</div>}

      {loading ? (
        <div style={{ color: COLORS.text, fontSize: 13 }}>Loading…</div>
      ) : items.length === 0 ? (
        <div style={{ border: `1px dashed ${COLORS.border}`, borderRadius: 8, padding: 22, textAlign: 'center', color: COLORS.text, fontSize: 13.5 }}>
          Nothing tracked yet. Add a measure with “+ Add item”, or ask Hermes — e.g. “add the Treasury Laws Amendment (X) Bill to proposed law”.
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 10 }}>
          {items.map(it => (
            <div key={it.id} style={{ border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: '11px 13px', background: COLORS.surface }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 14.5, fontWeight: 600, color: COLORS.heading }}>{it.title}</span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                  <span style={{ background: STATUS_COLORS[it.status] || '#9e9e9e', color: '#fff', borderRadius: 10, padding: '2px 9px', fontSize: 11.5, fontWeight: 600 }}>
                    {label(STATUS_LABELS, it.status)}
                  </span>
                  <span style={{ background: '#eceff1', color: '#37474f', borderRadius: 10, padding: '2px 9px', fontSize: 11.5 }}>{label(TYPE_LABELS, it.measure_type)}</span>
                </span>
              </div>
              {it.summary && <div style={{ fontSize: 13, color: COLORS.text, marginTop: 6 }}>{it.summary}</div>}
              {(it.announced_date || it.source_url || it.notes) && (
                <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 6, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                  {it.announced_date && <span>Announced: {it.announced_date}</span>}
                  {it.source_url && <a href={it.source_url} target="_blank" rel="noreferrer" style={{ color: COLORS.accent }}>Source</a>}
                  {it.notes && <span style={{ flexBasis: '100%' }}>{it.notes}</span>}
                </div>
              )}
              <div style={{ marginTop: 9, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                <select value={it.status} onChange={e => changeStatus(it.id, e.target.value)}
                  style={{ padding: '3px 6px', borderRadius: 6, border: `1px solid ${COLORS.border}`, fontSize: 12, background: COLORS.surface, color: COLORS.text }}>
                  {Object.entries(STATUS_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
                <button onClick={() => remove(it.id)} title="Delete"
                  style={{ background: 'none', border: `1px solid ${COLORS.border}`, borderRadius: 6, padding: '3px 9px', fontSize: 12, color: '#c62828', cursor: 'pointer' }}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
