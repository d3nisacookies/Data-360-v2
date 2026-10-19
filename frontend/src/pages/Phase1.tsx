import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, type AssessResult, type Battery as BatteryT, type BorrowerDetail, type CleanResult, type NormResult } from '../api'
import { Chip, ErrorNote, RateChip, Ring, Spinner, Table, toast, when } from '../components/ui'
import { Setup, Stale, useMeta, useStep } from '../components/steps'
import SourceStep from './SourceStep'
import MemoStep from './Memo'
import { ClientPicker, ConfidenceBar, ExecSummary, rememberClient, TopBar } from '../components/Shell'

const STEPS = [['source', 'Source'], ['assess', 'Assess'], ['clean', 'Clean'], ['normalise', 'Normalise'], ['memo', 'Credit memo']] as const
const TABS = [['collector', 'Collector', 'You choose where to look'], ['seeker', 'Seeker', 'You choose what to look for'], ['files', 'Sources & files', 'What was uploaded']] as const

export default function Phase1() {
  const { id, step = 'source' } = useParams()
  const bid = Number(id)
  const nav = useNavigate()
  const [sp, setSp] = useSearchParams()
  const [exec, setExec] = useState(false)
  const [fac, setFac] = useState('')
  const b = useQuery({ queryKey: ['borrower', bid], queryFn: () => api.get<BorrowerDetail>(`/borrowers/${bid}`) })
  const conf = useQuery({ queryKey: ['confidence', bid, b.data?.steps.assess?.run_id, b.data?.steps.normalise?.run_id], queryFn: () => api.get<BatteryT | null>(`/borrowers/${bid}/confidence`), enabled: !!b.data })
  useEffect(() => { rememberClient(bid); setExec(false) }, [bid])
  if (b.isLoading) return <Spinner />
  if (b.error || !b.data) return <ErrorNote error={b.error || 'Not found'} />
  const d = b.data
  const ok = (k: 'collect' | 'seek' | 'assess' | 'clean' | 'normalise') => !!d.steps[k] && !d.steps[k]!.stale
  const done = (k: string) => k === 'source' ? ok('collect') && ok('seek') : k === 'memo' ? false : ok(k as 'assess' | 'clean' | 'normalise')
  const memoOpen = ok('collect') && ok('seek') && ok('assess') && ok('clean') && ok('normalise')
  const tab = sp.get('tab') || 'collector'
  return (
    <div>
      <TopBar back={{ to: `/console?b=${bid}`, label: '← Dashboard' }} sub="Phase 1 · Assess & Improve · Credit Memo Acceleration"
        right={<><button type="button" className="btn report" onClick={() => setExec(true)}>Executive summary</button>
          <ol className="steps p1steps" aria-label="Phase 1 steps">
            {STEPS.map(([k, l], i) => (
              <li key={k} className={`${step === k ? 'on' : done(k) ? 'done' : ''}${k === 'memo' && !memoOpen ? ' locked' : ''}`} aria-current={step === k ? 'step' : undefined}>
                <button type="button" onClick={() => nav(`/b/${bid}/p1/${k}`)} title={k === 'memo' && !memoOpen ? 'Run Source, Assess, Clean and Normalise first' : undefined}>
                  <span className="n">{done(k) ? '✓' : i + 1}</span>{l}</button></li>))}
          </ol></>} />
      <section className="panel ctx" aria-label="Borrower information">
        <div className="f"><label className="lbl" htmlFor="client">Client name</label>
          <ClientPicker id={bid} onPick={x => nav(`/b/${x}/p1/${step}`)} />
          <span className="hint">{d.aliases.length ? `Also seen as ${d.aliases.join(', ')} · ` : ''}data {d.version}</span></div>
        <div className="f"><label className="lbl" htmlFor="facility">Client facility ID <em>Optional</em></label>
          <input type="text" id="facility" value={fac} onChange={e => setFac(e.target.value)} placeholder="Leave blank to cover everything for the client" />
          {d.facility_ids.length > 0 && <div className="idchips">{d.facility_ids.map(f => <button type="button" key={f} className="idchip" onClick={() => setFac(f)}>{f}</button>)}</div>}</div>
        <div className="f"><div className="lbl">{step === 'source' ? 'Data finder' : 'Data pack'}</div>
          {step === 'source' ? <div className="tabs" role="tablist" aria-label="Data finder" style={{ gridTemplateColumns: '1fr 1fr 1fr' }}>
            {TABS.map(([k, l, h], i) => <button key={k} type="button" role="tab" aria-selected={tab === k}
              onClick={() => setSp(k === 'collector' ? {} : { tab: k }, { replace: true })} style={i ? { borderLeft: '2px solid var(--accent)' } : undefined}>
              <b>{l}{(k === 'collector' && ok('collect')) || (k === 'seeker' && ok('seek')) ? ' ✓' : ''}</b><span>{h}</span></button>)}
          </div> : <div className="row"><DataPack bid={bid} name={d.name} /><Link className="btn" to={`/b/${bid}/fix`}>Fix plan</Link></div>}
        </div>
      </section>
      <ConfidenceBar b={conf.data} name={d.name} />
      {step === 'source' && <SourceStep d={d} />}
      {step !== 'source' && <div className="screenhead"><span className="crumb">Step {STEPS.findIndex(x => x[0] === step) + 1} · {STEPS.find(x => x[0] === step)?.[1]}</span>
        <h1>{({ assess: 'Assess the data', clean: 'Clean the data', normalise: 'Normalise the data', memo: 'Build the credit memo' } as Record<string, string>)[step]}</h1></div>}
      {step === 'assess' && <AssessStep bid={bid} d={d} />}
      {step === 'clean' && <CleanStep bid={bid} d={d} />}
      {step === 'normalise' && <NormStep bid={bid} d={d} />}
      {step === 'memo' && <MemoStep bid={bid} name={d.name} />}
      {exec && <ExecSummary bid={bid} name={d.name} facility={fac} onClose={() => setExec(false)} />}
    </div>
  )
}

function DataPack({ bid, name }: { bid: number; name: string }) {
  const [busy, setBusy] = useState(false)
  return <button className="btn" disabled={busy} onClick={async () => {
    setBusy(true)
    try { await api.download(`/borrowers/${bid}/export/datapack.xlsx`, `Data360 data pack - ${name}.xlsx`) } catch (e) { toast(String(e)) } finally { setBusy(false) }
  }}>{busy ? 'Preparing…' : 'Download data pack (.xlsx)'}</button>
}

/* ---------------- Assess ---------------- */
function AssessStep({ bid, d }: { bid: number; d: BorrowerDetail }) {
  const meta = useMeta()
  const { q, m } = useStep<AssessResult>(bid, 'assess')
  const [sel, setSel] = useState<string[] | null>(null)
  const [extra, setExtra] = useState<string[] | null>(null)
  const [ref, setRef] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  if (!meta.data) return <Spinner />
  const items = meta.data.assess
  const s = sel ?? q.data?.result.selected ?? Object.keys(items)
  const R = q.data?.result
  return (
    <div className="layout2">
      <Setup title="Assess data quality" items={items} sel={s} setSel={setSel} running={m.isPending}
        pick={meta.data.picks.assess} extra={extra ?? Object.keys(q.data?.result.crit || {})} setExtra={setExtra}
        onRun={() => m.mutate({ selected: s, extra: extra ?? Object.keys(q.data?.result.crit || {}), ref_date: ref || undefined }, { onSuccess: r => toast(`Confidence ${r.result.overall.score}/100`) })}
        hint={`Scores ${d.name}'s ${d.version.includes('cleaned') ? 'cleaned' : 'sourced'} data against each criterion, from the data itself.`}>
        <label className="f"><span className="lbl">Reference date for timeliness</span>
          <input type="date" value={ref} onChange={e => setRef(e.target.value)} /><span className="hint">Blank = {meta.data.reference_date}</span></label>
      </Setup>
      <div className="stack">
        <ErrorNote error={m.error || q.error} />
        <Stale r={q.data} label="Assess" />
        {!R ? <div className="panel"><div className="empty"><b>Not assessed yet</b><span className="hint">Choose criteria and run Assess.</span></div></div> : <>
          <section className="panel"><div className="pb ovr">
            <Ring score={R.overall.score} rating={R.overall.rating} />
            <div className="stack grow" style={{ gap: 6 }}>
              <div className="row"><h2>Data confidence for {R.borrower}</h2><RateChip r={R.overall.rating} /></div>
              {R.inputs && (!R.inputs.collector || !R.inputs.seeker) && <p className="hint warn">{!R.inputs.collector && !R.inputs.seeker ? 'Collector and Seeker' : !R.inputs.collector ? 'Collector' : 'Seeker'} not run: output coverage and identity attributes are not scored. <Link to={`/b/${bid}/p1/source${!R.inputs.collector ? '' : '?tab=seeker'}`}>Run it</Link></p>}
              {R.inputs?.scope && <p className="hint">Scope: {R.inputs.scope.length} sources chosen in the Collector.</p>}
              <p className="hint">Average of {R.selected.length} criteria on data {R.version}. High ≥ 85, Medium 60–84, Low &lt; 60.{R.overall.cap ? ` ${R.overall.cap}.` : ''} Reference date {R.ref_date}.</p>
              {R.stages.length > 1 && <div className="row">{R.stages.map((st, i) => <span key={st.key} className="row" style={{ gap: 6 }}>
                {i > 0 && <span aria-hidden>→</span>}<span className="hint">{st.label}</span><b>{st.score}</b></span>)}
                <span className={`delta ${R.stages[1].score! >= R.stages[0].score! ? 'up' : 'down'}`}>{R.stages[1].score! - R.stages[0].score! >= 0 ? '+' : ''}{R.stages[1].score! - R.stages[0].score!} after Clean</span></div>}
              {Object.keys(R.provider_flags).length > 0 && <p className="hint">Provider quality flags in the files: {Object.entries(R.provider_flags).map(([k, v]) => `${k} ${v}`).join(', ')} (used as extra evidence only).</p>}
            </div>
          </div></section>
          <div className="cards">{R.selected.map(k => { const v = R.dims[k]; const delta = v.before !== null && v.score !== null ? v.score - v.before : null
            return (
              <div key={k} className={`dcard ${v.rating}`}>
                <div className="dtop"><span className="dn">{k}</span><RateChip r={v.rating} /></div>
                <div className="dscore"><b>{v.score ?? '—'}</b><div className="bar"><i style={{ width: `${v.score ?? 0}%` }} /></div>
                  {delta !== null && delta !== 0 && <span className={`delta ${delta > 0 ? 'up' : 'down'}`}>{delta > 0 ? '+' : ''}{delta}</span>}</div>
                <p className="hint">{v.basis}</p>
                {v.issues.length ? <button className="linkbtn" aria-expanded={open === k} onClick={() => setOpen(open === k ? null : k)}>{open === k ? 'Hide' : 'Show'} {v.issues.length} issue{v.issues.length > 1 ? 's' : ''}</button> : <span className="hint ok">No issues</span>}
              </div>) })}</div>
          {open && R.dims[open] && <section className="panel"><div className="ph"><h2>{open} · {R.dims[open].issues.length} issues</h2><button className="linkbtn" onClick={() => setOpen(null)}>Close</button></div>
            <div className="pb"><Table head={['Issue', 'Where', 'Detail']} mono={[2]} rows={R.dims[open].issues.map(i => [i.issue, i.where, i.detail])} /></div></section>}
          {R.crit && Object.keys(R.crit).length > 0 && <section className="panel"><h2>Additional criteria <small>From the pick list</small></h2>
            <div className="tblwrap flat"><table><thead><tr><th>Criterion</th><th className="num">Score</th><th>Result</th><th>Basis</th><th>What's needed</th></tr></thead><tbody>
              {Object.entries(R.crit).map(([n, v]) => <tr key={n}><td><b>{n}</b><div className="hint">{v.cat}</div></td><td className="num">{v.score ?? '—'}</td>
                <td>{v.status === 'review' ? <Chip kind="info">Evidence · review</Chip> : v.status === 'none' ? <Chip kind="idle">No evidence</Chip> : <RateChip r={v.status as 'high' | 'med' | 'low'} />}</td>
                <td className="hint">{v.basis}</td><td className="hint">{v.needs || '—'}</td></tr>)}</tbody></table></div></section>}
          <GoldenTable g={R.golden} />
          <p><Link to={`/b/${bid}/p1/clean`} className="btn primary">Next: Clean →</Link></p>
        </>}
      </div>
    </div>
  )
}

function GoldenTable({ g }: { g: AssessResult['golden'] }) {
  const [show, setShow] = useState(false)
  const rows = Object.entries(g)
  return (
    <section className="panel">
      <div className="ph"><div><h2>Golden record</h2><p className="hint">The value Data360 relies on for each field, and why.</p></div>
        <button className="linkbtn" onClick={() => setShow(!show)} aria-expanded={show}>{show ? 'Hide' : `Show ${rows.length} fields`}</button></div>
      {show && <div className="pb"><Table head={['Field', 'Value', 'Source', 'Record', 'As of', 'Why', 'Agreeing sources']} mono={[1, 3]}
        rows={rows.map(([k, v]) => v ? [k.replace(/_/g, ' '), v.display, v.source, v.record, v.as_of || '—', v.why, String(v.support.length)] : [k.replace(/_/g, ' '), <span className="hint bad">Not held</span>, '', '', '', '', ''])} /></div>}
    </section>
  )
}

/* ---------------- Clean ---------------- */
function CleanStep({ bid, d }: { bid: number; d: BorrowerDetail }) {
  const meta = useMeta()
  const { q, m } = useStep<CleanResult>(bid, 'clean')
  const [sel, setSel] = useState<string[] | null>(null)
  const [tab, setTab] = useState<'esc' | 'trail' | 'crit'>('esc')
  const [extra, setExtra] = useState<string[] | null>(null)
  if (!meta.data) return <Spinner />
  const items = meta.data.clean
  const s = sel ?? q.data?.result.selected ?? Object.keys(items)
  const R = q.data?.result
  const S = R?.summary || {}
  const V = S['Validate critical information']
  return (
    <div className="layout2">
      <Setup title="Clean the data" items={items} sel={s} setSel={setSel} running={m.isPending}
        pick={meta.data.picks.clean} extra={extra ?? Object.keys(R?.picks || {})} setExtra={setExtra}
        onRun={() => m.mutate({ selected: s, extra: extra ?? Object.keys(R?.picks || {}) }, { onSuccess: r => toast(`Cleaned: ${r.result.log.length} changes logged`) })}
        hint={`Cleans the data sourced for ${d.name}. The originals are kept: the result is a new version (v1.1), and every change is logged.`} />
      <div className="stack">
        <ErrorNote error={m.error || q.error} />
        <Stale r={q.data} label="Clean" />
        {!R ? <div className="panel"><div className="empty"><b>Not cleaned yet</b><span className="hint">Choose actions and run Clean.</span></div></div> : <>
          <section className="panel"><div className="pb stack">
            <p><b>Data pack {R.version}</b> for {d.name}: {R.log.length} changes logged, {R.escalations.length} items escalated. v1.0 (as sourced) retained.
              {q.data?.by && <span className="hint"> Run by {q.data.by}, {when(q.data.at)}.</span>}</p>
            <div className="kpis">
              <div className="kpi"><div className="v">{S['Remove duplicates']?.n ?? '—'}</div><div className="k">Duplicates removed</div></div>
              <div className="kpi"><div className="v">{S['Correct errors']?.n ?? '—'}</div><div className="k">Errors corrected</div></div>
              <div className="kpi"><div className="v">{V ? `${V.n}/${V.rows!.length}` : '—'}</div><div className="k">Critical fields validated</div></div>
              <div className="kpi"><div className="v">{S['Reconcile conflicting records']?.n ?? '—'}</div><div className="k">Values reconciled</div></div>
              <div className="kpi"><div className="v">{R.escalations.length}</div><div className="k">Escalated</div></div>
            </div>
            <ul style={{ margin: 0, paddingLeft: 18 }}>{Object.entries(S).map(([k, v]) => <li key={k}><b>{k}:</b> <span className="hint">{v.text}</span></li>)}</ul>
            {q.data && !q.data.stale && <div className="callout ok">Assess now scores the cleaned data. <Link to={`/b/${bid}/p1/assess`}>Re-run Assess</Link> to see the change in confidence.</div>}
          </div></section>
          <section className="panel">
            <div className="ph"><div className="row" role="tablist">
              {([['esc', `Escalations (${R.escalations.length})`], ['crit', 'Critical fields'], ['trail', `Audit trail (${R.log.length})`]] as const).map(([k, l]) =>
                <button key={k} role="tab" aria-selected={tab === k} className={`btn small${tab === k ? ' primary' : ''}`} onClick={() => setTab(k)}>{l}</button>)}
            </div></div>
            <div className="pb">
              {tab === 'esc' && <Table head={['Item', 'Why', 'Owner', 'Due']} mono={[3]} empty="Nothing to escalate." rows={R.escalations.map(e => [e.item, e.why, e.owner, e.due])} />}
              {tab === 'crit' && (V ? <Table head={['Field', 'Golden value', 'Golden source', 'Status', 'Detail']} mono={[1]}
                rows={V.rows!.map(r => [r.field, r.golden || '—', r.source || '—', <Chip kind={r.status === 'Validated' ? 'ok' : r.status === 'Failed' ? 'bad' : 'idle'}>{r.status}</Chip>, r.detail])} /> : <p className="hint">Validation was not selected.</p>)}
              {tab === 'trail' && <Table head={['#', 'Action', 'Record', 'Field', 'Original', 'New', 'Reason', 'Source']} mono={[2, 4, 5]}
                rows={R.log.map(l => [l.n, l.action, l.record, l.field, l.from, l.to, l.reason, l.source])} />}
            </div>
          </section>
          {R.picks && Object.keys(R.picks).length > 0 && <section className="panel"><h2>Additional actions <small>From the pick list</small></h2>
            <div className="tblwrap flat"><table><thead><tr><th>Action</th><th>Result</th></tr></thead><tbody>
              {Object.entries(R.picks).map(([n, v]) => <tr key={n}><td><b>{n}</b></td><td>{v.text}</td></tr>)}</tbody></table></div></section>}
          <p><Link to={`/b/${bid}/p1/normalise`} className="btn primary">Next: Normalise →</Link></p>
        </>}
      </div>
    </div>
  )
}

/* ---------------- Normalise ---------------- */
function NormStep({ bid, d }: { bid: number; d: BorrowerDetail }) {
  const meta = useMeta()
  const { q, m } = useStep<NormResult>(bid, 'normalise')
  const [sel, setSel] = useState<string[] | null>(null)
  const [open, setOpen] = useState<string | null>('Metrics')
  const [extra, setExtra] = useState<string[] | null>(null)
  if (!meta.data) return <Spinner />
  const items = meta.data.normalise
  const s = sel ?? q.data?.result.selected ?? Object.keys(items)
  const R = q.data?.result
  return (
    <div className="layout2">
      <Setup title="Normalise definitions" items={items} sel={s} setSel={setSel} running={m.isPending}
        pick={meta.data.picks.normalise} extra={extra ?? Object.keys(R?.picks || {})} setExtra={setExtra}
        onRun={() => m.mutate({ selected: s, extra: extra ?? Object.keys(R?.picks || {}) }, { onSuccess: () => toast('Definitions published') })}
        hint={`Builds common definitions for ${d.name} from the ${d.version.includes('cleaned') ? 'cleaned data pack and its golden record' : 'sourced data (Clean not run)'}.`} />
      <div className="stack">
        <ErrorNote error={m.error || q.error} />
        <Stale r={q.data} label="Normalise" />
        {!R ? <div className="panel"><div className="empty"><b>Not normalised yet</b></div></div> : <>
          <div className="cards">{Object.entries(R.out).map(([k, v]) => (
            <div key={k} className="dcard"><div className="dtop"><span className="dn">{k}</span><Chip kind="ok">Defined</Chip></div>
              <p className="hint">{v.text}</p><button className="linkbtn" aria-expanded={open === k} onClick={() => setOpen(open === k ? null : k)}>{open === k ? 'Hide' : 'Show'} definitions</button></div>))}</div>
          {open && R.out[open] && <section className="panel"><div className="ph"><h2>{open}</h2><span className="hint">Data {R.version}</span></div>
            <div className="pb"><Table head={R.out[open].head} rows={R.out[open].rows.map(r => open === 'KPIs'
              ? [...r.slice(0, 6), <Chip kind={r[6] === 'g' ? 'ok' : r[6] === 'a' ? 'warn' : r[6] === 'r' ? 'bad' : 'idle'}>{({ g: 'Green', a: 'Amber', r: 'Red', na: 'No data' } as Record<string, string>)[String(r[6])]}</Chip>]
              : r)} mono={open === 'Metrics' ? [4] : []} /></div></section>}
          {R.picks && Object.keys(R.picks).length > 0 && <section className="panel"><h2>Additional definitions <small>From the pick list</small></h2>
            <div className="tblwrap flat"><table><thead><tr><th>Item</th><th>Result</th></tr></thead><tbody>
              {Object.entries(R.picks).map(([n, v]) => <tr key={n}><td><b>{n}</b></td><td>{v.text}</td></tr>)}</tbody></table></div></section>}
          <p><Link to={`/b/${bid}/p1/memo`} className="btn primary">Continue to Credit memo →</Link></p>
        </>}
      </div>
    </div>
  )
}
