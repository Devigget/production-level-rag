import { useRef, useState } from 'react'

export default function Upload({ onUploaded }) {
  const inputRef = useRef(null)
  const [busy, setBusy] = useState(false)

  async function upload(file) {
    if (!file) return
    setBusy(true)
    const formData = new FormData()
    formData.append('file', file)
    try {
      const response = await fetch('/api/upload', { method: 'POST', body: formData })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Upload failed')
      onUploaded(`${payload.filename} indexed · ${payload.total_chunks} chunk${payload.total_chunks === 1 ? '' : 's'}`)
    } catch (error) {
      onUploaded(error.message)
    } finally {
      setBusy(false)
    }
  }

  return <div className="upload-widget"><div className="widget-heading"><span className="section-kicker">Context library</span><span className="file-count">PDF · XLSX · CSV</span></div><button className="drop-zone" onClick={() => inputRef.current?.click()} disabled={busy}><span className="upload-icon">↑</span><strong>{busy ? 'Indexing...' : 'Add a report'}</strong><small>Drop or browse financial files</small></button><input ref={inputRef} type="file" hidden accept=".pdf,.xlsx,.csv,.png,.jpeg" onChange={(event) => upload(event.target.files?.[0])} /></div>
}
