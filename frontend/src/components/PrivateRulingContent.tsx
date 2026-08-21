import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import { COLORS } from './common/types'
import { createMarkdownComponents } from './MarkdownRenderers'
import SmartLinkPanel from './SmartLinkPanel'

// ---------------------------------------------------------------------------
// Private ruling detail view — one of the 57,608 ATO private rulings.
// Shape: { authorisation_number, name, date_of_advice, subject, qa_pairs,
//         applies_for_periods, scheme_commenced, facts, relevant_legislation,
//         reasons_for_decision, case_references, formatted_text, graph_key }
// ---------------------------------------------------------------------------

type PrivateRulingContentProps = {
  data: any
  isMobile: boolean
  renderLink?: (href?: string, children?: React.ReactNode) => React.ReactNode | null
  onNavigate: (act: string, section: string, anchor?: string) => void
  onNavigateRuling: (citation: string) => void
  onNavigateCase?: (citation: string) => void
}

function textBlock(value: unknown): string {
  if (Array.isArray(value)) return value.join('\n\n')
  return String(value ?? '')
}

export default function PrivateRulingContent({
  data,
  isMobile,
  renderLink,
  onNavigate,
  onNavigateRuling,
  onNavigateCase,
}: PrivateRulingContentProps) {
  const auth = data.authorisation_number || ''
  const name = data.name || data.subject || 'Private ruling'
  const date = data.date_of_advice || ''
  const qaPairs: { question?: string; answer?: string }[] = data.qa_pairs || []
  const facts = textBlock(data.facts)
  const reasons = textBlock(data.reasons_for_decision)
  const periods = textBlock(data.applies_for_periods)
  const commenced = textBlock(data.scheme_commenced)
  const legRefs: unknown[] = data.relevant_legislation || []
  const caseRefs: unknown[] = data.case_references || []
  const formatted = textBlock(data.formatted_text)
  const graphKey: string = data.graph_key || ''
  const atoUrl: string = data.ato_url || ''
  const downloadUrl: string = data.download_url || ''
  const baseComponents = createMarkdownComponents(isMobile, 'private-rulings', onNavigate, onNavigateRuling, renderLink)

  const md = (src: string) => (
    <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]} components={baseComponents}>
      {src}
    </ReactMarkdown>
  )

  const refList = (items: unknown[]) => {
    if (!items || items.length === 0) return null
    return (
      <div style={{ marginTop: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.heading, marginBottom: 6 }}>
          {Array.isArray(items[0]) && typeof items[0][0] === 'string' ? 'Relevant legislation' : 'References'}
        </div>
        <ul style={{ margin: 0, paddingLeft: 18, color: COLORS.text, fontSize: 13, display: 'flex', flexDirection: 'column', gap: 3 }}>
          {items.map((it, i) => (
            <li key={i}>{typeof it === 'string' ? it : JSON.stringify(it)}</li>
          ))}
        </ul>
      </div>
    )
  }

  return (
    <div>
      <div style={{
        marginBottom: 20, color: COLORS.textMuted, fontSize: 12,
        fontFamily: "'Montserrat', sans-serif", letterSpacing: 0.3,
        textTransform: 'uppercase' as const,
      }}>
        Private Ruling &rsaquo; EV/{auth}
      </div>
      <h1 style={{
        fontSize: 22, fontWeight: 700, color: COLORS.heading, lineHeight: 1.3,
        margin: '0 0 6px', fontFamily: "'Montserrat', sans-serif",
      }}>
        {name}
        {downloadUrl && (
          <a
            href={downloadUrl}
            download
            style={{
              fontSize: 12, fontWeight: 500, marginLeft: 12,
              color: '#fff', background: COLORS.accent,
              textDecoration: 'none', padding: '4px 12px',
              borderRadius: 4, display: 'inline-block',
              verticalAlign: 'middle',
            }}
            title="Download original ATO page"
          >
            Download
          </a>
        )}
      </h1>
      <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 20, fontFamily: "'Montserrat', sans-serif" }}>
        {date ? `Date of advice: ${date}` : 'Undated'} · ATO reference EV/{auth}
        {atoUrl && (
          <>
            {' · '}
            <a href={atoUrl} target="_blank" rel="noopener noreferrer"
               style={{ color: COLORS.accent, textDecoration: 'none' }}>
              View on ATO website ↗
            </a>
          </>
        )}
      </div>

      {formatted && (
        <div style={{ fontSize: 13.5, lineHeight: 1.65, color: COLORS.text }}>
          {md(formatted)}
        </div>
      )}

      {qaPairs.length > 0 && (
        <div style={{ marginTop: 20, display: 'flex', flexDirection: 'column', gap: 14 }}>
          {qaPairs.map((qa, i) => (
            <div key={i}>
              {qa.question && (
                <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.heading, marginBottom: 4 }}>
                  {qa.question}
                </div>
              )}
              {qa.answer && (
                <div style={{ fontSize: 13, color: COLORS.text, lineHeight: 1.6 }}>
                  {md(textBlock(qa.answer))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {facts && (
        <div style={{ marginTop: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.heading, marginBottom: 4 }}>Facts</div>
          <div style={{ fontSize: 13, color: COLORS.text, lineHeight: 1.6 }}>{md(facts)}</div>
        </div>
      )}

      {reasons && (
        <div style={{ marginTop: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.heading, marginBottom: 4 }}>Reasons for decision</div>
          <div style={{ fontSize: 13, color: COLORS.text, lineHeight: 1.6 }}>{md(reasons)}</div>
        </div>
      )}

      {periods && (
        <div style={{ marginTop: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.heading, marginBottom: 4 }}>Applies for periods</div>
          <div style={{ fontSize: 13, color: COLORS.text, lineHeight: 1.6 }}>{md(periods)}</div>
        </div>
      )}

      {commenced && (
        <div style={{ marginTop: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.heading, marginBottom: 4 }}>Scheme commenced</div>
          <div style={{ fontSize: 13, color: COLORS.text, lineHeight: 1.6 }}>{md(commenced)}</div>
        </div>
      )}

      {refList(legRefs)}
      {refList(caseRefs)}

      {graphKey && (
        <div style={{ marginTop: 40, borderTop: `1px solid ${COLORS.border}`, paddingTop: 20 }}>
          <SmartLinkPanel
            act="private-rulings"
            section={auth}
            graphKey={graphKey}
            onNavigate={onNavigate}
            onNavigateRuling={onNavigateRuling}
            onNavigateCase={onNavigateCase}
          />
        </div>
      )}
    </div>
  )
}
