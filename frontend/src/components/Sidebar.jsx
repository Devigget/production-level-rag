import { useState } from 'react'

export default function Sidebar({
  stores = [],
  activeStoreId,
  onSelectStore,
  onCreateStore,
  onDeleteStore,
  documents = [],
  onClearChat,
}) {
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newStoreName, setNewStoreName] = useState('')
  const [newStoreDesc, setNewStoreDesc] = useState('')
  const [creating, setCreating] = useState(false)
  const [docsExpanded, setDocsExpanded] = useState(true)

  async function handleCreate(e) {
    e.preventDefault()
    if (!newStoreName.trim() || creating) return
    setCreating(true)
    try {
      await onCreateStore(newStoreName.trim(), newStoreDesc.trim())
      setNewStoreName('')
      setNewStoreDesc('')
      setShowCreateModal(false)
    } finally {
      setCreating(false)
    }
  }

  function getFileIcon(type = '') {
    const ext = type.toLowerCase()
    if (ext.includes('xls') || ext.includes('csv')) return '📊'
    if (ext.includes('pdf')) return '📕'
    if (ext.includes('doc')) return '📝'
    if (ext.includes('png') || ext.includes('jpg') || ext.includes('jpeg')) return '🖼️'
    return '📄'
  }

  return (
    <aside className="sidebar store-sidebar">
      {/* Sidebar Header & New Store Action */}
      <div className="sidebar-header">
        <div className="sidebar-title-row">
          <span className="sidebar-icon">🏬</span>
          <div>
            <span className="section-kicker">Workspace</span>
            <h3>Store Contexts</h3>
          </div>
        </div>
        <button
          className="new-store-button"
          onClick={() => setShowCreateModal(true)}
          title="Create New Store Context"
          aria-label="Create Store"
        >
          <span>+</span> New Store
        </button>
      </div>

      {/* Store Tabs List */}
      <div className="store-tabs-container">
        <div className="store-tabs-label">Active Stores ({stores.length})</div>
        <div className="store-tabs-list">
          {stores.map((store) => {
            const isActive = store.id === activeStoreId
            const docCount = store.documents?.length || 0
            return (
              <div
                key={store.id}
                className={`store-tab ${isActive ? 'active' : ''}`}
                onClick={() => onSelectStore(store.id)}
                role="button"
                tabIndex={0}
              >
                <div className="store-tab-main">
                  <div className="store-tab-title-row">
                    <span className="store-dot" />
                    <strong className="store-name">{store.name}</strong>
                  </div>
                  <div className="store-tab-meta">
                    <span className="store-doc-badge">{docCount} {docCount === 1 ? 'doc' : 'docs'}</span>
                    <span className="store-id-tag">#{store.id}</span>
                  </div>
                </div>
                {store.id !== 'default' && (
                  <button
                    className="delete-store-btn"
                    onClick={(e) => {
                      e.stopPropagation()
                      if (confirm(`Delete store "${store.name}" and its data?`)) {
                        onDeleteStore(store.id)
                      }
                    }}
                    title="Delete Store"
                  >
                    ×
                  </button>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Expandable Document Drawer for Active Store */}
      <div className="store-docs-section">
        <div
          className="store-docs-header"
          onClick={() => setDocsExpanded(!docsExpanded)}
          role="button"
          tabIndex={0}
        >
          <span className="section-kicker">Store Library ({documents.length})</span>
          <span className="toggle-arrow">{docsExpanded ? '▼' : '▶'}</span>
        </div>

        {docsExpanded && (
          <div className="store-docs-list">
            {documents.length === 0 ? (
              <p className="no-docs-hint">No files in this store. Upload reports below.</p>
            ) : (
              documents.map((doc) => (
                <div className="store-doc-item" key={doc.doc_id}>
                  <span className="doc-type-icon">{getFileIcon(doc.file_type)}</span>
                  <div className="doc-details">
                    <span className="doc-filename" title={doc.filename}>{doc.filename}</span>
                    <span className="doc-meta-sub">
                      {doc.total_chunks} chunks · {doc.uploaded_at?.split(' ')[1] || 'Today'}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Store Chat Actions */}
      <div className="store-actions-bar">
        <button
          className="clear-chat-btn"
          onClick={onClearChat}
          title="Clear conversation history for this store"
        >
          🗑️ Clear Store Chat
        </button>
      </div>

      {/* Create Store Modal */}
      {showCreateModal && (
        <div className="modal-backdrop" onClick={() => setShowCreateModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h4>Create New Store Context</h4>
              <button className="modal-close" onClick={() => setShowCreateModal(false)}>×</button>
            </div>
            <form onSubmit={handleCreate}>
              <div className="form-group">
                <label>Store Name *</label>
                <input
                  type="text"
                  placeholder="e.g. European Operations, Q2 Retail"
                  value={newStoreName}
                  onChange={(e) => setNewStoreName(e.target.value)}
                  autoFocus
                  required
                />
              </div>
              <div className="form-group">
                <label>Description (Optional)</label>
                <textarea
                  placeholder="Notes about this store's scope and entities"
                  value={newStoreDesc}
                  onChange={(e) => setNewStoreDesc(e.target.value)}
                  rows={2}
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn-cancel" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-create" disabled={creating || !newStoreName.trim()}>
                  {creating ? 'Creating...' : 'Create Store'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </aside>
  )
}
