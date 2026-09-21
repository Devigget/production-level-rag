function formatValue(value) {
  if (typeof value !== 'number') return value || 'Not available'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value)
}

function shortPeriod(period) {
  return String(period || '').replace('_', ' ')
}

export default function DashboardResult({ payload }) {
  const rows = payload?.rows || []
  if (!rows.length) return null

  const values = rows.map((row) => row.value).filter((value) => typeof value === 'number')
  const maximum = Math.max(...values, 1)
  const latest = rows[rows.length - 1]
  const first = rows[0]
  const change = values.length > 1 ? values[values.length - 1] - values[0] : null
  const changePercent = change !== null && values[0] !== 0 ? (change / values[0]) * 100 : null

  return (
    <section className="dashboard-result" aria-label="Financial dashboard result">
      <div className="dashboard-result-heading">
        <div>
          <span className="section-kicker">Dashboard result</span>
          <h3>{latest.metric || 'Financial measure'}</h3>
        </div>
        <span className="result-badge"><span /> Source-backed</span>
      </div>

      <div className="kpi-grid">
        <div className="kpi-card kpi-primary">
          <span>Latest value</span>
          <strong>{formatValue(latest.value)}</strong>
          <small>{shortPeriod(latest.period)}</small>
        </div>
        <div className="kpi-card">
          <span>Change</span>
          <strong className={change >= 0 ? 'positive' : 'negative'}>
            {change === null ? '—' : `${change >= 0 ? '+' : ''}${formatValue(change)}`}
          </strong>
          <small>{changePercent === null ? 'One reported period' : `${changePercent >= 0 ? '+' : ''}${changePercent.toFixed(1)}% across results`}</small>
        </div>
      </div>

      <div className="trend-panel">
        <div className="trend-header"><span>Financial records</span><span>{rows.length} record{rows.length === 1 ? '' : 's'}</span></div>
        <div className="dashboard-table" role="table" aria-label="Financial records">
          <div className="dashboard-table-row dashboard-table-header" role="row">
            <span>Period</span><span>Value</span><span>Source</span>
          </div>
          {rows.map((row) => (
            <div className="dashboard-table-row" role="row" key={`table-${row.citation_id || `${row.metric}-${row.period}`}`}>
              <span>{shortPeriod(row.period)}</span>
              <strong>{formatValue(row.value)}</strong>
              <span title={row.source_file}>{row.source_file || 'Indexed record'}</span>
            </div>
          ))}
        </div>
        <div className="trend-header trend-header-spaced"><span>Relative value view</span><span>Scaled to largest record</span></div>
        <div className="trend-list">
          {rows.map((row) => (
            <div className="trend-row" key={row.citation_id || `${row.metric}-${row.period}`}>
              <div className="trend-label"><strong>{shortPeriod(row.period)}</strong><span>{row.source_file}</span></div>
              <div className="trend-track"><span style={{ width: `${Math.max(7, ((row.value || 0) / maximum) * 100)}%` }} /></div>
              <strong className="trend-value">{formatValue(row.value)}</strong>
            </div>
          ))}
        </div>
      </div>

      <div className="dashboard-footnote">
        <span>↳</span>
        <p>Values are retrieved from indexed financial records. <strong>{first.source_file}</strong> is available in the evidence trail.</p>
      </div>
    </section>
  )
}