import React, { useState } from 'react'
import { useTheme, FONTS, ThemeConfig } from '../ThemeContext'
import { COLORS } from './common/types'
import { api } from '../api'
import { shortActName } from '../utils/display'

const ACCENT_PRESETS = [
  '#279e88', '#2563eb', '#7c3aed', '#059669',
  '#d97706', '#dc2626', '#e11d48', '#0891b2',
]

export default function SettingsPanel({ onClose }: { onClose: () => void }) {
  const {
    colors: c, theme, accentColor, textColor, bgColor, headingFont, bodyFont,
    userPrefs, setTheme, setAccentColor, setTextColor, setBgColor,
    setHeadingFont, setBodyFont, setDisplayName, setDefaultAct,
    resetTheme, savePrefs,
  } = useTheme()

  const [tab, setTab] = useState<'profile' | 'appearance' | 'mcp'>('profile')
  const [editingDisplayName, setEditingDisplayName] = useState(userPrefs?.display_name || '')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [acts, setActs] = useState<{ id: string; name: string }[]>([])

  React.useEffect(() => {
    fetch('/api/acts').then(r => r.ok ? r.json() : []).then(setActs).catch(() => {})
  }, [])

  const handleSaveDisplayName = async () => {
    setSaving(true)
    setDisplayName(editingDisplayName)
    await savePrefs({ display_name: editingDisplayName })
    setSaving(false)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const handleThemeToggle = (t: string) => {
    setTheme(t)
    savePrefs({ theme: t } as any)
  }

  const handleAccent = (color: string) => {
    setAccentColor(color)
    savePrefs({ accent_color: color } as any)
  }

  const handleTextColor = (color: string) => {
    setTextColor(color)
    savePrefs({ text_color: color } as any)
  }

  const handleBgColor = (color: string) => {
    setBgColor(color)
    savePrefs({ bg_color: color } as any)
  }

  const handleHeadingFont = (f: string) => {
    setHeadingFont(f)
    savePrefs({ heading_font: f } as any)
  }

  const handleBodyFont = (f: string) => {
    setBodyFont(f)
    savePrefs({ body_font: f } as any)
  }

  const handleReset = () => {
    resetTheme()
    fetch('/api/user/prefs/reset', { method: 'POST' }).catch(() => {})
  }

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
          background: c.surface, borderRadius: 12,
          padding: 24, width: '90%', maxWidth: 520,
          maxHeight: '85vh', overflow: 'auto',
          boxShadow: '0 16px 48px rgba(0,0,0,0.5)',
          border: `1px solid ${c.border}`,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ margin: 0, color: c.heading, fontSize: 16, fontFamily: "var(--heading-font, 'Montserrat'), sans-serif", fontWeight: 600 }}>
            Settings
          </h2>
          <button onClick={onClose} style={{
            background: 'transparent', border: 'none',
            color: c.textMuted, fontSize: 22, cursor: 'pointer', lineHeight: 1, padding: '0 4px',
          }}>&times;</button>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 0, marginBottom: 20, borderBottom: `1px solid ${c.border}` }}>
          <button
            onClick={() => setTab('profile')}
            style={{
              padding: '8px 16px', border: 'none', cursor: 'pointer',
              background: 'transparent', color: tab === 'profile' ? c.accent : c.textMuted,
              fontSize: 12, fontWeight: tab === 'profile' ? 600 : 400,
              fontFamily: "var(--heading-font, 'Montserrat'), sans-serif",
              borderBottom: tab === 'profile' ? `2px solid ${c.accent}` : '2px solid transparent',
            }}
          >Profile</button>
          <button
            onClick={() => setTab('appearance')}
            style={{
              padding: '8px 16px', border: 'none', cursor: 'pointer',
              background: 'transparent', color: tab === 'appearance' ? c.accent : c.textMuted,
              fontSize: 12, fontWeight: tab === 'appearance' ? 600 : 400,
              fontFamily: "var(--heading-font, 'Montserrat'), sans-serif",
              borderBottom: tab === 'appearance' ? `2px solid ${c.accent}` : '2px solid transparent',
            }}
          >Appearance</button>
          <button
            onClick={() => setTab('mcp')}
            style={{
              padding: '8px 16px', border: 'none', cursor: 'pointer',
              background: 'transparent', color: tab === 'mcp' ? c.accent : c.textMuted,
              fontSize: 12, fontWeight: tab === 'mcp' ? 600 : 400,
              fontFamily: "var(--heading-font, 'Montserrat'), sans-serif",
              borderBottom: tab === 'mcp' ? `2px solid ${c.accent}` : '2px solid transparent',
            }}
          >MCP Tokens</button>
        </div>

        {tab === 'profile' && (
          <div>
            {/* Display Name */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 11, color: c.textMuted, display: 'block', marginBottom: 4, fontFamily: "var(--heading-font, 'Montserrat'), sans-serif" }}>
                Display Name
              </label>
              <div style={{ display: 'flex', gap: 6 }}>
                <input
                  value={editingDisplayName}
                  onChange={e => setEditingDisplayName(e.target.value)}
                  placeholder="Your display name"
                  onKeyDown={e => { if (e.key === 'Enter') handleSaveDisplayName() }}
                  style={{
                    flex: 1, padding: '8px 10px', borderRadius: 6, fontSize: 12,
                    background: c.bg, color: c.heading,
                    border: `1px solid ${c.border}`, outline: 'none',
                    fontFamily: "var(--body-font, 'Lora'), serif",
                  }}
                />
                <button
                  onClick={handleSaveDisplayName}
                  disabled={saving}
                  style={{
                    padding: '8px 14px', borderRadius: 6,
                    background: saved ? '#059669' : c.accent, color: '#fff',
                    border: 'none', cursor: 'pointer', fontSize: 11,
                    fontWeight: 600, whiteSpace: 'nowrap',
                  }}
                >
                  {saved ? 'Saved!' : saving ? 'Saving...' : 'Save'}
                </button>
              </div>
            </div>

            {/* Default Act */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 11, color: c.textMuted, display: 'block', marginBottom: 4, fontFamily: "var(--heading-font, 'Montserrat'), sans-serif" }}>
                Default Act
              </label>
              <select
                value={userPrefs?.default_act || 'itaa-1997'}
                onChange={e => { setDefaultAct(e.target.value); savePrefs({ default_act: e.target.value } as any) }}
                style={{
                  width: '100%', padding: '8px 10px', borderRadius: 6, fontSize: 12,
                  background: c.bg, color: c.heading,
                  border: `1px solid ${c.border}`, outline: 'none',
                  fontFamily: "var(--heading-font, 'Montserrat'), sans-serif",
                  cursor: 'pointer',
                }}
              >
                {(acts.length > 0 ? acts : [{ id: 'itaa-1997', name: 'ITAA 1997' }, { id: 'itaa-1936', name: 'ITAA 1936' }, { id: 'corporations-act-2001', name: 'Corporations Act 2001' }, { id: 'regulatory-guides', name: 'ASIC Regulatory Guides' }]).length > 0 ? (() => {
                  const actList = acts.length > 0 ? acts : [{ id: 'itaa-1997', name: 'ITAA 1997' }, { id: 'itaa-1936', name: 'ITAA 1936' }, { id: 'corporations-act-2001', name: 'Corporations Act 2001' }, { id: 'regulatory-guides', name: 'ASIC Regulatory Guides' }]
                  const actById = Object.fromEntries(actList.map(a => [a.id, a]))
                  const DOMAINS = [
                    { label: 'Australian Tax', ids: ['itaa-1997', 'itaa-1936', 'gst-1999', 'taa-1953', 'master-tax-guide', 'master-tax-examples', 'master-gst-guide', 'rulings', 'tax-cases'] },
                    { label: 'New Zealand Tax', ids: ['nz-it-2007'] },
                    { label: 'Corporate Law', ids: ['corporations-act-2001', 'regulatory-guides'] },
                  ]
                  return DOMAINS.map(domain => {
                    const domainActs = domain.ids.filter(id => actById[id]).map(id => actById[id])
                    if (domainActs.length === 0) return null
                    return (
                      <optgroup key={domain.label} label={domain.label}>
                        {domainActs.map(a => <option key={a.id} value={a.id}>{shortActName(a.id)}</option>)}
                      </optgroup>
                    )
                  })
                })() : null}
              </select>
            </div>
          </div>
        )}

        {tab === 'appearance' && (
          <div>
            {/* Theme toggle */}
            <div style={{ marginBottom: 20 }}>
              <label style={{ fontSize: 11, color: c.textMuted, display: 'block', marginBottom: 6, fontFamily: "var(--heading-font, 'Montserrat'), sans-serif" }}>
                Theme
              </label>
              <div style={{ display: 'flex', gap: 8 }}>
                {['dark', 'light'].map(t => (
                  <button
                    key={t}
                    onClick={() => handleThemeToggle(t)}
                    style={{
                      flex: 1, padding: '8px 12px', borderRadius: 6,
                      background: theme === t ? c.accent : c.bg,
                      color: theme === t ? '#fff' : c.text,
                      border: `1px solid ${theme === t ? c.accent : c.border}`,
                      cursor: 'pointer', fontSize: 11,
                      fontWeight: theme === t ? 600 : 400,
                      fontFamily: "var(--heading-font, 'Montserrat'), sans-serif",
                      textTransform: 'capitalize',
                    }}
                  >{t}</button>
                ))}
              </div>
            </div>

            {/* Accent Color */}
            <div style={{ marginBottom: 20 }}>
              <label style={{ fontSize: 11, color: c.textMuted, display: 'block', marginBottom: 6, fontFamily: "var(--heading-font, 'Montserrat'), sans-serif" }}>
                Accent Color
              </label>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {ACCENT_PRESETS.map(color => (
                  <button
                    key={color}
                    onClick={() => handleAccent(color)}
                    title={color}
                    style={{
                      width: 28, height: 28, borderRadius: 6,
                      background: color, border: accentColor === color ? '2px solid #fff' : `1px solid ${c.border}`,
                      cursor: 'pointer', outline: accentColor === color ? `2px solid ${color}` : 'none',
                      outlineOffset: 1,
                    }}
                  />
                ))}
                <div style={{ position: 'relative' }}>
                  <input
                    type="color"
                    value={accentColor}
                    onChange={e => handleAccent(e.target.value)}
                    style={{
                      width: 28, height: 28, borderRadius: 6, padding: 0,
                      border: `1px solid ${c.border}`, cursor: 'pointer',
                      background: 'transparent',
                    }}
                  />
                </div>
              </div>
            </div>

            {/* Text Color */}
            <div style={{ marginBottom: 20 }}>
              <label style={{ fontSize: 11, color: c.textMuted, display: 'block', marginBottom: 6, fontFamily: "var(--heading-font, 'Montserrat'), sans-serif" }}>
                Text Color
              </label>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input
                  type="color"
                  value={textColor}
                  onChange={e => handleTextColor(e.target.value)}
                  style={{
                    width: 32, height: 32, borderRadius: 6, padding: 0,
                    border: `1px solid ${c.border}`, cursor: 'pointer',
                    background: 'transparent',
                  }}
                />
                <button
                  onClick={() => handleTextColor('#aebec2')}
                  style={{
                    padding: '4px 10px', borderRadius: 4, fontSize: 10,
                    background: c.bg, color: c.textMuted,
                    border: `1px solid ${c.border}`, cursor: 'pointer',
                  }}
                >Reset</button>
              </div>
            </div>

            {/* Background Color */}
            <div style={{ marginBottom: 20 }}>
              <label style={{ fontSize: 11, color: c.textMuted, display: 'block', marginBottom: 6, fontFamily: "var(--heading-font, 'Montserrat'), sans-serif" }}>
                Background Color
              </label>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input
                  type="color"
                  value={bgColor}
                  onChange={e => handleBgColor(e.target.value)}
                  style={{
                    width: 32, height: 32, borderRadius: 6, padding: 0,
                    border: `1px solid ${c.border}`, cursor: 'pointer',
                    background: 'transparent',
                  }}
                />
                <button
                  onClick={() => handleBgColor('#0a1214')}
                  style={{
                    padding: '4px 10px', borderRadius: 4, fontSize: 10,
                    background: c.bg, color: c.textMuted,
                    border: `1px solid ${c.border}`, cursor: 'pointer',
                  }}
                >Reset</button>
              </div>
            </div>

            {/* Heading Font */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 11, color: c.textMuted, display: 'block', marginBottom: 4, fontFamily: "var(--heading-font, 'Montserrat'), sans-serif" }}>
                Heading Font
              </label>
              <select
                value={headingFont}
                onChange={e => handleHeadingFont(e.target.value)}
                style={{
                  width: '100%', padding: '8px 10px', borderRadius: 6, fontSize: 12,
                  background: c.bg, color: c.heading,
                  border: `1px solid ${c.border}`, outline: 'none',
                  fontFamily: "'Montserrat', sans-serif",
                  cursor: 'pointer',
                }}
              >
                {FONTS.heading.map(f => (
                  <option key={f} value={f} style={{ fontFamily: f }}>{f}</option>
                ))}
              </select>
            </div>

            {/* Body Font */}
            <div style={{ marginBottom: 24 }}>
              <label style={{ fontSize: 11, color: c.textMuted, display: 'block', marginBottom: 4, fontFamily: "var(--heading-font, 'Montserrat'), sans-serif" }}>
                Body Font
              </label>
              <select
                value={bodyFont}
                onChange={e => handleBodyFont(e.target.value)}
                style={{
                  width: '100%', padding: '8px 10px', borderRadius: 6, fontSize: 12,
                  background: c.bg, color: c.heading,
                  border: `1px solid ${c.border}`, outline: 'none',
                  fontFamily: "'Montserrat', sans-serif",
                  cursor: 'pointer',
                }}
              >
                {FONTS.body.map(f => (
                  <option key={f} value={f} style={{ fontFamily: f }}>{f}</option>
                ))}
              </select>
              <div style={{ marginTop: 8, fontSize: 13, color: c.text, fontFamily: `'${bodyFont}', ${bodyFont === 'serif' ? 'serif' : 'sans-serif'}`, lineHeight: 1.6, padding: 12, background: c.bg, borderRadius: 6, border: `1px solid ${c.border}` }}>
                The quick brown fox jumps over the lazy dog. <span style={{ color: c.accent }}>Section 8-1</span> of the ITAA 1997.
              </div>
            </div>

            {/* Reset */}
            <button
              onClick={handleReset}
              style={{
                width: '100%', padding: '10px', borderRadius: 6,
                background: 'transparent', color: '#ef4444',
                border: `1px solid #ef4444`, cursor: 'pointer',
                fontSize: 12, fontWeight: 600,
                fontFamily: "var(--heading-font, 'Montserrat'), sans-serif",
              }}
            >
              Reset to Defaults
            </button>
          </div>
        )}

        {tab === 'mcp' && (
          <MCPTabContent c={c} />
        )}
      </div>
    </div>
  )
}

type TokenInfo = {
  id: number;
  name: string;
  created_by: string;
  created_at: number;
  last_used: number | null;
  request_count: number;
};

function MCPTabContent({ c }: { c: ThemeConfig }) {
  const [generatedToken, setGeneratedToken] = useState<string | null>(null);
  const [tokens, setTokens] = useState<TokenInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [copiedToken, setCopiedToken] = useState(false);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState('');

  const baseUrl = 'https://legislation.scriptkitty.yachts/mcp';
  const fullUrl = generatedToken ? `${baseUrl}/${generatedToken}` : baseUrl;

  React.useEffect(() => {
    loadTokens();
    setGeneratedToken(null);
    setError(null);
  }, []);

  const loadTokens = async () => {
    try {
      const data = await api.listMcpTokens();
      setTokens(data.tokens || []);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const generateToken = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.generateMcpToken();
      setGeneratedToken(data.token);
      loadTokens();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const revokeToken = async (tokenId: number) => {
    setError(null);
    try {
      await api.revokeMcpToken(String(tokenId));
      loadTokens();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const startRename = (token: TokenInfo) => {
    setRenamingId(token.id);
    setRenameValue(token.name || '');
  };

  const submitRename = async () => {
    if (renamingId === null) return;
    setError(null);
    try {
      await api.renameMcpToken(renamingId, renameValue.trim() || 'Untitled');
      setRenamingId(null);
      loadTokens();
    } catch (e: any) {
      setError(e.message);
    }
  };

  const cancelRename = () => {
    setRenamingId(null);
    setRenameValue('');
  };

  const copyToClipboard = (text: string, type: 'url' | 'token') => {
    navigator.clipboard.writeText(text).then(() => {
      if (type === 'url') {
        setCopiedUrl(true);
        setTimeout(() => setCopiedUrl(false), 2000);
      } else {
        setCopiedToken(true);
        setTimeout(() => setCopiedToken(false), 2000);
      }
    }).catch(() => {});
  };

  const formatDate = (ts: number | null) => {
    if (!ts) return 'Never';
    return new Date(ts * 1000).toLocaleString();
  };

  return (
    <div>
      <p style={{ color: c.textMuted, fontSize: 12, marginBottom: 16, lineHeight: 1.5 }}>
        Connect Claude Desktop or other MCP clients to this Legislation Explorer.
      </p>

      {/* Generate Token */}
      <button
        onClick={generateToken}
        disabled={loading}
        style={{
          padding: '10px 18px', borderRadius: 6,
          background: c.accent, color: '#fff',
          border: 'none', fontSize: 13, cursor: loading ? 'not-allowed' : 'pointer',
          fontWeight: 600, fontFamily: "var(--heading-font, 'Montserrat'), sans-serif",
          opacity: loading ? 0.7 : 1,
        }}
      >
        {loading ? 'Generating...' : 'Generate New Token'}
      </button>

      {error && (
        <div style={{ marginTop: 12, padding: 10, borderRadius: 6, background: 'rgba(239,68,68,0.1)', color: '#ef4444', fontSize: 12 }}>
          {error}
        </div>
      )}

      {/* Newly generated token */}
      {generatedToken && (
        <div style={{
          marginTop: 20, padding: 14, borderRadius: 6,
          background: 'rgba(39,158,136,0.08)', border: `1px solid ${c.accent}`,
        }}>
          <div style={{ color: c.accent, fontSize: 11, fontWeight: 600, marginBottom: 8, fontFamily: "var(--heading-font, 'Montserrat'), sans-serif" }}>
            Copy this token now — it will not be shown again
          </div>
          <div style={{ position: 'relative' }}>
            <pre style={{
              background: c.bg, color: c.text,
              padding: 10, borderRadius: 6, fontSize: 11,
              overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
              fontFamily: 'monospace', margin: 0,
              border: `1px solid ${c.border}`,
            }}>
              {generatedToken}
            </pre>
            <button
              onClick={() => copyToClipboard(generatedToken, 'token')}
              style={{
                position: 'absolute', top: 6, right: 6,
                padding: '4px 8px', borderRadius: 4,
                background: copiedToken ? c.accent : c.surface,
                color: copiedToken ? '#fff' : c.text,
                border: `1px solid ${c.border}`, fontSize: 10, cursor: 'pointer',
                fontWeight: 600, fontFamily: "var(--heading-font, 'Montserrat'), sans-serif",
              }}
            >
              {copiedToken ? 'Copied!' : 'Copy'}
            </button>
          </div>
        </div>
      )}

{/* MCP Endpoint URL */}
      <div style={{ marginTop: 20 }}>
        <div style={{ color: c.heading, fontSize: 12, fontWeight: 600, marginBottom: 6, fontFamily: "var(--heading-font, 'Montserrat'), sans-serif" }}>
          MCP Endpoint URL
        </div>
        <div style={{ position: 'relative' }}>
          <pre style={{
            background: c.bg, color: c.text,
            padding: 12, borderRadius: 6, fontSize: 11,
            overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
            fontFamily: 'monospace', margin: 0,
            border: `1px solid ${c.border}`,
            minHeight: 36, display: 'flex', alignItems: 'center',
          }}>
            {fullUrl}
          </pre>
          <button
            onClick={() => copyToClipboard(fullUrl, 'url')}
            style={{
              position: 'absolute', top: 6, right: 6,
              padding: '4px 8px', borderRadius: 4,
              background: copiedUrl ? c.accent : c.surface,
              color: copiedUrl ? '#fff' : c.text,
              border: `1px solid ${c.border}`, fontSize: 10, cursor: 'pointer',
              fontWeight: 600, fontFamily: "var(--heading-font, 'Montserrat'), sans-serif",
            }}
          >
            {copiedUrl ? 'Copied!' : 'Copy URL'}
          </button>
        </div>
      </div>

      {/* Token list */}
      {tokens.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <div style={{ color: c.heading, fontSize: 12, fontWeight: 600, marginBottom: 10, fontFamily: "var(--heading-font, 'Montserrat'), sans-serif" }}>
            Your Tokens ({tokens.length})
          </div>
          <div style={{
            maxHeight: 280, overflowY: 'auto',
            border: `1px solid ${c.border}`, borderRadius: 6,
          }}>
            {tokens.map(t => (
              <div key={t.id} style={{
                padding: '10px 12px',
                borderBottom: `1px solid ${c.border}`,
                fontSize: 11, color: c.text,
                fontFamily: "var(--heading-font, 'Montserrat'), sans-serif",
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    {renamingId === t.id ? (
                      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                        <input
                          value={renameValue}
                          onChange={e => setRenameValue(e.target.value)}
                          onKeyDown={e => { if (e.key === 'Enter') submitRename(); if (e.key === 'Escape') cancelRename(); }}
                          autoFocus
                          style={{
                            flex: 1, padding: '4px 6px', borderRadius: 4, fontSize: 11,
                            background: c.bg, color: c.heading,
                            border: `1px solid ${c.accent}`, outline: 'none',
                            fontFamily: "var(--heading-font, 'Montserrat'), sans-serif",
                          }}
                        />
                        <button onClick={submitRename} style={{ padding: '3px 6px', borderRadius: 4, background: c.accent, color: '#fff', border: 'none', cursor: 'pointer', fontSize: 10, fontWeight: 600 }}>Save</button>
                        <button onClick={cancelRename} style={{ padding: '3px 6px', borderRadius: 4, background: c.bg, color: c.textMuted, border: `1px solid ${c.border}`, cursor: 'pointer', fontSize: 10 }}>Cancel</button>
                      </div>
                    ) : (
                      <div
                        onClick={() => startRename(t)}
                        style={{ color: c.heading, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}
                        title="Click to rename"
                      >
                        {t.name || `Token #${t.id}`}
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke={c.textMuted} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
                        </svg>
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => revokeToken(t.id)}
                    title="Revoke token"
                    style={{
                      padding: '3px 6px', borderRadius: 4,
                      background: 'rgba(239,68,68,0.1)', color: '#ef4444',
                      border: 'none', cursor: 'pointer',
                      fontSize: 10, fontWeight: 600, fontFamily: "var(--heading-font, 'Montserrat'), sans-serif",
                      whiteSpace: 'nowrap', flexShrink: 0,
                    }}
                  >
                    Revoke
                  </button>
                </div>
                <div style={{ display: 'flex', gap: 10, marginTop: 4, color: c.textMuted, fontSize: 10 }}>
                  <span><strong style={{ color: c.accent }}>{t.request_count}</strong> calls</span>
                  <span>Created: {formatDate(t.created_at)}</span>
                  <span>Last used: {formatDate(t.last_used)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tokens.length === 0 && !generatedToken && (
        <div style={{ marginTop: 16, color: c.textMuted, fontSize: 11, fontStyle: 'italic' }}>
          No tokens yet. Generate one above to get started.
        </div>
      )}

      <p style={{ color: c.textMuted, fontSize: 11, marginTop: 20, lineHeight: 1.4 }}>
        In Claude Desktop, go to <strong>Settings → Developer → Connectors</strong>, click <strong>Add Custom Connector</strong>:
      </p>
      <div style={{
        background: c.bg, color: c.text,
        padding: 12, borderRadius: 6, fontSize: 11,
        fontFamily: 'monospace', margin: '8px 0 0 0',
        border: `1px solid ${c.border}`,
        lineHeight: 1.5,
      }}>
        <div><strong>Name:</strong> Legislation Explorer</div>
        <div><strong>URL:</strong> <code style={{wordBreak: 'break-all'}}>{fullUrl}</code></div>
        <div style={{marginTop: 4, color: c.textMuted}}>Leave OAuth optional items blank.</div>
      </div>
    </div>
  );
}