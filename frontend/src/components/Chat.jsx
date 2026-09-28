import { useEffect, useRef, useState } from 'react'
import DashboardResult from './DashboardResult'
import RichAnswer from './RichAnswer'

export default function Chat({ activeStoreId = 'default', activeStoreName = 'Main Ledger', onInspect }) {
  const [messages, setMessages] = useState([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Load store-scoped conversation history whenever active store changes
  useEffect(() => {
    let isMounted = true
    async function fetchHistory() {
      try {
        const res = await fetch(`/api/stores/${activeStoreId}/messages`)
        if (res.ok) {
          const history = await res.json()
          if (isMounted) {
            setMessages(
              history.map((m) => ({
                role: m.role,
                answer: m.content,
                citations: m.citations || [],
                graph_nodes_traversed: m.graph_nodes_traversed || [],
                route_used: m.route_used || 'HYBRID',
                dashboard_payload: m.dashboard_payload || {},
                numerical_fidelity_passed: true,
              }))
            )
          }
        }
      } catch (err) {
        console.error('Failed to load store chat history:', err)
      }
    }
    fetchHistory()
    return () => {
      isMounted = false
    }
  }, [activeStoreId])

  async function submit(event) {
    event.preventDefault()
    const trimmed = query.trim()
    if (!trimmed || loading) return

    const assistantIndex = messages.length + 1
    setMessages((current) => [
      ...current,
      { role: 'user', answer: trimmed },
      { role: 'assistant', answer: '', citations: [], route_used: 'ROUTING...' },
    ])
    setQuery('')
    setLoading(true)

    try {
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: trimmed, store_id: activeStoreId }),
      })
      if (!response.ok) throw new Error('Chat request failed')
      if (!response.body) throw new Error('Streaming is not supported by this browser')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let streamedAnswer = ''

      const updateAssistant = (patch) =>
        setMessages((current) =>
          current.map((message, index) =>
            index === assistantIndex ? { ...message, ...patch } : message
          )
        )

      while (true) {
        const { value, done } = await reader.read()
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
        const events = buffer.split('\n\n')
        buffer = events.pop() || ''
        for (const event of events) {
          const dataLine = event.split('\n').find((line) => line.startsWith('data: '))
          if (!dataLine) continue
          try {
            const data = JSON.parse(dataLine.slice(6))
            if (event.startsWith('event: token')) {
              streamedAnswer += data.text
              updateAssistant({ answer: streamedAnswer })
            } else if (event.startsWith('event: complete')) {
              updateAssistant({
                answer: data.answer || streamedAnswer,
                citations: data.citations || [],
                graph_nodes_traversed: data.graph_nodes_traversed || [],
                numerical_fidelity_passed: data.numerical_fidelity_passed,
                dashboard_payload: data.dashboard_payload || {},
                route_used: data.route_used || 'HYBRID',
              })
            }
          } catch {
            // Ignore malformed intermediate chunks
          }
        }
        if (done) break
      }
    } catch (error) {
      setMessages((current) => [
        ...current,
        { role: 'assistant', answer: `Error: ${error.message}`, citations: [], route_used: 'ERROR' },
      ])
    } finally {
      setLoading(false)
    }
  }

  function getRouteBadge(route) {
    if (!route) return null
    if (route === 'VECTOR_SEARCH') {
      return <span className="route-pill vector" title="Retrieved via Dense Vector Embeddings">📄 Vector Search</span>
    }
    if (route === 'GRAPH_TRAVERSAL') {
      return <span className="route-pill graph" title="Retrieved via Knowledge Graph Cypher Traversal">🕸️ Graph Traversal</span>
    }
    if (route === 'HYBRID') {
      return <span className="route-pill hybrid" title="Retrieved via Hybrid Vector + Knowledge Graph Blend">⚡ Hybrid Blend</span>
    }
    return <span className="route-pill">{route}</span>
  }

  return (
    <section className="chat-panel">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">Store Conversation · Short-Term Memory</span>
          <h2>{activeStoreName} <span className="store-pill">#{activeStoreId}</span></h2>
        </div>
        <div className="panel-chips">
          <span className="model-chip">Guarded Hybrid RAG</span>
        </div>
      </div>

      <div className="message-list">
        {messages.length === 0 && (
          <div className="empty-state">
            <span>01</span>
            <p>Ask anything about <strong>{activeStoreName}</strong> documents.</p>
            <small className="empty-sub">
              Dual-path ingestion routes numerical queries to Graph Traversal and narrative to Vector Search.
            </small>
          </div>
        )}
        {messages.map((message, index) => (
          <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
            <div className="message-header-row">
              <span className="message-label">{message.role === 'user' ? 'You' : 'Ledger Lens'}</span>
              {message.role === 'assistant' && getRouteBadge(message.route_used)}
            </div>
            {message.role === 'assistant' ? (
              <RichAnswer answer={message.answer} />
            ) : (
              <p>{message.answer}</p>
            )}
            {message.role === 'assistant' && (
              <>
                <DashboardResult payload={message.dashboard_payload} />
                <button className="inspect-button" onClick={() => onInspect(message)}>
                  Inspect evidence <span>↗</span>
                </button>
              </>
            )}
          </article>
        ))}
        {loading && <div className="typing">Routing query & synthesizing sources<span>...</span></div>}
        <div ref={messagesEndRef} />
      </div>

      <form className="prompt-bar" onSubmit={submit}>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={`Ask about ${activeStoreName} revenue, quarterly growth, or policies`}
          aria-label="Financial question"
        />
        <button type="submit" disabled={loading || !query.trim()} aria-label="Send question">
          Send <span>↗</span>
        </button>
      </form>
    </section>
  )
}
