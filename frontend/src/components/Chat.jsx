import { useState } from 'react'

export default function Chat({ onInspect }) {
  const [messages, setMessages] = useState([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event) {
    event.preventDefault()
    const trimmed = query.trim()
    if (!trimmed || loading) return
    setMessages((current) => [...current, { role: 'user', answer: trimmed }])
    setQuery('')
    setLoading(true)
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: trimmed }),
      })
      if (!response.ok) throw new Error('Chat request failed')
      const answer = await response.json()
      setMessages((current) => [...current, { role: 'assistant', ...answer }])
    } catch (error) {
      setMessages((current) => [...current, { role: 'assistant', answer: error.message, citations: [] }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="chat-panel">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">Conversation</span>
          <h2>Ask the ledger</h2>
        </div>
        <span className="model-chip">Guarded RAG</span>
      </div>
      <div className="message-list">
        {messages.length === 0 && <div className="empty-state"><span>01</span><p>What would you like to verify?</p></div>}
        {messages.map((message, index) => (
          <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
            <span className="message-label">{message.role === 'user' ? 'You' : 'Ledger Lens'}</span>
            <p>{message.answer}</p>
            {message.role === 'assistant' && <button className="inspect-button" onClick={() => onInspect(message)}>Inspect evidence <span>↗</span></button>}
          </article>
        ))}
        {loading && <div className="typing">Synthesizing sources<span>...</span></div>}
      </div>
      <form className="prompt-bar" onSubmit={submit}>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ask about revenue, margins, or cash flow" aria-label="Financial question" />
        <button type="submit" aria-label="Send question">Send <span>↗</span></button>
      </form>
    </section>
  )
}
