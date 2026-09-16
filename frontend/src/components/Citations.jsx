export default function Citations({ message, onClose }) {
  if (!message) return <aside className="evidence-drawer empty-drawer"><span className="drawer-index">03</span><p>Select an answer to inspect its evidence.</p></aside>

  return (
    <aside className="evidence-drawer">
      <div className="drawer-heading"><div><span className="section-kicker">Evidence</span><h2>Source trail</h2></div><button className="close-button" onClick={onClose} aria-label="Close evidence">×</button></div>
      <div className="fidelity"><span className="checkmark">✓</span><div><strong>{message.numerical_fidelity_passed ? 'Numerically grounded' : 'Needs verification'}</strong><p>Output guardrail result</p></div></div>
      <div className="citation-list">
        {(message.citations || []).length === 0 && <p className="muted">No source citations returned.</p>}
        {(message.citations || []).map((citation, index) => <div className="citation" key={citation.source_id || index}><span className="citation-number">{String(index + 1).padStart(2, '0')}</span><div><strong>{citation.source_file || 'Retrieved context'}</strong><p>{citation.snippet}</p></div></div>)}
      </div>
      <div className="traversal"><span>Graph traversal</span><strong>{(message.graph_nodes_traversed || []).join(' → ') || 'No graph hops'}</strong></div>
    </aside>
  )
}
