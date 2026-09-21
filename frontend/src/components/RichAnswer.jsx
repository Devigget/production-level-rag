function renderInline(text, keyPrefix = '') {
  const parts = text.split(/(\*\*[^*]+\*\*|\[[^\]]+:document\])/g)
  return parts.map((part, index) => {
    const key = `${keyPrefix}-${index}`
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={key}>{part.slice(2, -2)}</strong>
    }
    if (/^\[[^\]]+:document\]$/.test(part)) {
      return <span className="inline-citation" key={key}>{part.slice(1, -10)}</span>
    }
    return part
  })
}

function parseInvoice(line) {
  const match = line.match(/^\s*(\d+)\.\s+\*\*(.+?)\*\*\s+\((.+?)\)\s+[–-]\s+(.+?)(?:\s+\[[^\]]+:document\])?$/)
  if (!match) return null
  const [_, number, invoice, details, amount] = match
  const detailParts = details.split(',').map((part) => part.trim())
  return { number, invoice, vendor: detailParts[0] || '', department: detailParts.slice(1).join(', '), amount }
}

export default function RichAnswer({ answer = '' }) {
  const lines = answer.split(/\r?\n/)
  const blocks = []
  let invoiceRows = []

  const flushInvoices = () => {
    if (!invoiceRows.length) return
    blocks.push(
      <div className="invoice-list" key={`invoices-${blocks.length}`}>
        <div className="invoice-list-header"><span>Invoice</span><span>Vendor / department</span><span>Amount</span></div>
        {invoiceRows.map((row) => (
          <div className="invoice-row" key={`${row.number}-${row.invoice}`}>
            <div><span className="invoice-number">{row.number.padStart(2, '0')}</span><strong>{row.invoice}</strong></div>
            <div><strong>{row.vendor}</strong><small>{row.department}</small></div>
            <strong className="invoice-amount">{row.amount}</strong>
          </div>
        ))}
      </div>,
    )
    invoiceRows = []
  }

  lines.forEach((line, index) => {
    const invoice = parseInvoice(line)
    if (invoice) {
      invoiceRows.push(invoice)
      return
    }
    flushInvoices()
    if (!line.trim()) return
    if (/^#{1,3}\s/.test(line)) {
      blocks.push(<h3 className="answer-heading" key={`heading-${index}`}>{renderInline(line.replace(/^#{1,3}\s+/, ''), `heading-${index}`)}</h3>)
      return
    }
    blocks.push(<p key={`paragraph-${index}`}>{renderInline(line, `paragraph-${index}`)}</p>)
  })
  flushInvoices()

  return <div className="rich-answer">{blocks}</div>
}