import { useCallback, useEffect, useState } from 'react'
import Chat from './components/Chat'
import Citations from './components/Citations'
import Sidebar from './components/Sidebar'
import Upload from './components/Upload'

export default function App() {
  const [stores, setStores] = useState([])
  const [activeStoreId, setActiveStoreId] = useState(() => {
    return localStorage.getItem('activeStoreId') || 'b23f1806'
  })
  const [documents, setDocuments] = useState([])
  const [selectedMessage, setSelectedMessage] = useState(null)
  const [uploadStatus, setUploadStatus] = useState('')

  const handleSelectStore = (storeId) => {
    setActiveStoreId(storeId)
    localStorage.setItem('activeStoreId', storeId)
    const target = stores.find((s) => s.id === storeId)
    if (target && target.documents) {
      setDocuments(target.documents)
    }
  }

  // Fetch all stores
  const loadStores = useCallback(async () => {
    try {
      const res = await fetch('/api/stores')
      if (res.ok) {
        const list = await res.json()
        setStores(list)
        if (list.length > 0) {
          const saved = localStorage.getItem('activeStoreId')
          if (saved && list.find((s) => s.id === saved)) {
            setActiveStoreId(saved)
          } else if (!list.find((s) => s.id === activeStoreId)) {
            const fallbackId = list.find((s) => s.id === 'b23f1806') ? 'b23f1806' : list[0].id
            setActiveStoreId(fallbackId)
            localStorage.setItem('activeStoreId', fallbackId)
          }
        }
      }
    } catch (err) {
      console.error('Failed to load stores:', err)
    }
  }, [activeStoreId])

  // Fetch documents for active store
  const loadDocuments = useCallback(async (storeId) => {
    try {
      const res = await fetch(`/api/stores/${storeId}/documents`)
      if (res.ok) {
        const docs = await res.json()
        setDocuments(docs)
      }
    } catch (err) {
      console.error('Failed to load store documents:', err)
    }
  }, [])

  useEffect(() => {
    loadStores()
  }, [loadStores])

  useEffect(() => {
    if (activeStoreId) {
      loadDocuments(activeStoreId)
    }
  }, [activeStoreId, loadDocuments])

  const activeStore = stores.find((s) => s.id === activeStoreId) || {
    id: 'default',
    name: 'Main Ledger',
  }

  async function handleCreateStore(name, description) {
    try {
      const res = await fetch('/api/stores', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, description }),
      })
      if (res.ok) {
        const newStore = await res.json()
        await loadStores()
        setActiveStoreId(newStore.id)
      }
    } catch (err) {
      console.error('Create store failed:', err)
    }
  }

  async function handleDeleteStore(storeId) {
    try {
      const res = await fetch(`/api/stores/${storeId}`, { method: 'DELETE' })
      if (res.ok) {
        setActiveStoreId('default')
        await loadStores()
      }
    } catch (err) {
      console.error('Delete store failed:', err)
    }
  }

  async function handleClearChat() {
    if (confirm(`Clear conversation memory for store "${activeStore.name}"?`)) {
      try {
        await fetch(`/api/stores/${activeStoreId}/clear-chat`, { method: 'POST' })
        // Force refresh chat by toggling storeId briefly or triggering child reload
        setActiveStoreId((prev) => prev)
        window.location.reload()
      } catch (err) {
        console.error('Clear chat failed:', err)
      }
    }
  }

  function handleUploadComplete(statusMsg) {
    setUploadStatus(statusMsg)
    loadDocuments(activeStoreId)
    loadStores()
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-mark">LL</div>
        <div>
          <p className="eyebrow">Enterprise Multi-Modal Graph + Vector RAG</p>
          <h1>Ledger Lens</h1>
        </div>
        <div className="topbar-actions">
          <div className="store-indicator">
            <span className="live-dot" />
            <span>Store: <strong>{activeStore.name}</strong></span>
          </div>
          <a
            className="dashboard-link"
            href="http://localhost:3001/d/financial-rag-showcase/financial-rag-showcase"
            target="_blank"
            rel="noreferrer"
          >
            Open Grafana <span>↗</span>
          </a>
          <div className="status-dot">
            <span /> API ready
          </div>
        </div>
      </header>

      <section className="workspace">
        <Sidebar
          stores={stores}
          activeStoreId={activeStoreId}
          onSelectStore={handleSelectStore}
          onCreateStore={handleCreateStore}
          onDeleteStore={handleDeleteStore}
          documents={documents.length > 0 ? documents : (activeStore?.documents || [])}
          onClearChat={handleClearChat}
        />

        <div className="center-pane">
          <div className="upload-container">
            <Upload
              activeStoreId={activeStoreId}
              activeStoreName={activeStore.name}
              onUploaded={handleUploadComplete}
            />
            {uploadStatus && (
              <div className="upload-status-row">
                <span className="upload-status-text">{uploadStatus}</span>
                <button
                  type="button"
                  className="upload-status-dismiss"
                  onClick={() => setUploadStatus('')}
                  title="Dismiss notification"
                >
                  ×
                </button>
              </div>
            )}
          </div>
          <Chat
            key={activeStoreId}
            activeStoreId={activeStoreId}
            activeStoreName={activeStore.name}
            onInspect={setSelectedMessage}
          />
        </div>

        <Citations message={selectedMessage} onClose={() => setSelectedMessage(null)} />
      </section>
    </main>
  )
}
