import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, NavLink, useParams } from 'react-router-dom'
import { api, type AssessResult, type BorrowerDetail, type CleanResult, type Meta, type NormResult, type Run, type Steps } from '../api'
import { useAuth } from '../auth'
import { Chip, ErrorNote, RateChip, Ring, Spinner, Table, toast, when } from '../components/ui'

const STEPS = [['source', 'Source'], ['assess', 'Assess'], ['clean', 'Clean'], ['normalise', 'Normalise']] as const

export default function Borrower() {
  const { id, step = 'source' } = useParams()
  const bid = Number(id)
  const b = useQuery({ queryKey: ['borrower', bid], queryFn: () => api.get<BorrowerDetail>(`/borrowers/${bid}`) })
  if (b.isLoading) return <Spinner />
  if (b.error || !b.data) return <ErrorNote error={b.error || 'Not found'} />
  const d = b.data
  const done = (k: string) => k === 'source' ? d.sources.length > 0 : !!d.steps[k as keyof Steps]
  return (
    <div className="stack">
      <div className="spread">
        <div><p className="hint"><Link to="/">Borrowers</Link> /</p><h1>{d.name}</h1>
          <p className="hint">{d.facility_ids.length ? <span className="mono">{d.facility_ids.join(' · ')}</span> : null}
            {d.aliases.length ? <> · also seen as {d.aliases.join(', ')}</> : null} · data {d.version}</p></div>
        <DataPack bid={bid} name={d.name} />
      </div>
      <nav aria-label="Phase 1 steps">
        <ol className="steps">
          {STEPS.map(([k, l], i) => (
            <li key={k}><NavLink to={`/borrowers/${bid}/${k}`} className={({ isActive }) => (isActive || (k === 'source' && step === 'source') ? 'active' : done(k) ? 'done' : '')} end>
              <span className="n">{i + 1}</span>{l}</NavLink></li>
          ))}
          <li><span className="locked" title="Next milestone"><span className="n">5</span>Credit memo · next milestone</span></li>
        </ol>
      </nav>
      {step === 'source' && <SourceStep d={d} />}
      {step === 'assess' && <AssessStep bid={bid} d={d} />}
      {step === 'clean' && <CleanStep bid={bid} d={d} />}
      {step === 'normalise' && <NormStep bid={bid} d={d} />}
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

/* ---------------- Source ---------------- */
function SourceStep({ d }: { d: BorrowerDetail }) {
  const [src, setSrc] = useState<string>('')
  const recs = useQuery({
    queryKey: ['records', d.id, src], enabled: !!src,
    queryFn: () => api.get<{ fields: { key: string; label: string }[]; records: { id: string; as_of: string | null; flag: string; stale: boolean; fields: Record<string, string> }[]; elements: { element: string; category: string; type: string; value: string | null; sensitivity: string }[]; elements_total: number }>(`/borrowers/${d.id}/records?source=${encodeURIComponent(src)}`),
  })
  const internal = d.sources.filter(s => s.elements && !s.records), external = d.sources.filter(s => s.records)
  const cols = recs.data ? recs.data.fields.filter(f => recs.data!.records.some(r => r.fields[f.key] !== undefined)) : []
  return (
    <div className="stack">
      <div className="kpis">
        <div className="kpi"><div className="v">{d.sources.length}</div><div className="k">Sources</div></div>
        <div className="kpi"><div className="v">{internal.length}</div><div className="k">Internal systems</div></div>
        <div className="kpi"><div className="v">{external.length}</div><div className="k">Record-level feeds</div></div>
        <div className="kpi"><div className="v">{d.sources.reduce((t, s) => t + s.records, 0)}</div><div className="k">Records</div></div>
        <div className="kpi"><div className="v">{d.sources.reduce((t, s) => t + s.elements, 0)}</div><div className="k">Internal data elements</div></div>
      </div>
      <section className="panel">
        <div className="ph"><h2>Where the data comes from</h2><span className="hint">Select a source to see its data</span></div>
        <div className="tblwrap" style={{ border: 0, borderRadius: 0 }}>
          <table>
            <thead><tr><th>Source</th><th>Zone</th><th className="num">Records</th><th className="num">Elements</th><th>Newest data</th><th>Provider flags</th></tr></thead>
            <tbody>{d.sources.map(s => (
              <tr key={s.source} className="click" onClick={() => setSrc(s.source)} aria-selected={src === s.source} style={src === s.source ? { background: 'var(--accent-soft)' } : undefined}>
                <td><button className="linkbtn" onClick={e => { e.stopPropagation(); setSrc(s.source) }}>{s.source}</button></td><td>{s.zone}</td>
                <td className="num">{s.records || '—'}</td><td className="num">{s.elements || '—'}</td><td className="mono">{s.newest || '—'}</td>
                <td>{s.flags ? <Chip kind="warn">{s.flags} flagged</Chip> : <span className="hint">—</span>}</td></tr>))}
            </tbody>
          </table>
        </div>
      </section>
      {src && <section className="panel">
        <div className="ph"><h2>{src}</h2><button className="linkbtn" onClick={() => setSrc('')}>Close</button></div>
        <div className="pb">{recs.isLoading ? <Spinner /> : recs.data && (recs.data.records.length ? (
          <Table head={['Record', 'As of', 'Flag', ...cols.map(c => c.label)]} mono={[0, 1]}
            rows={recs.data.records.map(r => [r.id, r.as_of || '—', r.flag ? <Chip kind={r.flag === 'VALIDATED' ? 'ok' : 'warn'}>{r.flag}</Chip> : '—', ...cols.map(c => r.fields[c.key] ?? '')])} />
        ) : (
          <>
            <Table head={['Category', 'Element', 'Type', 'Value', 'Sensitivity']} mono={[3]}
              rows={recs.data.elements.map(e => [e.category, e.element, e.type, e.value ?? '', e.sensitivity])} />
            {recs.data.elements_total > recs.data.elements.length && <p className="hint">Showing {recs.data.elements.length} of {recs.data.elements_total}.</p>}
          </>
        ))}</div>
      </section>}
      <section className="panel"><div className="ph"><h2>Files</h2></div>
        <div className="pb"><ul className="hint" style={{ margin: 0, paddingLeft: 18 }}>{d.uploads.map(u => <li key={u.id}>{u.filename} · {when(u.at)}</li>)}</ul>
          <p style={{ marginTop: 10 }}><Link to={`/borrowers/${d.id}/assess`} className="btn primary">Next: Assess →</Link></p></div></section>
    </div>
  )
}

/* ---------------- shared step plumbing ---------------- */
function useStep<T>(bid: number, step: string) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['run', bid, step], queryFn: () => api.get<Run<T> | null>(`/borrowers/${bid}/${step}`) })
  const m = useMutation({
    mutationFn: (body: { selected: string[]; ref_date?: string }) => api.post<Run<T>>(`/borrowers/${bid}/${step}`, body),
    onSuccess: r => {
      qc.setQueryData(['run', bid, step], r)
      qc.invalidateQueries({ queryKey: ['borrower', bid] }); qc.invalidateQueries({ queryKey: ['borrowers'] })
      ;['assess', 'clean', 'normalise'].filter(s => s !== step).forEach(s => qc.invalidateQueries({ queryKey: ['run', bid, s] }))
    },
  })
  return { q, m }
}
const useMeta = () => useQuery({ queryKey: ['meta'], queryFn: () => api.get<Meta>('/meta'), staleTime: Infinity })

function Setup({ title, items, sel, setSel, onRun, running, hint, children }: {
  title: string; items: Record<string, string>; sel: string[]; setSel: (s: string[]) => void; onRun: () => void; running: boolean; hint: string; children?: React.ReactNode
}) {
  const { canEdit } = useAuth()
  return (
    <section className="panel">
      <div className="ph"><h2>{title}</h2><span className="hint">{sel.length} selected</span></div>
      <div className="pb stack">
        <p className="hint">{hint}</p>
        <ul className="checks">{Object.entries(items).map(([k, v]) => (
          <li key={k}><label><input type="checkbox" checked={sel.includes(k)} onChange={e => setSel(e.target.checked ? [...sel, k] : sel.filter(x => x !== k))} />
            <span className="t">{k}</span><span className="s">{v}</span></label></li>))}</ul>
        {children}
      </div>
      <div className="pf">{canEdit ? <button className="btn primary" disabled={running || !sel.length} onClick={onRun}>{running ? <><span className="spin" aria-hidden /> Running…</> : `Run ${title.split(' ')[0]}`}</button>
        : <span className="hint">Viewers can see results but not run steps.</span>}</div>
    </section>
  )
}

function Stale({ r, label }: { r: { stale: boolean; stale_reason?: string } | null | undefined; label: string }) {
  if (!r?.stale) return null
  return <div className="note warn">{r.stale_reason || 'New files were uploaded after this run'}. Run {label} again to update the results.</div>
}

/* ---------------- Assess ---------------- */
function AssessStep({ bid, d }: { bid: number; d: BorrowerDetail }) {
  const meta = useMeta()
  const { q, m } = useStep<AssessResult>(bid, 'assess')
  const [sel, setSel] = useState<string[] | null>(null)
  const [ref, setRef] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  if (!meta.data) return <Spinner />
  const items = meta.data.assess
  const s = sel ?? q.data?.result.selected ?? Object.keys(items)
  const R = q.data?.result
  return (
    <div className="layout2">
      <Setup title="Assess data quality" items={items} sel={s} setSel={setSel} running={m.isPending}
        onRun={() => m.mutate({ selected: s, ref_date: ref || undefined }, { onSuccess: r => toast(`Confidence ${r.result.overall.score}/100`) })}
        hint={`Scores ${d.name}'s ${d.version.includes('cleaned') ? 'cleaned' : 'sourced'} data against each criterion, from the data itself.`}>
        <label className="f"><span className="lbl">Reference date for timeliness</span>
          <input type="date" value={ref} onChange={e => setRef(e.target.value)} /><span className="hint">Blank = {meta.data.reference_date}</span></label>
      </Setup>
      <div className="stack">
        <ErrorNote error={m.error || q.error} />
        <Stale r={q.data} label="Assess" />
        {!R ? <div className="panel"><div className="empty"><b>Not assessed yet</b><span className="hint">Choose criteria and run Assess.</span></div></div> : <>
          <section className="panel"><div className="pb overall">
            <Ring score={R.overall.score} rating={R.overall.rating} />
            <div className="stack grow" style={{ gap: 6 }}>
              <div className="row"><h2>Data confidence for {R.borrower}</h2><RateChip r={R.overall.rating} /></div>
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
          <GoldenTable g={R.golden} />
          <p><Link to={`/borrowers/${bid}/clean`} className="btn primary">Next: Clean →</Link></p>
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
  if (!meta.data) return <Spinner />
  const items = meta.data.clean
  const s = sel ?? q.data?.result.selected ?? Object.keys(items)
  const R = q.data?.result
  const S = R?.summary || {}
  const V = S['Validate critical information']
  return (
    <div className="layout2">
      <Setup title="Clean the data" items={items} sel={s} setSel={setSel} running={m.isPending}
        onRun={() => m.mutate({ selected: s }, { onSuccess: r => toast(`Cleaned: ${r.result.log.length} changes logged`) })}
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
            {q.data && !q.data.stale && <div className="note ok">Assess now scores the cleaned data. <Link to={`/borrowers/${bid}/assess`}>Re-run Assess</Link> to see the change in confidence.</div>}
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
          <p><Link to={`/borrowers/${bid}/normalise`} className="btn primary">Next: Normalise →</Link></p>
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
  if (!meta.data) return <Spinner />
  const items = meta.data.normalise
  const s = sel ?? q.data?.result.selected ?? Object.keys(items)
  const R = q.data?.result
  return (
    <div className="layout2">
      <Setup title="Normalise definitions" items={items} sel={s} setSel={setSel} running={m.isPending}
        onRun={() => m.mutate({ selected: s }, { onSuccess: () => toast('Definitions published') })}
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
          <div className="note">Next milestone: step 5 drafts the credit memo from this golden record, with the rules and policies checklist.</div>
        </>}
      </div>
    </div>
  )
}
