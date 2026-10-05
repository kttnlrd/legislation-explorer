import React, { useEffect, useState } from 'react'

interface AdminUser {
  id: number
  email: string
  name: string | null
  provider: string | null
  tier: string
  last_login_at: string | null
  created_at: string | null
}

interface Stats {
  total_users: number
  by_tier: Record<string, number>
  active_7d: number
  total_mcp_tokens: number
  total_mcp_calls: number
  mcp_calls_by_user: { email: string; calls: number; tokens: number }[]
}

const TIERS = [
  { key: 'trial', name: 'Kitten' },
  { key: 'solo', name: 'House cat' },
  { key: 'power', name: 'Maine Coon' },
]

const fmtDate = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : '—')

export default function AdminPanel() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'denied' | 'error'>('loading')
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const [s, u] = await Promise.all([fetch('/api/admin/stats'), fetch('/api/admin/users')])
      if ([s, u].some(r => r.status === 401 || r.status === 403)) return setStatus('denied')
      if (!s.ok || !u.ok) throw new Error(`HTTP ${s.ok ? u.status : s.status}`)
      setStats(await s.json())
      setUsers((await u.json()).users)
      setStatus('ready')
    } catch (e) {
      setError(String(e))
      setStatus('error')
    }
  }

  useEffect(() => { load() }, [])

  const post = async (url: string, body?: unknown) => {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    })
    if (!r.ok) alert(`Failed: ${(await r.json().catch(() => ({}))).detail || r.status}`)
    load()
  }

  const setTier = (u: AdminUser, tier: string) => post(`/api/admin/users/${u.id}/tier`, { tier })
  const remove = (u: AdminUser) => {
    if (confirm(`Delete ${u.email}? This revokes their MCP tokens and cannot be undone.`)) {
      post(`/api/admin/users/${u.id}/delete`)
    }
  }

  const cards: [string, number][] = stats ? [
    ['Total users', stats.total_users],
    ...TIERS.map(t => [t.name, stats.by_tier[t.key] ?? 0] as [string, number]),
    ['Active 7 days', stats.active_7d],
    ['MCP tokens', stats.total_mcp_tokens],
    ['MCP calls', stats.total_mcp_calls],
  ] : []

  return (
    <div className="lk-admin">
      <h1 className="lk-admin__title">Admin</h1>

      {status === 'loading' && <p className="lk-admin__note">Loading…</p>}
      {status === 'denied' && <p className="lk-admin__note">Admin only — sign in as the admin account.</p>}
      {status === 'error' && <p className="lk-admin__note lk-admin__note--error">Couldn't load admin data: {error}</p>}

      {status === 'ready' && (
        <>
          <div className="lk-admin__stats">
            {cards.map(([label, value]) => (
              <div key={label} className="lk-admin__stat">
                <div className="lk-admin__stat-value">{value.toLocaleString()}</div>
                <div className="lk-admin__stat-label">{label}</div>
              </div>
            ))}
          </div>

          {stats && stats.mcp_calls_by_user && stats.mcp_calls_by_user.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <h2 style={{ fontSize: 16, fontWeight: 700, color: 'var(--color-heading)', margin: '0 0 10px' }}>MCP calls by user</h2>
              <div className="lk-admin__table-wrap">
                <table className="lk-admin__table">
                  <thead>
                    <tr><th>User</th><th>Calls</th><th>Tokens</th></tr>
                  </thead>
                  <tbody>
                    {stats.mcp_calls_by_user.map(r => (
                      <tr key={r.email}>
                        <td>{r.email}</td>
                        <td>{r.calls.toLocaleString()}</td>
                        <td>{r.tokens}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {users.length === 0 ? (
            <p className="lk-admin__note">No users yet.</p>
          ) : (
            <div className="lk-admin__table-wrap">
              <table className="lk-admin__table">
                <thead>
                  <tr>
                    <th>Email</th><th>Name</th><th>Provider</th><th>Tier</th>
                    <th>Last login</th><th>Created</th><th />
                  </tr>
                </thead>
                <tbody>
                  {users.map(u => (
                    <tr key={u.id}>
                      <td>{u.email}</td>
                      <td>{u.name || '—'}</td>
                      <td>{u.provider || '—'}</td>
                      <td>
                        <select
                          className="lk-admin__select"
                          value={u.tier}
                          onChange={e => setTier(u, e.target.value)}
                          aria-label={`Tier for ${u.email}`}
                        >
                          {TIERS.map(t => <option key={t.key} value={t.key}>{t.name}</option>)}
                        </select>
                      </td>
                      <td>{fmtDate(u.last_login_at)}</td>
                      <td>{fmtDate(u.created_at)}</td>
                      <td>
                        <button type="button" className="lk-admin__delete" onClick={() => remove(u)}>Delete</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
