import React, { useState, useEffect } from 'react'
import { COLORS } from './common/types'

type TaxCaseContentProps = {
  caseData: any
  isMobile: boolean
  onNavigate?: (act: string, section: string) => void
  onNavigateRuling?: (citation: string) => void
}

// Parse legislation citation like "Income Tax Assessment Act 1997 (Cth) s 8-1" → {act, section}
function parseLegislationRef(ref: string): { act: string; section: string } | null {
  // Patterns: "Act Name (Cth) s X", "Act Name (Cth) ss X, Y", "Act Name X s Y"
  const trimmed = ref.trim()
  // Try to match common formats
  let m = trimmed.match(/s{1,2}\s+([\d]+(?:[A-Z])?(?:\([\d]+\))?(?:-\d+(?:\([\d]+\))?)*)/i)
  if (!m) m = trimmed.match(/section\s+([\d][\dA-Za-z\-\(\)]+\d?)/i)
  if (!m) return null
  
  const section = m[1]
  
  // Map common act names to act IDs
  const actMap: Record<string, string> = {
    'income tax assessment act 1997': 'itaa-1997',
    'income tax assessment act 1936': 'itaa-1936',
    'taxation administration act 1953': 'taa-1953',
    'a new tax system (goods and services tax) act 1999': 'gst-1999',
    'goods and services tax act 1999': 'gst-1999',
    'federal court of australia act 1976': 'itaa-1997',
    'administrative appeals tribunal act 1975': 'itaa-1997',
    'fringe benefits tax assessment act 1986': 'itaa-1997',
    'superannuation industry (supervision) act 1993': 'itaa-1997',
    'taxation administration act 1999': 'taa-1953',
    'income tax (transitional provisions) act 1997': 'itaa-1997',
    'international tax agreements act 1953': 'itaa-1997',
    'customs act 1901': 'itaa-1997',
    'federal proceedings (costs) act 1981': 'itaa-1997',
    'federal court rules 2011': 'itaa-1997',
    'a new tax system (australian business number) act 1999': 'itaa-1997',
    'customs tariff act 1995': 'itaa-1997',
    'superannuation guarantee (administration) act 1992': 'itaa-1997',
  }
  
  const lower = trimmed.toLowerCase()
  let matchedAct = 'itaa-1997' // default fallback
  for (const [name, actId] of Object.entries(actMap)) {
    if (lower.includes(name)) {
      matchedAct = actId
      break
    }
  }
  
  return { act: matchedAct, section }
}

// Extract citation from cases_cited entry like "[2025] FCAFC 11 — Rusanov v Commissioner"
function extractCaseCitation(entry: string | any): string {
  if (typeof entry === 'string') {
    const m = entry.match(/^(\[[^\]]+\]\s+\S+\s+\S+)/)
    return m ? m[1] : entry.split(' — ')[0].trim()
  }
  return entry.citation || ''
}

export default function TaxCaseContent({ caseData, isMobile, onNavigate, onNavigateRuling }: TaxCaseContentProps) {
  if (!caseData) return null

  const {
    citation,
    title,
    court_label,
    decision_date,
    judges,
    outcome,
    catchwords,
    related_provisions,
    related_rulings,
    section_refs,
    paragraph_count,
    content_length,
    cited_by_count,
    austlii_url,
    hca_url,
    fedcourt_url,
  } = caseData

  // Summary — skip fetch for headnote-only cases (< 10 paragraphs)
  const [summaryData, setSummaryData] = useState<any>(null)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const hasSubstance = true // always show summary if available; paragraph_count may be unreliable

  useEffect(() => {
    setSummaryData(null)
    if (!citation || !hasSubstance) return
    const safe = citation.replace(/ /g, '_').replace(/\//g, '_').replace(/\[/g, '').replace(/\]/g, '')
    setSummaryLoading(true)
    fetch(`/static/cleaned/summaries/${safe}.json`)
      .then(r => r.ok ? r.json() : null)
      .then(data => setSummaryData(data))
      .catch(() => setSummaryData(null))
      .finally(() => setSummaryLoading(false))
  }, [citation, hasSubstance])

  return (
    <div>
      <div style={{
        marginBottom: 20, color: COLORS.textMuted, fontSize: 12,
        fontFamily: "'Montserrat', sans-serif", letterSpacing: 0.3,
        textTransform: 'uppercase' as const,
      }}>
        Tax Case &rsaquo; {title || citation}
      </div>
      <h1 style={{
        color: COLORS.heading, fontSize: isMobile ? 20 : 22, marginBottom: 16,
        fontWeight: 600, borderBottom: `1px solid ${COLORS.border}`, paddingBottom: 8,
      }}>
        {title ? `${title} — ${citation}` : citation}
      </h1>

      {/* Metadata table */}
      <div style={{
        display: 'flex', flexDirection: 'column', gap: 8,
        marginBottom: 24, fontSize: isMobile ? 13 : 14,
        fontFamily: "'Montserrat', sans-serif",
      }}>
        {citation && <MetadataRow label="Citation" value={citation} />}
        {court_label && <MetadataRow label="Court" value={court_label} />}
        {decision_date && <MetadataRow label="Decision Date" value={decision_date} />}
        {judges && <MetadataRow label="Judges" value={Array.isArray(judges) ? judges.join(', ') : judges} />}
        {outcome && <MetadataRow label="Outcome" value={outcome} />}
        {catchwords && <MetadataRow label="Catchwords" value={catchwords} />}
        {paragraph_count !== undefined && paragraph_count !== null && (
          <MetadataRow label="Paragraphs" value={String(paragraph_count)} />
        )}
        {content_length !== undefined && content_length !== null && (
          <MetadataRow label="Content Length" value={`${(content_length / 1024).toFixed(1)} KB`} />
        )}
        {cited_by_count !== undefined && cited_by_count !== null && (
          <MetadataRow label="Cited By" value={String(cited_by_count)} />
        )}
      </div>

      {/* Links */}
      {(austlii_url || hca_url || fedcourt_url || citation) && (
        <div style={{ marginBottom: 24, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {austlii_url && (
            <a href={austlii_url} target="_blank" rel="noopener noreferrer" style={{
              padding: '8px 14px', borderRadius: 6, background: COLORS.accent, color: '#fff',
              textDecoration: 'none', fontSize: 12, fontFamily: "'Montserrat', sans-serif", fontWeight: 500,
            }}>
              View on AustLII &rarr;
            </a>
          )}
          {hca_url && (
            <a href={hca_url} target="_blank" rel="noopener noreferrer" style={{
              padding: '8px 14px', borderRadius: 6, background: COLORS.surface, color: COLORS.accent,
              border: `1px solid ${COLORS.border}`, textDecoration: 'none', fontSize: 12,
              fontFamily: "'Montserrat', sans-serif", fontWeight: 500,
            }}>
              View on HCA &rarr;
            </a>
          )}
          {fedcourt_url && (
            <a href={fedcourt_url} target="_blank" rel="noopener noreferrer" style={{
              padding: '8px 14px', borderRadius: 6, background: COLORS.surface, color: COLORS.accent,
              border: `1px solid ${COLORS.border}`, textDecoration: 'none', fontSize: 12,
              fontFamily: "'Montserrat', sans-serif", fontWeight: 500,
            }}>
              View on FedCourt &rarr;
            </a>
          )}
          {citation && (
            <a href={`/api/tax-cases/case/${encodeURIComponent(citation)}/download`} style={{
              padding: '8px 14px', borderRadius: 6, background: COLORS.surface, color: COLORS.accent,
              border: `1px solid ${COLORS.border}`, textDecoration: 'none', fontSize: 12,
              fontFamily: "'Montserrat', sans-serif", fontWeight: 500,
            }}>
              Download HTML &darr;
            </a>
          )}
        </div>
      )}

      {/* Case Summary — only for cases with substantive text (>= 10 paragraphs) */}
      {hasSubstance && (
        <div style={{ marginBottom: 24, borderTop: `1px solid ${COLORS.border}`, paddingTop: 20 }}>
          <h2 style={{
            color: COLORS.heading, fontSize: isMobile ? 16 : 17,
            marginBottom: 12, fontWeight: 600,
            fontFamily: "'Montserrat', sans-serif",
          }}>
            Case Summary
          </h2>
          {summaryLoading ? (
            <div style={{ color: COLORS.textMuted, fontSize: 13, fontFamily: "'Montserrat', sans-serif" }}>
              Loading summary...
            </div>
          ) : summaryData && !summaryData.error ? (
            <div style={{ fontSize: 13, color: COLORS.textMuted, lineHeight: 1.6 }}>
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontWeight: 600, color: COLORS.heading, marginBottom: 4 }}>Facts</div>
                <div style={{ color: COLORS.text, fontSize: 12 }}>{summaryData.facts}</div>
              </div>
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontWeight: 600, color: COLORS.heading, marginBottom: 4 }}>Issues</div>
                <ol style={{ margin: 0, paddingLeft: 18, color: COLORS.text, fontSize: 12 }}>
                  {(summaryData.issues || []).map((i: string, idx: number) => (
                    <li key={idx} style={{ marginBottom: 4 }}>{i}</li>
                  ))}
                </ol>
              </div>
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontWeight: 600, color: COLORS.heading, marginBottom: 4 }}>Held</div>
                <div style={{ color: COLORS.text, fontSize: 12 }}>{summaryData.held}</div>
              </div>
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontWeight: 600, color: COLORS.heading, marginBottom: 4 }}>Reasoning</div>
                <div style={{ color: COLORS.text, fontSize: 12 }}>{summaryData.reasoning}</div>
              </div>
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontWeight: 600, color: COLORS.heading, marginBottom: 4 }}>Outcome</div>
                <div style={{ color: COLORS.text, fontSize: 12 }}>{summaryData.outcome}</div>
              </div>
              {(summaryData.cases_cited || []).length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontWeight: 600, color: COLORS.heading, marginBottom: 4 }}>
                    Cases Cited ({summaryData.cases_cited.length})
                  </div>
                  <div style={{ color: COLORS.text, fontSize: 12, lineHeight: 1.8 }}>
                    {(summaryData.cases_cited || []).map((c: any, idx: number) => {
                      const cit = typeof c === 'string' ? c : c.citation || ''
                      const name = typeof c === 'string' ? '' : c.name || ''
                      const linkCit = extractCaseCitation(c)
                      return (
                        <div key={idx}
                          style={{ cursor: 'pointer', color: COLORS.accent }}
                          onClick={() => onNavigate?.('tax-cases', linkCit)}
                        >
                          {cit}{name ? ` — ${name}` : ''}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
              {(summaryData.legislation_cited || []).length > 0 && (
                <div>
                  <div style={{ fontWeight: 600, color: COLORS.heading, marginBottom: 4 }}>
                    Legislation Cited ({summaryData.legislation_cited.length})
                  </div>
                  <div style={{ color: COLORS.text, fontSize: 12, lineHeight: 1.8 }}>
                    {(summaryData.legislation_cited || []).map((l: string, idx: number) => {
                      const parsed = parseLegislationRef(l)
                      return (
                        <div key={idx}
                          style={{ cursor: parsed ? 'pointer' : 'default', color: parsed ? COLORS.accent : COLORS.text }}
                          onClick={() => parsed && onNavigate?.(parsed.act, parsed.section)}
                        >
                          {l}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div style={{ color: COLORS.textMuted, fontSize: 13, fontFamily: "'Montserrat', sans-serif" }}>
              AI-powered case summary not available yet. Processing in progress.
            </div>
          )}
        </div>
      )}

      {/* Related provisions */}
      {related_provisions && related_provisions.length > 0 && (
        <div style={{ marginTop: 24, borderTop: `1px solid ${COLORS.border}`, paddingTop: 20 }}>
          <h2 style={{
            color: COLORS.heading, fontSize: isMobile ? 16 : 17,
            marginBottom: 12, fontWeight: 600,
            fontFamily: "'Montserrat', sans-serif",
          }}>
            Related Provisions
          </h2>
          <div style={{ fontSize: isMobile ? 13 : 14, color: COLORS.text, lineHeight: 1.7 }}>
            {Array.isArray(related_provisions) ? related_provisions.map((prov: string, i: number) => {
              // Try to parse act/section from provision like "ITAA 1997 s 8-1"
              const parsed = parseLegislationRef(prov)
              return parsed ? (
                <span key={i}
                  style={{ cursor: 'pointer', color: COLORS.accent }}
                  onClick={() => onNavigate?.(parsed.act, parsed.section)}
                >
                  {prov}{i < related_provisions.length - 1 ? ', ' : ''}
                </span>
              ) : (
                <span key={i}>{prov}{i < related_provisions.length - 1 ? ', ' : ''}</span>
              )
            }) : related_provisions}
          </div>
        </div>
      )}

      {/* Section references — structured refs from case_data */}
      {section_refs && section_refs.length > 0 && (
        <div style={{ marginTop: 24, borderTop: `1px solid ${COLORS.border}`, paddingTop: 20 }}>
          <h2 style={{
            color: COLORS.heading, fontSize: isMobile ? 16 : 17,
            marginBottom: 12, fontWeight: 600,
            fontFamily: "'Montserrat', sans-serif",
          }}>
            Section References
          </h2>
          <div style={{ fontSize: isMobile ? 13 : 14, color: COLORS.text, lineHeight: 1.7 }}>
            {section_refs.map((ref: any, i: number) => (
              <span key={i}
                style={{ cursor: 'pointer', color: COLORS.accent }}
                onClick={() => onNavigate?.(ref.act, ref.section)}
              >
                {ref.act && ref.section ? `${ref.act} s ${ref.section}` : ref.section || ref.base || ref}{i < section_refs.length - 1 ? ', ' : ''}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Related rulings */}
      {related_rulings && related_rulings.length > 0 && (
        <div style={{ marginTop: 24, borderTop: `1px solid ${COLORS.border}`, paddingTop: 20 }}>
          <h2 style={{
            color: COLORS.heading, fontSize: isMobile ? 16 : 17,
            marginBottom: 12, fontWeight: 600,
            fontFamily: "'Montserrat', sans-serif",
          }}>
            Related Rulings
          </h2>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {related_rulings.map((ruling: string, i: number) => (
              <li key={i} style={{
                padding: '4px 0', fontSize: 12,
                fontFamily: "'Montserrat', sans-serif",
                color: COLORS.accent, cursor: 'pointer',
              }}
                onClick={() => onNavigateRuling?.(ruling)}
              >
                {ruling}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function MetadataRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{
      display: 'flex', gap: 8,
      padding: '6px 10px',
      background: 'rgba(0,0,0,0.15)',
      borderRadius: 4,
    }}>
      <span style={{
        fontWeight: 600, color: COLORS.heading,
        minWidth: 130, flexShrink: 0,
        fontSize: 12,
      }}>
        {label}
      </span>
      <span style={{ color: COLORS.text, fontSize: 12 }}>
        {value}
      </span>
    </div>
  )
}