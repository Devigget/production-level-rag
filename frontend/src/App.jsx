import { useState } from 'react'
import Chat from './components/Chat'
import Citations from './components/Citations'
import Upload from './components/Upload'

export default function App() {
  const [selectedMessage, setSelectedMessage] = useState(null)
  const [uploadStatus, setUploadStatus] = useState('')

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-mark">LL</div>
        <div>
          <p className="eyebrow">Financial intelligence workspace</p>
          <h1>Ledger Lens</h1>
        </div>
        <div className="topbar-actions">
          <a className="dashboard-link" href="http://localhost:3001/d/financial-rag-showcase/financial-rag-showcase" target="_blank" rel="noreferrer">Open Grafana <span>↗</span></a>
          <div className="status-dot"><span /> API ready</div>
        </div>
      </header>
      <section className="workspace">
        <aside className="sidebar">
          <Upload onUploaded={setUploadStatus} />
          {uploadStatus && <p className="upload-status">{uploadStatus}</p>}
          <div className="sidebar-note">
            <span className="note-label">Focus</span>
            <strong>Trace every figure.</strong>
            <p>Ask questions about uploaded reports and inspect the source behind each answer.</p>
          </div>
        </aside>
        <Chat onInspect={setSelectedMessage} />
        <Citations message={selectedMessage} onClose={() => setSelectedMessage(null)} />
      </section>
    </main>
  )
}
