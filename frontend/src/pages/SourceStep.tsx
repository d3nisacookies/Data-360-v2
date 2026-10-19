import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type BorrowerDetail, type CollectResult, type SeekAttr, type SeekResult, type SeekStatus } from '../api'
import { useAuth } from '../auth'
import { Chip, ErrorNote, Spinner, Table, toast, when } from '../components/ui'
import { Stale, useMeta, useStep } from '../components/steps'

const TABS = [['collector', 'Collector'], ['seeker', 'Seeker'], ['files', 'Sources & files']] as const

export default function SourceStep({ d }: { d: BorrowerDetail }) {
  const [sp, setSp] = useSearchParams()
  const tab = sp.get('tab') || 'collector'
  const go = (t: string) => setSp(t === 'collector' ? {} : { tab: t }, { replace: true })
  return (
    <div className="stack">
      <div className="row" role="tablist" aria-label="Source">
        {TABS.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className={`btn small${tab === k ? ' primary' : ''}`} onClick={() => go(k)}>{l}
          {k === 'collector' && d.steps.collect && <span aria-hidden> ✓</span>}{k === 'seeker' && d.steps.seek && <span aria-hidden> ✓</span>}</button>)}
      </div>
      {tab === 'collector' && <Collector d={d} goSeek={() => go('seeker')} />}
      {tab === 'seeker' && <Seeker d={d} />}
      {tab === 'files' && <Files d={d} />}
    </div>
  )
}

function RunButton({ running, disabled, onClick, label }: { running: boolean; disabled?: boolean; onClick: () => void; label: string }) {
  const { canEdit } = useAuth()
  if (!canEdit) return <span className="hint">Viewers can see results but not run steps.</span>
  return <button className="btn primary" disabled={running || disabled} onClick={onClick}>{running ? <><span className="spin" aria-hidden /> Running…</> : label}</button>
}

function CheckList({ items, sel, setSel }: { items: [string, string][]; sel: string[]; setSel: (s: string[]) => void }) {
  return <ul className="checks">{items.map(([k, v]) => (
    <li key={k}><label><input type="checkbox" checked={sel.includes(k)} onChange={e => setSel(e.target.checked ? [...sel, k] : sel.filter(x => x !== k))} />
      <span className="t">{k}</span>{v && <span className="s">{v}</span>}</label></li>))}</ul>
}

/* ---------------- Collector ---------------- */
const COV: Record<string, ['ok' | 'warn' | 'bad', string]> = { ok: ['ok', 'Covered'], part: ['warn', 'Partly covered'], none: ['bad', 'Not covered'] }

function Collector({ d, goSeek }: { d: BorrowerDetail; goSeek: () => void }) {
  const meta = useMeta()
  const { q, m } = useStep<CollectResult>(d.id, 'collect')
  const [srcs, setSrcs] = useState<string[] | null>(null)
  const [outs, setOuts] = useState<string[] | null>(null)
  const [view, setView] = useState('')
  if (!meta.data) return <Spinner />
  const R = q.data?.result
  const all = d.sources.map(s => s.source)
  const s = srcs ?? R?.sources ?? all
  const o = outs ?? R?.outputs ?? meta.data.standard_outputs
  const run = (sources = s, outputs = o) => m.mutate({ sources, outputs }, {
    onSuccess: r => toast(`Collected from ${r.result.counts.locations} sources: ${r.result.counts.full} of ${r.result.outputs.length} outputs covered`),
  })
  const zone = (z: string) => d.sources.filter(x => (z === 'Internal' ? x.zone === 'Internal' : x.zone !== 'Internal')).map(x => [x.source, `${x.records ? x.records + ' records' : x.elements + ' elements'}${x.newest ? ' · newest ' + x.newest : ''}`] as [string, string])
  return (
    <div className="layout2">
      <section className="panel">
        <div className="ph"><h2>Collector</h2><span className="hint">{s.length} sources · {o.length} outputs</span></div>
        <div className="pb stack">
          <p className="hint">Choose where to look and what the credit memo needs. Assess, Clean and Normalise then use only the sources in scope.</p>
          <div className="spread"><span className="lbl">Where to look</span>
            <span className="row" style={{ gap: 8 }}><button className="linkbtn" onClick={() => setSrcs(all)}>All</button><button className="linkbtn" onClick={() => setSrcs([])}>None</button></span></div>
          {zone('Internal').length > 0 && <><span className="hint">Internal systems</span><CheckList items={zone('Internal')} sel={s} setSel={setSrcs} /></>}
          {zone('External').length > 0 && <><span className="hint">External and record-level feeds</span><CheckList items={zone('External')} sel={s} setSel={setSrcs} /></>}
          <span className="lbl">What the credit memo needs</span>
          <CheckList items={Object.entries(meta.data.outputs)} sel={o} setSel={setOuts} />
        </div>
        <div className="pf"><RunButton running={m.isPending} disabled={!s.length || !o.length} onClick={() => run()} label="Run Collector" /></div>
      </section>
      <div className="stack">
        <ErrorNote error={m.error || q.error} />
        <Stale r={q.data} label="the Collector" />
        {!R ? <div className="panel"><div className="empty"><b>Collector not run yet</b><span className="hint">Pick sources and outputs, then run the Collector.</span></div></div> : <>
          <div className="kpis">
            <div className="kpi"><div className="v">{R.counts.locations}</div><div className="k">Sources in scope</div></div>
            <div className="kpi"><div className="v">{R.counts.records}</div><div className="k">Records</div></div>
            <div className="kpi"><div className="v">{R.counts.elements}</div><div className="k">Data elements</div></div>
            <div className="kpi"><div className="v">{R.counts.restricted}</div><div className="k">Restricted elements</div></div>
            <div className="kpi"><div className="v">{R.counts.full}/{R.outputs.length}</div><div className="k">Outputs covered</div></div>
          </div>
          <section className="panel">
            <div className="ph"><h2>Does the data cover the credit memo?</h2><span className="hint">{q.data?.by} · {q.data && when(q.data.at)}</span></div>
            <div className="pb stack">{R.coverage.map(c => (
              <div key={c.output} className="dcard">
                <div className="dtop"><span className="dn">{c.output}</span><Chip kind={COV[c.status][0]}>{COV[c.status][1]}</Chip></div>
                <p className="hint">{c.desc} · {c.hit} of {c.total} evidence groups found</p>
                <div className="row" style={{ gap: 6 }}>{c.groups.map(g => <span key={g.label} className={`chip ${g.n ? 'ok' : g.held_elsewhere ? 'warn' : 'idle'}`}
                  title={g.n ? `${g.n} values` : g.held_elsewhere ? 'Held in a source that is out of scope' : 'Not held in any uploaded file'}>{g.label}{g.n ? ` · ${g.n}` : ''}</span>)}</div>
                {(c.addable.length > 0 || c.missing.length > 0) && <div className="row">
                  {c.addable.length > 0 && <button className="btn small" disabled={m.isPending} onClick={() => { const ns = [...new Set([...s, ...c.addable])]; setSrcs(ns); run(ns, o) }}>Add {c.addable.join(' + ')} and run again</button>}
                  {c.missing.length > 0 && <span className="hint">Not in any uploaded file: {c.missing.join(', ')}. <button className="linkbtn" onClick={goSeek}>Try the Seeker →</button></span>}
                </div>}
              </div>))}</div>
          </section>
          <section className="panel">
            <div className="ph"><h2>What each source holds</h2><span className="hint">Select a source to see its data</span></div>
            <div className="tblwrap" style={{ border: 0, borderRadius: 0 }}>
              <table>
                <thead><tr><th>Source</th><th>Scope</th><th className="num">Records</th><th className="num">Elements</th><th>Main categories</th></tr></thead>
                <tbody>{R.locations.map(l => (
                  <tr key={l.source} className="click" onClick={() => setView(l.source)}>
                    <td><button className="linkbtn" onClick={e => { e.stopPropagation(); setView(l.source) }}>{l.source}</button><div className="hint">{l.zone}{l.newest ? ` · newest ${l.newest}` : ''}</div></td>
                    <td>{l.in_scope ? <Chip kind="ok">In scope</Chip> : <Chip kind="idle">Not used</Chip>}</td>
                    <td className="num">{l.records || '—'}</td><td className="num">{l.elements || '—'}</td>
                    <td className="hint">{l.categories.slice(0, 4).map(([k, n]) => `${k} (${n})`).join(' · ') || '—'}</td>
                  </tr>))}</tbody>
              </table>
            </div>
          </section>
          {view && <SourceData bid={d.id} source={view} onClose={() => setView('')} />}
          <p className="row"><button className="btn" onClick={goSeek}>Next: Seeker →</button><Link to={`/borrowers/${d.id}/assess`} className="linkbtn">Skip to Assess</Link></p>
        </>}
      </div>
    </div>
  )
}

/* ---------------- Seeker ---------------- */
const SK: Record<SeekStatus, ['ok' | 'warn' | 'bad' | 'info', string]> = {
  ok: ['ok', 'Found'], multi: ['ok', 'Found (several)'], conf: ['warn', 'Values disagree'], indirect: ['info', 'Partial match'], pending: ['info', 'Requested'], miss: ['bad', 'Not found'],
}
const FILTERS: [string, string, SeekStatus[]][] = [['all', 'All', []], ['ok', 'Found', ['ok', 'multi']], ['conf', 'Values disagree', ['conf']], ['gap', 'Not found or partial', ['miss', 'indirect']], ['pending', 'Requested', ['pending']]]

function Seeker({ d }: { d: BorrowerDetail }) {
  const meta = useMeta()
  const { q, m } = useStep<SeekResult>(d.id, 'seek')
  const [sel, setSel] = useState<string[] | null>(null)
  const [custom, setCustom] = useState<string[] | null>(null)
  const [req, setReq] = useState<string[] | null>(null)
  const [typed, setTyped] = useState('')
  const [filter, setFilter] = useState('all')
  const [open, setOpen] = useState<string | null>(null)
  const [pick, setPick] = useState('')
  if (!meta.data) return <Spinner />
  const M = meta.data
  const R = q.data?.result
  const known = Object.keys(M.attributes)
  const s = sel ?? R?.attributes ?? M.standard_attributes
  const cust = custom ?? (R?.attributes.filter(a => !known.includes(a)) || [])
  const rq = req ?? R?.requested ?? []
  const allAttrs = [...known, ...cust.filter(c => !known.includes(c))]
  const run = (attributes = s, requested = rq) => m.mutate({ attributes, requested }, {
    onSuccess: r => toast(`${r.result.counts.found} of ${r.result.counts.total} attributes found`),
  })
  const addTyped = () => { const t = typed.trim(); if (!t) return; setCustom([...new Set([...cust, t])]); setSel([...new Set([...s, t])]); setTyped('') }
  const request = (src: string) => { const n = [...new Set([...rq, src])]; setReq(n); run(s, n) }
  const f = FILTERS.find(x => x[0] === filter)!
  const rows = (R?.results || []).filter(r => !f[2].length || f[2].includes(r.status))
  return (
    <div className="layout2">
      <section className="panel">
        <div className="ph"><h2>Seeker</h2><span className="hint">{s.length} attributes</span></div>
        <div className="pb stack">
          <p className="hint">Searches every uploaded file for each attribute, including sources outside the Collector's scope, and checks whether the sources agree.</p>
          <div className="spread"><span className="lbl">Attributes to find</span>
            <span className="row" style={{ gap: 8 }}><button className="linkbtn" onClick={() => setSel(M.standard_attributes)}>Standard set</button><button className="linkbtn" onClick={() => setSel(allAttrs)}>All</button></span></div>
          <CheckList items={allAttrs.map(a => [a, known.includes(a) ? (M.standard_attributes.includes(a) ? '' : 'Pick list') : 'Your attribute'])} sel={s} setSel={setSel} />
          <label className="f"><span className="lbl">Add your own attribute</span>
            <span className="row" style={{ flexWrap: 'nowrap' }}><input type="text" value={typed} onChange={e => setTyped(e.target.value)} onKeyDown={e => e.key === 'Enter' && addTyped()} placeholder="e.g. UBO nationality" />
              <button className="btn small" onClick={addTyped}>Add</button></span>
            <span className="hint">Matched to element names and fields by similarity.</span></label>
          <label className="f"><span className="lbl">Request from an outside source</span>
            <select value={pick} onChange={e => { if (e.target.value) { setReq([...new Set([...rq, e.target.value])]); setPick('') } }}>
              <option value="">Choose a source…</option>
              {M.pick_sources.map(c => <optgroup key={c.cat} label={c.cat}>{c.src.filter(x => !rq.includes(x)).map(x => <option key={x}>{x}</option>)}</optgroup>)}
            </select>
            {rq.length > 0 && <span className="row" style={{ gap: 6 }}>{rq.map(x => <span key={x} className="chip info">{x} <button className="linkbtn" aria-label={`Remove ${x}`} onClick={() => setReq(rq.filter(y => y !== x))}>×</button></span>)}</span>}
            <span className="hint">Not connected yet: requested sources are recorded so the gap shows as requested, not missing.</span></label>
        </div>
        <div className="pf"><RunButton running={m.isPending} disabled={!s.length} onClick={() => run()} label="Run Seeker" /></div>
      </section>
      <div className="stack">
        <ErrorNote error={m.error || q.error} />
        <Stale r={q.data} label="the Seeker" />
        {!R ? <div className="panel"><div className="empty"><b>Seeker not run yet</b><span className="hint">Tick the attributes you need, then run the Seeker.</span></div></div> : <>
          <section className="panel"><div className="pb stack">
            <p><b>{R.counts.found}</b> of <b>{R.counts.total}</b> attributes found for <b>{d.name}</b> across <b>{R.locations}</b> sources.
              {' '}<b>{R.counts.conflict}</b> have values that disagree, <b>{R.counts.gap}</b> are missing or partial{R.counts.pending ? <>, <b>{R.counts.pending}</b> requested</> : null}.</p>
            <div className="row" style={{ gap: 6 }}>{FILTERS.map(([k, l, st]) => <button key={k} className={`btn small${filter === k ? ' primary' : ''}`} aria-pressed={filter === k} onClick={() => setFilter(k)}>
              {l} <b>{st.length ? R.results.filter(r => st.includes(r.status)).length : R.results.length}</b></button>)}</div>
          </div></section>
          <section className="panel">
            <div className="tblwrap" style={{ border: 0, borderRadius: 0, maxHeight: 'none' }}>
              <table>
                <thead><tr><th>Attribute</th><th>Status</th><th>Where</th><th></th></tr></thead>
                <tbody>{rows.map(r => <SeekRow key={r.attribute} r={r} open={open === r.attribute} toggle={() => setOpen(open === r.attribute ? null : r.attribute)} request={request} busy={m.isPending} />)}
                  {!rows.length && <tr><td colSpan={4} className="hint">No attributes match this filter.</td></tr>}</tbody>
              </table>
            </div>
          </section>
          <p><Link to={`/borrowers/${d.id}/assess`} className="btn primary">Next: Assess →</Link></p>
        </>}
      </div>
    </div>
  )
}

function SeekRow({ r, open, toggle, request, busy }: { r: SeekAttr; open: boolean; toggle: () => void; request: (s: string) => void; busy: boolean }) {
  const { canEdit } = useAuth()
  const quick = ['miss', 'indirect', 'conf'].includes(r.status) ? r.suppliers.filter(x => !r.requested_from.includes(x)).slice(0, 2) : []
  return (
    <>
      <tr>
        <td><b>{r.attribute}</b></td>
        <td><Chip kind={SK[r.status][0]}>{SK[r.status][1]}</Chip></td>
        <td className="hint">{r.status === 'pending' ? `Requested from ${r.requested_from.join(', ')}` : r.locations.length
          ? <>{r.values.length > 1 ? `${r.values.length} values from ` : 'In '}{r.locations.slice(0, 3).join(', ')}{r.locations.length > 3 ? ` +${r.locations.length - 3} more` : ''}</> : 'Not held in any uploaded file'}
          {canEdit && quick.length > 0 && <div className="row" style={{ gap: 6, marginTop: 4 }}><span>{r.status === 'conf' ? 'Verify with:' : 'Request from:'}</span>
            {quick.map(x => <button key={x} className="btn small" disabled={busy} onClick={() => request(x)}>+ {x}</button>)}</div>}</td>
        <td><button className="btn small" aria-expanded={open} onClick={toggle}>{open ? 'Hide' : 'Details'}</button></td>
      </tr>
      {open && <tr><td colSpan={4} style={{ background: 'var(--surface-2)' }}><div className="stack" style={{ gap: 10 }}>
        {r.note && <p className="hint">{r.note}</p>}
        {r.values.length > 0 && <div className="row" style={{ gap: 6 }}>{r.values.map(v => <span key={v.value} className="chip idle" style={{ whiteSpace: 'normal' }}>
          <span className="mono">{v.value}</span> · {v.count}× · {v.locations.join(', ')}</span>)}</div>}
        {r.hits.length > 0 && <Table head={['Location', 'Field', 'Value', 'Record', 'As of', 'Record flag']} mono={[2, 3, 4]}
          rows={r.hits.map(h => [<><b>{h.location}</b><div className="hint">{h.zone}</div></>, h.field, h.value, h.record, h.as_of || '—',
            h.flag ? <Chip kind={h.flag === 'VALIDATED' ? 'ok' : 'warn'}>{h.flag}</Chip> : '—'])} />}
        {r.potential && <p className="hint"><b>Potential sources:</b> {r.potential}</p>}
      </div></td></tr>}
    </>
  )
}

/* ---------------- Sources & files ---------------- */
interface RecordsResp {
  fields: { key: string; label: string }[]
  records: { id: string; as_of: string | null; flag: string; stale: boolean; fields: Record<string, string> }[]
  elements: { element: string; category: string; type: string; value: string | null; sensitivity: string }[]; elements_total: number
}

function SourceData({ bid, source, onClose }: { bid: number; source: string; onClose: () => void }) {
  const [filter, setFilter] = useState('')
  const recs = useQuery({ queryKey: ['records', bid, source], queryFn: () => api.get<RecordsResp>(`/borrowers/${bid}/records?source=${encodeURIComponent(source)}`) })
  const D = recs.data
  const cols = D ? D.fields.filter(f => D.records.some(r => r.fields[f.key] !== undefined)) : []
  const fl = filter.toLowerCase()
  const els = D ? D.elements.filter(e => !fl || `${e.category} ${e.element} ${e.value}`.toLowerCase().includes(fl)) : []
  return (
    <section className="panel">
      <div className="ph"><h2>{source}</h2><button className="linkbtn" onClick={onClose}>Close</button></div>
      <div className="pb stack">{recs.isLoading ? <Spinner /> : D && (D.records.length ? (
        <Table head={['Record', 'As of', 'Flag', ...cols.map(c => c.label)]} mono={[0, 1]}
          rows={D.records.map(r => [r.id, r.as_of || '—', r.flag ? <Chip kind={r.flag === 'VALIDATED' ? 'ok' : 'warn'}>{r.flag}</Chip> : '—', ...cols.map(c => r.fields[c.key] ?? '')])} />
      ) : (
        <>
          <input type="text" value={filter} onChange={e => setFilter(e.target.value)} placeholder={`Filter ${D.elements.length} elements`} aria-label="Filter elements" />
          <Table head={['Category', 'Element', 'Type', 'Value', 'Sensitivity']} mono={[3]} rows={els.map(e => [e.category, e.element, e.type, e.value ?? '', e.sensitivity])} />
          {D.elements_total > D.elements.length && <p className="hint">Showing {D.elements.length} of {D.elements_total}.</p>}
        </>
      ))}</div>
    </section>
  )
}

function Files({ d }: { d: BorrowerDetail }) {
  const [src, setSrc] = useState('')
  return (
    <div className="stack">
      <section className="panel">
        <div className="ph"><h2>Where the data comes from</h2><span className="hint">{d.scope ? `${d.scope.length} of ${d.sources.length} in the Collector's scope` : 'All sources (Collector not run)'}</span></div>
        <div className="tblwrap" style={{ border: 0, borderRadius: 0 }}>
          <table>
            <thead><tr><th>Source</th><th>Zone</th><th className="num">Records</th><th className="num">Elements</th><th>Newest data</th><th>Provider flags</th></tr></thead>
            <tbody>{d.sources.map(s => (
              <tr key={s.source} className="click" onClick={() => setSrc(s.source)}>
                <td><button className="linkbtn" onClick={e => { e.stopPropagation(); setSrc(s.source) }}>{s.source}</button>
                  {d.scope && !d.scope.includes(s.source) && <span className="hint"> · not in scope</span>}</td><td>{s.zone}</td>
                <td className="num">{s.records || '—'}</td><td className="num">{s.elements || '—'}</td><td className="mono">{s.newest || '—'}</td>
                <td>{s.flags ? <Chip kind="warn">{s.flags} flagged</Chip> : <span className="hint">—</span>}</td></tr>))}
            </tbody>
          </table>
        </div>
      </section>
      {src && <SourceData bid={d.id} source={src} onClose={() => setSrc('')} />}
      <section className="panel"><div className="ph"><h2>Files</h2></div>
        <div className="pb"><ul className="hint" style={{ margin: 0, paddingLeft: 18 }}>{d.uploads.map(u => <li key={u.id}>{u.filename} · {when(u.at)}</li>)}</ul></div></section>
    </div>
  )
}
