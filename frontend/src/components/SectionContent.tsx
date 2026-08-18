import React, { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import { COLORS } from './common/types'
import { createMarkdownComponents, RenderLinkFn } from './MarkdownRenderers'
import SmartLinkPanel from './SmartLinkPanel'
import { api } from '../api'

interface SectionContentProps {
  act: string
  sectionData: any
  isMobile: boolean
  isPinned?: boolean
  togglePin?: () => void
  renderLink?: RenderLinkFn
  onNavigate: (act: string, section: string, anchor?: string) => void
  onNavigateRuling: (citation: string) => void
  onNavigateCase: (citation: string) => void
}

const SectionContent: React.FC<SectionContentProps> = ({
  act,
  sectionData,
  isMobile,
  isPinned,
  togglePin,
  renderLink,
  onNavigate,
  onNavigateRuling,
  onNavigateCase,
}) => {
  const fm = sectionData?.frontmatter || {}
  const components = createMarkdownComponents(isMobile, act, onNavigate, onNavigateRuling, renderLink)

  // Comments state
  const [comments, setComments] = useState<any[]>([])
  const [commentsOpen, setCommentsOpen] = useState(false)
  const [commentAuthor, setCommentAuthor] = useState('')
  const [commentText, setCommentText] = useState('')
  const [commentLoading, setCommentLoading] = useState(false)

  const sectionId = fm.section || ''

  useEffect(() => {
    if (!act || !sectionId) {
      setComments([])
      return
    }
    api.listComments(act, sectionId)
      .then(data => setComments(data.comments || []))
      .catch(() => setComments([]))
  }, [act, sectionId])

  const handleAddComment = async () => {
    if (!commentText.trim()) return
    setCommentLoading(true)
    try {
      const newComment = await api.createComment(act, sectionId, commentAuthor || 'Anonymous', commentText)
      setComments(prev => [newComment, ...prev])
      setCommentText('')
      setCommentAuthor('')
    } catch (e) {
      alert('Failed to add comment')
    } finally {
      setCommentLoading(false)
    }
  }

  const handleResolve = async (id: number) => {
    try {
      await api.resolveComment(id)
      setComments(prev => prev.map(c => c.id === id ? { ...c, resolved: true } : c))
    } catch (e) {
      alert('Failed to resolve comment')
    } finally {
      // No longer need setCommentLoading(false) here, it's for addComment
    }
  }

  return (
    <div>
      <div style={{
        marginBottom: 20, color: COLORS.textMuted, fontSize: 12,
        fontFamily: "'Montserrat', sans-serif", letterSpacing: 0.3,
        textTransform: 'uppercase' as const, display: 'flex', alignItems: 'center',
      }}>
        {fm.act} &rsaquo; Part {fm.part} &rsaquo; Division {fm.division}
        <button
          onClick={togglePin}
          style={{
            marginLeft: 12, padding: '4px 8px', borderRadius: 4,
            background: isPinned ? COLORS.accent : COLORS.surface,
            color: isPinned ? '#fff' : COLORS.textMuted,
            border: `1px solid ${COLORS.border}`, fontSize: 11, cursor: 'pointer',
            fontWeight: 600, fontFamily: "'Montserrat', sans-serif",
            whiteSpace: 'nowrap',
            alignSelf: 'flex-start',
          }}
        >
          {isPinned ? 'Unpin' : 'Pin'}
        </button>
      </div>

      <div style={{ lineHeight: 1.7, fontSize: isMobile ? 15 : 15, color: COLORS.text }}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]} components={components}>
          {sectionData.body || sectionData.markdown}
        </ReactMarkdown>
      </div>

      {/* Comments */}
      <div style={{ marginTop: 40, borderTop: `1px solid ${COLORS.border}`, paddingTop: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', marginBottom: 12 }}
             onClick={() => setCommentsOpen(!commentsOpen)}>
          <h2 style={{ color: COLORS.heading, fontSize: isMobile ? 17 : 18, fontWeight: 600, margin: 0 }}>
            Comments {comments.length > 0 && `(${comments.length})`}
          </h2>
          <span style={{ color: COLORS.textMuted, fontSize: 20 }}>{commentsOpen ? '\u25b2' : '\u25bc'}</span>
        </div>
        {commentsOpen && (
          <div>
            {/* Add comment form */}
            <div style={{ marginBottom: 16, padding: 12, background: COLORS.surface, borderRadius: 6, border: `1px solid ${COLORS.border}` }}>
              <input
                value={commentAuthor}
                onChange={e => setCommentAuthor(e.target.value)}
                placeholder="Your name (optional)"
                style={{
                  width: '100%', padding: 8, marginBottom: 8, borderRadius: 4,
                  background: COLORS.bg, color: COLORS.heading,
                  border: `1px solid ${COLORS.border}`, fontSize: 13,
                  fontFamily: "'Montserrat', sans-serif",
                }}
              />
              <textarea
                value={commentText}
                onChange={e => setCommentText(e.target.value)}
                placeholder="Add a comment..."
                rows={3}
                style={{
                  width: '100%', padding: 8, marginBottom: 8, borderRadius: 4,
                  background: COLORS.bg, color: COLORS.heading,
                  border: `1px solid ${COLORS.border}`, fontSize: 13,
                  fontFamily: "'Montserrat', sans-serif",
                  resize: 'vertical',
                }}
              />
              <button
                onClick={handleAddComment}
                disabled={commentLoading || !commentText.trim()}
                style={{
                  padding: '8px 16px', borderRadius: 4,
                  background: commentLoading || !commentText.trim() ? COLORS.surfaceHover : COLORS.accent,
                  color: '#fff', border: 'none', fontSize: 13, cursor: commentLoading || !commentText.trim() ? 'not-allowed' : 'pointer',
                  fontWeight: 600, fontFamily: "'Montserrat', sans-serif",
                }}
              >
                {commentLoading ? 'Posting...' : 'Post Comment'}
              </button>
            </div>

            {/* Comments list */}
            {comments.length === 0 ? (
              <p style={{ color: COLORS.textMuted, fontSize: 13 }}>No comments yet.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {comments.map((c: any) => (
                  <div key={c.id} style={{
                    padding: 12, background: COLORS.surface, borderRadius: 6,
                    border: `1px solid ${COLORS.border}`, opacity: c.resolved ? 0.5 : 1,
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                      <span style={{ fontWeight: 600, color: COLORS.heading, fontSize: 13 }}>{c.author}</span>
                      <span style={{ color: COLORS.textMuted, fontSize: 11 }}>
                        {new Date(c.created_at).toLocaleString()}
                      </span>
                    </div>
                    <p style={{ margin: 0, color: COLORS.text, fontSize: 14, lineHeight: 1.6 }}>{c.text}</p>
                    {!c.resolved && (
                      <button
                        onClick={() => handleResolve(c.id)}
                        style={{
                          marginTop: 8, padding: '4px 10px', borderRadius: 4,
                          background: COLORS.surfaceHover, color: COLORS.textMuted,
                          border: `1px solid ${COLORS.border}`, fontSize: 11, cursor: 'pointer',
                          fontFamily: "'Montserrat', sans-serif",
                        }}
                      >
                        Resolve
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Smart Links — Related content */}
      <div style={{ marginTop: 40, borderTop: `1px solid ${COLORS.border}`, paddingTop: 20 }}>
        <SmartLinkPanel
          act={act}
          section={sectionId}
          onNavigate={onNavigate}
          onNavigateRuling={onNavigateRuling}
          onNavigateCase={onNavigateCase}
        />
      </div>
    </div>
  )
}

export default SectionContent
