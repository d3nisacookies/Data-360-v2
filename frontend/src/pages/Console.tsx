import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, type Overview, type StepState } from '../api'
import { useAuth } from '../auth'
import { ClientPicker, ConfidenceBar, lastClient, rememberClient, TopBar, useBorrowers } from '../components/Shell'
import { ErrorNote, RateChip, Spinner, toast } from '../components/ui'

const LOCK = <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><rect x="3" y="7" width="10" height="7" rx="1.5" /><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" /></svg>
const PHASES = [
  { id: 1, cls: 'p1', title: 'Assess & Improve', tag: 'Understand, assess, clean and normalise' },
  { id: 2, cls: 'p2', title: 'Improve & Plan', tag: 'Identify gaps, build confidence and prioritise' },
  { id: 3, cls: 'p3', title: 'Transform', tag: 'Execute the roadmap to an intelligent enterprise' },
]

export default function Console() {
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const { canEdit, user } = useAuth()
  const qc = useQueryClient()
  const list = useBorrowers()
  const fromUrl = sp.get('b') ? Number(sp.get('b')) : null
  const known = (id: number | null) => id !== null && !!list.data?.some(b => b.id === id)
  const bid = known(fromUrl) ? fromUrl : known(lastClient()) ? lastClient() : list.data?.[0]?.id ?? null
  useEffect(() => { if (bid) rememberClient(bid) }, [bid])
  const q = useQuery({ queryKey: ['overview', bid], queryFn: () => api.get<Overview>(`/borrowers/${bid}/overview`), enabled: !!bid })
  const O = q.data
  const pick = (id: number) => { rememberClient(id); nav(`/console?b=${id}`) }
  const reset = async () => {
    const name = list.data?.find(b => b.id === bid)?.name
    if (!bid || !window.confirm(`Reset ${name}? This clears every step result, the credit memo and Phases 2 and 3 for this client. Uploaded files are kept.`)) return
    try { await api.post(`/borrowers/${bid}/reset`); await qc.invalidateQueries(); toast(`${name} reset: start again from Phase 1`) } catch (e) { toast(String(e)) }
  }

  if (list.isLoading) return <Spinner />
  if (!list.data?.length) return (
    <div><TopBar sub="Three-phase data transformation framework" />
      <section className="panel"><div className="empty"><b>No data yet</b>
        <p className="hint" style={{ maxWidth: 520 }}>Upload data-dictionary exports from internal systems and record-level files from vendor feeds (Excel or CSV). Borrowers are recognised automatically from the files.</p>
        {canEdit && <Link to="/upload" className="btn primary">Upload your first files</Link>}</div></section></div>)

  return (
    <div>
      <TopBar back={{ to: '/', label: '← About' }} sub="Three-phase data transformation framework"
        right={<>{bid && user?.role === 'admin' && <button type="button" className="btn" onClick={reset}>Reset this client</button>}
          {bid && <Link className="btn report" to={`/b/${bid}/fix`}>Fix plan</Link>}<span className="dclient">Client <ClientPicker id={bid} onPick={pick} /></span></>} />
      <section className="dhero"><h1>From understanding the data landscape to trusted intelligence</h1>
        <p>Work through the phases in order. Each phase unlocks when the one before it is cleared.</p></section>
      <ErrorNote error={q.error} />
      {!O ? <Spinner /> : <>
        <div className="dkpis">{O.kpis.map(k => <div className="kpi" key={k.k}><div className={`v${k.sm ? ' sm' : ''}`}>{k.v}</div><div className="k">{k.k}</div></div>)}</div>
        <ol className="phases">
          {PHASES.map(P => {
            const open = !!O.gates.open[String(P.id)], done = P.id === 1 ? O.gates.p1 : P.id === 2 ? O.gates.p2 : O.gates.p3
            const steps = O.phases[P.id - 1].steps
            const nDone = steps.filter(s => s.done).length, pct = Math.round(nDone / steps.length * 100), started = nDone > 0 || steps.some(s => s.part)
            const go = (s?: string) => nav(P.id === 1 ? `/b/${bid}/p1/${s || 'source'}` : `/b/${bid}/p${P.id}/${s || ''}`)
            return (
              <li key={P.id} className={`phase ${P.cls}${open ? '' : ' locked'}`}>
                <div className="ph"><span className="k">Phase {P.id}</span><h2>{P.title}</h2><span className="ptag">{P.tag}</span></div>
                <div className="pst">{done ? <span className="chip ok">Cleared</span> : !open ? <span className="lock">{LOCK}Locked</span>
                  : started ? <span className="chip info">In progress</span> : P.id === 1 ? <span className="chip idle">Not started</span> : <span className="chip info">Unlocked</span>}
                  <div className="pbar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`Phase ${P.id} progress`}><i style={{ width: `${pct}%` }} /></div>
                  <span className="hint">{nDone} of {steps.length}</span></div>
                <ol>{steps.map(s => {
                  const inner = <><span className="sn">{s.done ? '✓' : s.n}</span><span><b>{s.t}</b><span className="hint">{s.d}</span></span></>
                  const cls = `st${s.done ? ' done' : s.part ? ' part' : ''}`
                  return open ? <li key={s.n}><button type="button" className={cls} onClick={() => go(s.go || s.k)}
                    style={{ display: 'grid', gridTemplateColumns: '28px minmax(0,1fr)', gap: 10, alignItems: 'start', padding: '10px 8px', borderRadius: 8, width: '100%', border: 0, background: 'none', color: 'inherit', textAlign: 'left' }}>{inner}</button></li>
                    : <li key={s.n} className={cls}>{inner}</li> })}</ol>
                <div className="pfoot"><span className="hint">{open ? (P.id === 1 ? (done ? 'Phase 2 is unlocked.' : 'Clears when all five steps are done and the credit memo is retained.')
                  : P.id === 2 ? (done ? 'Phase 3 is unlocked.' : 'Clears when all four steps are run and the roadmap is approved.') : done ? 'All phases complete.' : 'Clears when all four stages are completed.')
                  : P.id === 2 ? 'Unlocks when all five Phase 1 steps are done and the credit memo is retained.' : 'Unlocks when the Phase 2 roadmap is approved.'}</span>
                  {open ? <button type="button" className="btn primary" onClick={() => go()}>{started ? `Continue Phase ${P.id}` : `Start Phase ${P.id}`} →</button>
                    : <button type="button" className="btn" disabled>Locked</button>}</div>
              </li>)
          })}
        </ol>
        <section className="doutcome"><b>Outcome</b><span>Trusted data → consistent reporting → stronger insight → better business decisions → intelligent, continuously improving enterprise</span></section>
        <div style={{ marginTop: 18 }}><ConfidenceBar b={O.battery} name={O.borrower.name} /></div>
      </>}
      <AllBorrowers current={bid} onPick={pick} />
    </div>
  )
}

function StepCell({ s }: { s: StepState | null }) {
  if (!s) return <span className="chip idle">Not run</span>
  return s.stale ? <span className="chip warn" title={s.stale_reason || 'Newer files arrived'}>Out of date</span> : <span className="chip ok">Done</span>
}

function AllBorrowers({ current, onPick }: { current: number | null; onPick: (id: number) => void }) {
  const q = useBorrowers()
  const rows = q.data || []
  return (
    <section className="panel" style={{ marginTop: 18 }}>
      <h2>All borrowers <small>{rows.length} found in your files</small></h2>
      <div className="tblwrap flat"><table>
        <thead><tr><th>Borrower</th><th className="num">Sources</th><th className="num">Values</th><th>Confidence</th><th>Collector</th><th>Seeker</th><th>Assess</th><th>Clean</th><th>Normalise</th></tr></thead>
        <tbody>{rows.map(b => (
          <tr key={b.id} className={`click${b.id === current ? ' tot' : ''}`} onClick={() => onPick(b.id)}>
            <td><b>{b.name}</b>{b.facility_ids.length > 0 && <div className="hint mono">{b.facility_ids.join(' · ')}</div>}</td>
            <td className="num">{b.sources}</td><td className="num">{b.observations.toLocaleString()}</td>
            <td>{b.confidence ? <span className="row" style={{ gap: 6 }}><b>{b.confidence.score}</b><RateChip r={b.confidence.rating} /></span> : <span className="hint">Not assessed</span>}</td>
            <td><StepCell s={b.steps.collect} /></td><td><StepCell s={b.steps.seek} /></td>
            <td><StepCell s={b.steps.assess} /></td><td><StepCell s={b.steps.clean} /></td><td><StepCell s={b.steps.normalise} /></td>
          </tr>))}</tbody></table></div>
    </section>
  )
}
