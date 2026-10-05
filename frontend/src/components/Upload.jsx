import { useRef, useState } from 'react'

export default function Upload({ activeStoreId = 'default', activeStoreName = 'Main Ledger', onUploaded }) {
  const inputRef = useRef(null)
  const [busy, setBusy] = useState(false)
  const [isDragOver, setIsDragOver] = useState(false)

  async function upload(file) {
    if (!file) return
    setBusy(true)
    const formData = new FormData()
    formData.append('file', file)
    formData.append('store_id', activeStoreId)
    try {
      const response = await fetch('/api/upload', { method: 'POST', body: formData })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Upload failed')
      onUploaded(
        `✓ ${payload.filename} indexed into [${activeStoreName}] · ${payload.total_chunks} chunk${payload.total_chunks === 1 ? '' : 's'}`
      )
    } catch (error) {
      onUploaded(`✕ Upload failed: ${error.message}`)
    } finally {
      setBusy(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  function handleDrop(e) {
    e.preventDefault()
    setIsDragOver(false)
    const file = e.dataTransfer?.files?.[0]
    if (file) upload(file)
  }

  return (
    <div className="upload-widget">
      <button
        className={`drop-zone ${isDragOver ? 'drag-over' : ''} ${busy ? 'busy' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault()
          setIsDragOver(true)
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        disabled={busy}
        type="button"
        title="Drop or click to upload files"
      >
        <div className="drop-zone-main">
          <span className="upload-icon">↑</span>
          <div className="drop-zone-info">
            <strong>{busy ? 'Ingesting into Vector + Knowledge Graph...' : `Upload Documents to [${activeStoreName}]`}</strong>
            <small>Drag & drop or browse · XLSX, XLS, CSV, PDF, DOCX, TXT, PNG, JPG</small>
          </div>
        </div>
        <div className="drop-zone-action">
          <span className="browse-badge">{busy ? 'Processing...' : 'Browse File'}</span>
        </div>
      </button>
      <input
        ref={inputRef}
        type="file"
        hidden
        accept=".pdf,.xlsx,.xls,.csv,.docx,.txt,.png,.jpg,.jpeg"
        onChange={(event) => upload(event.target.files?.[0])}
      />
    </div>
  )
}

