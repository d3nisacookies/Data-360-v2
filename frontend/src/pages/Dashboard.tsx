import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { api, type BorrowerRow, type StepState } from '../api'
import { useAuth } from '../auth'
import { ErrorNote, RateChip, Spinner } from '../components/ui'

function StepCell({ s }: { s: StepState | null }) {
  if (!s) return <span className="chip idle">Not run</span>
  return s.stale ? <span className="chip warn" title={s.stale_reason || 'Newer files arrived'}>Out of date</span> : <span className="chip ok">Done</span>
}

export default function Dashboard() {
  const { canEdit } = useAuth()
  const nav = useNavigate()
  const q = useQuery({ queryKey: ['borrowers'], queryFn: () => api.get<BorrowerRow[]>('/borrowers') })
  const rows = q.data || []
  return (
    <div className="stack">
      <section className="panel">
        <div className="pb stack">
          <div className="spread">
            <div className="stack" style={{ gap: 6, maxWidth: 760 }}>
              <h1>Get credit-memo data you can trust</h1>
              <p>Banks keep borrower data in many systems and vendor feeds, and they rarely agree. Data360 reads your files,
                finds what is missing, wrong, stale or conflicting, fixes what it safely can with a full audit trail, and tells
                you how far you can rely on the result.</p>
            </div>
            {canEdit && <Link to="/upload" className="btn primary">Upload files</Link>}
          </div>
          <div className="phases">
            <div className="phase p1"><span className="pn">Phase 1 · Prepare</span><b>Source → Assess → Clean → Normalise → Credit memo</b>
              <span className="hint">Live: upload files, score data quality, clean with an audit trail, standard definitions. Credit memo drafting is next.</span></div>
            <div className="phase p2 locked"><span className="pn">Phase 2 · Steps 6–9</span><b>Coming in a later milestone</b>
              <span className="hint">Moved over from the demo console after Phase 1.</span></div>
            <div className="phase p3 locked"><span className="pn">Phase 3 · Steps 10–13</span><b>Coming in a later milestone</b>
              <span className="hint">Stabilise, standardise and transform, with project plans.</span></div>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="ph"><h2>Borrowers</h2><span className="hint">{rows.length ? `${rows.length} borrowers found in your files` : ''}</span></div>
        {q.isLoading ? <div className="pb"><Spinner /></div> : q.error ? <div className="pb"><ErrorNote error={q.error} /></div> : !rows.length ? (
          <div className="empty">
            <b>No data yet</b>
            <p className="hint" style={{ maxWidth: 520 }}>Upload data-dictionary exports from internal systems and record-level files from vendor feeds
              (Excel or CSV). Borrowers are recognised automatically from the files.</p>
            {canEdit && <Link to="/upload" className="btn primary">Upload your first files</Link>}
          </div>
        ) : (
          <div className="tblwrap" style={{ border: 0, borderRadius: 0 }}>
            <table>
              <thead><tr><th>Borrower</th><th className="num">Sources</th><th className="num">Values</th><th>Confidence</th><th>Assess</th><th>Clean</th><th>Normalise</th></tr></thead>
              <tbody>
                {rows.map(b => (
                  <tr key={b.id} className="click" onClick={() => nav(`/borrowers/${b.id}`)}>
                    <td><Link to={`/borrowers/${b.id}`} onClick={e => e.stopPropagation()}><b>{b.name}</b></Link>
                      {b.facility_ids.length > 0 && <div className="hint mono">{b.facility_ids.join(' · ')}</div>}</td>
                    <td className="num">{b.sources}</td>
                    <td className="num">{b.observations.toLocaleString()}</td>
                    <td>{b.confidence ? <span className="row" style={{ gap: 6 }}><b>{b.confidence.score}</b><RateChip r={b.confidence.rating} /></span> : <span className="hint">Not assessed</span>}</td>
                    <td><StepCell s={b.steps.assess} /></td>
                    <td><StepCell s={b.steps.clean} /></td>
                    <td><StepCell s={b.steps.normalise} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
