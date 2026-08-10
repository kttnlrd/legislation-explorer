import React, { useState } from 'react'
import { COLORS } from './common/types'

type RegulatoryGuideContentProps = {
  sectionData: any
  isMobile: boolean
}

export default function RegulatoryGuideContent({
  sectionData,
  isMobile,
}: RegulatoryGuideContentProps) {
  const citation: string = sectionData?.citation || ''
  const title: string = sectionData?.descriptive_title || ''
  const status: string = sectionData?.status || ''
  const statusKey: string = sectionData?.status_key || ''
  const body: string = sectionData?.body || ''
  const hasPdf: boolean = sectionData?.has_pdf || false
  const pageUrl: string = sectionData?.page_url || ''
  const pdfUrl: string = sectionData?.pdf_url || ''
  const downloadUrl: string = sectionData?.download_url || ''
  const date: string = sectionData?.date || ''

  const subject: string = sectionData?.subject || ''
  const background: string = sectionData?.background || ''
  const ruling: string = sectionData?.ruling || ''
  const casesReferenced: string[] = sectionData?.cases_referenced || []
  const legislationReferenced: string[] = sectionData?.legislation_referenced || []
  const relatedRulings: string[] = sectionData?.related_rulings || []
  const hasSummary: boolean = sectionData?.has_summary || false

  const [showFullText, setShowFullText] = useState(false)

  const isWithdrawn = statusKey === 'withdrawn' || statusKey === 'unavailable' || statusKey === 'no_pdf'

  const summarySection = (label: string, text: string) =>
    text ? (
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 }}>
          {label}
        </div>
        <div style={{ fontSize: 14, lineHeight: 1.7, color: COLORS.text }}>{text}</div>
      </div>
    ) : null

  const refList = (label: string, items: string[], emptyMsg: string) => (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>
        {label} ({items.length})
      </div>
      {items.length > 0 ? (
        <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13.5, lineHeight: 1.7, color: COLORS.text }}>
          {items.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      ) : (
        <div style={{ fontSize: 13, color: COLORS.textMuted }}>{emptyMsg}</div>
      )}
    </div>
  )

  return (
    <div>
      <div style={{
        marginBottom: 20, color: COLORS.textMuted, fontSize: 12,
        fontFamily: "'Montserrat', sans-serif", letterSpacing: 0.3,
        textTransform: 'uppercase' as const,
      }}>
        ASIC Regulatory Guide &rsaquo; {citation}
      </div>

      <h1 style={{
        color: COLORS.heading, fontSize: isMobile ? 20 : 22, marginBottom: 16,
        fontWeight: 600, borderBottom: `1px solid ${COLORS.border}`, paddingBottom: 8,
      }}>
        {citation} — {title}
        {' '}
        <span style={{
          fontSize: 11, fontWeight: 500, marginLeft: 10,
          padding: '3px 10px', borderRadius: 4,
          color: isWithdrawn ? '#b45309' : '#059669',
          background: isWithdrawn ? '#fffbeb' : '#ecfdf5',
          textTransform: 'uppercase', letterSpacing: 0.5,
          verticalAlign: 'middle',
        }}>
          {status}
        </span>
      </h1>

      {/* Metadata + download panel */}
      <div style={{
        marginBottom: 24, border: `1px solid ${COLORS.border}`,
        borderRadius: 6, padding: '14px 16px',
        background: COLORS.surface,
        fontSize: 13, color: COLORS.text,
        fontFamily: "'Montserrat', sans-serif", lineHeight: 1.6,
      }}>
        {status && <p style={{ margin: '0 0 10px 0' }}><strong>Status:</strong> {status}</p>}
        {date && date !== 'unknown' && <p style={{ margin: '0 0 10px 0' }}><strong>Last updated:</strong> {date}</p>}
        {hasPdf && downloadUrl && (
          <p style={{ margin: '0 0 10px 0' }}>
            <a
              href={downloadUrl}
              download
              style={{
                display: 'inline-block', fontSize: 12, fontWeight: 500,
                color: '#fff', background: COLORS.accent,
                textDecoration: 'none', padding: '6px 14px',
                borderRadius: 4,
              }}
            >
              Download PDF
            </a>
            <span style={{ color: COLORS.textMuted, fontSize: 11, marginLeft: 8 }}>
              (hosted on this server)
            </span>
          </p>
        )}
        {pageUrl && (
          <p style={{ margin: 0 }}>
            <a href={pageUrl} target="_blank" rel="noopener noreferrer"
               style={{ color: COLORS.accent, textDecoration: 'none' }}>
              View on ASIC website ↗
            </a>
            {pdfUrl && (
              <span style={{ color: COLORS.textMuted, fontSize: 11, marginLeft: 8 }}>
                (direct PDF: <a href={pdfUrl} target="_blank" rel="noopener noreferrer"
                  style={{ color: COLORS.accent, textDecoration: 'none' }}>download.asic.gov.au</a>)
              </span>
            )}
          </p>
        )}
      </div>

      {/* Structured summary panel */}
      {hasSummary ? (
        <div style={{
          marginBottom: 24, border: `1px solid ${COLORS.border}`,
          borderRadius: 6, padding: '16px 18px',
          background: COLORS.surface,
        }}>
          {summarySection('Subject', subject)}
          {summarySection('Background', background)}
          {summarySection('ASIC position', ruling)}
          {refList('Cases referenced', casesReferenced, 'No cases referenced')}
          {refList('Legislation referenced', legislationReferenced, 'No legislation referenced')}
        </div>
      ) : (
        <div style={{
          marginBottom: 24, border: `1px dashed ${COLORS.border}`,
          borderRadius: 6, padding: '16px 18px',
          background: COLORS.surface,
          fontSize: 13, color: COLORS.textMuted,
          fontFamily: "'Montserrat', sans-serif",
        }}>
          {isWithdrawn
            ? 'This guide has been withdrawn and is no longer available as a PDF. See the ASIC website link above for historical context.'
            : 'Structured summary not yet available for this guide.'}
        </div>
      )}

      {/* Full text toggle */}
      {body ? (
        <div style={{ marginBottom: 24 }}>
          <button
            onClick={() => setShowFullText(!showFullText)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: COLORS.accent, fontSize: 13, fontWeight: 500,
              padding: 0, fontFamily: "'Montserrat', sans-serif",
              textDecoration: 'underline',
            }}
          >
            {showFullText ? 'Hide full text' : 'Show full text'}
          </button>
          {showFullText && (
            <div style={{
              marginTop: 12, lineHeight: 1.7, fontSize: isMobile ? 15 : 15,
              color: COLORS.text, whiteSpace: 'pre-wrap',
            }}>
              {body}
            </div>
          )}
        </div>
      ) : null}
    </div>
  )
}