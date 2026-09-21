import { useState } from 'react'
import DashboardResult from './DashboardResult'
import RichAnswer from './RichAnswer'

export default function Chat({ onInspect }) {
  const [messages, setMessages] = useState([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event) {
    event.preventDefault()
    const trimmed = query.trim()
    if (!trimmed || loading) return
    const assistantIndex = messages.length + 1
    setMessages((current) => [...current, { role: 'user', answer: trimmed }, { role: 'assistant', answer: '', citations: [] }])
    setQuery('')
    setLoading(true)
    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: trimmed }),
      })
      if (!response.ok) throw new Error('Chat request failed')
      if (!response.body) throw new Error('Streaming is not supported by this browser')
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let streamedAnswer = ''
      let metadata = {}

      const updateAssistant = (patch) => setMessages((current) => current.map((message, index) => index === assistantIndex ? { ...message, ...patch } : message))
      while (true) {
        const { value, done } = await reader.read()
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
        const events = buffer.split('\n\n')
        buffer = events.pop() || ''
        for (const event of events) {
          const dataLine = event.split('\n').find((line) => line.startsWith('data: '))
          if (!dataLine) continue
          const data = JSON.parse(dataLine.slice(6))
          if (event.startsWith('event: token')) {
            streamedAnswer += data.text
            updateAssistant({ answer: streamedAnswer })
          } else if (event.startsWith('event: complete')) {
            metadata = data
            updateAssistant(data)
          }
        }
        if (done) break
      }
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
            {message.role === 'assistant' ? <RichAnswer answer={message.answer} /> : <p>{message.answer}</p>}
            {message.role === 'assistant' && <>
              <DashboardResult payload={message.dashboard_payload} />
              <button className="inspect-button" onClick={() => onInspect(message)}>Inspect evidence <span>↗</span></button>
            </>}
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
