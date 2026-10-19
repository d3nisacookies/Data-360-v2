// Console chrome shared by the dashboard and phase screens: the per-view header, client picker,
// the confidence battery, the executive summary and the floating Rules & policies button.
import { useEffect, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { api, type Battery as Bat, type BorrowerRow, type ExecReport, type Policies } from '../api'
import { useAuth } from '../auth'
import { Battery, ErrorNote, Spinner, toast } from './ui'

const KEY = 'd360.client'
export function lastClient(): number | null { try { const v = localStorage.getItem(KEY); return v ? Number(v) : null } catch { return null } }
export function rememberClient(id: number) { try { localStorage.setItem(KEY, String(id)) } catch { /* private mode */ } }

export const useBorrowers = () => useQuery({ queryKey: ['borrowers'], queryFn: () => api.get<BorrowerRow[]>('/borrowers') })

export function ClientPicker({ id, onPick }: { id: number | null; onPick: (id: number) => void }) {
  const q = useBorrowers()
  if (!q.data?.length) return null
  return <select id="client" aria-label="Client" value={id ?? ''} onChange={e => onPick(Number(e.target.value))}>
    {id === null && <option value="">Choose a client…</option>}
    {q.data.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</select>
}

export function TopBar({ back, title, sub, right, children }: { back?: { to: string; label: string }; title?: string; sub: string; right?: ReactNode; children?: ReactNode }) {
  return (
    <header className="top">
      <div className="brand">{back && <Link to={back.to} className="btn small">{back.label}</Link>}<b>{title || 'Data360'}</b><span>{sub}</span></div>
      {(right || children) && <div className="hright">{right}{children}</div>}
    </header>
  )
}

export function ConfidenceBar({ b, name }: { b: Bat | null | undefined; name: string }) {
  const [how, setHow] = useState(false)
  if (!b) return null
  const color = b.rating === 'high' ? 'ok' : b.rating === 'med' ? 'warn' : 'bad'
  const word = ({ high: 'High', med: 'Medium', low: 'Low', na: '—' } as const)[b.rating] + (b.cap ? ` (${b.cap})` : '')
  const S = b.stages
  return (
    <section className="panel batt" aria-label="Data confidence">
      <div className="battinfo"><span className="lbl">Data confidence</span><b style={{ color: `var(--${color})` }}>{b.pct}%</b>
        <span className="hint">{word}{b.provisional ? ' · provisional' : ''} · {name}</span></div>
      <Battery stages={S} />
      <div className="battlegend"><span className="battleg">
        {S.map((x, i) => <span key={x.label}><i className={`dot g${i}`} />{x.label} <b>{x.pct}%</b>{i > 0 && <span className="hint"> ({x.pct - S[i - 1].pct >= 0 ? '+' : ''}{x.pct - S[i - 1].pct})</span>}</span>)}
        <span><i className="dot r" />Not confident <b>{100 - b.pct}%</b></span></span>
        <span className="hint">{S.length > 1 ? 'Values after Clean and Normalise are provisional until a reviewer signs off the golden record.' : 'Average of the 7 Assess criteria.'}</span></div>
      {b.breakdown && <details className="battHow" open={how} onToggle={e => setHow((e.target as HTMLDetailsElement).open)}>
        <summary className="linkbtn">How it changed</summary>
        <div className="tblwrap"><table><thead><tr>{b.breakdown.head.map(h => <th key={h}>{h}</th>)}</tr></thead>
          <tbody>{b.breakdown.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className={j === r.length - 1 ? 'hint' : j ? 'num' : undefined}>{c}</td>)}</tr>)}</tbody></table></div>
      </details>}
    </section>
  )
}

/* ---------------- executive summary (Phase 1) ---------------- */
export function ExecSummary({ bid, name, facility, onClose }: { bid: number; name: string; facility: string; onClose: () => void }) {
  const qs = facility ? `?facility=${encodeURIComponent(facility)}` : ''
  const q = useQuery({ queryKey: ['report', bid, facility], queryFn: () => api.get<ExecReport>(`/borrowers/${bid}/report${qs}`) })
  const [busy, setBusy] = useState('')
  const dl = async (kind: 'docx' | 'html') => {
    setBusy(kind)
    try { await api.download(`/borrowers/${bid}/report.${kind}${qs}`, `${q.data?.file || 'Data360 report'}.${kind}`) } catch (e) { toast(String(e)) } finally { setBusy('') }
  }
  useEffect(() => { document.getElementById('execPanel')?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }, [])
  const R = q.data
  return (
    <section className="panel exec" id="execPanel" aria-live="polite" style={{ marginTop: 18 }}>
      <h2>Executive summary <small>{name}{facility ? ` · ${facility}` : ''} <button type="button" className="linkbtn rm" onClick={onClose} aria-label="Close">✕</button></small></h2>
      <div className="execbody">
        {q.isLoading ? <Spinner /> : q.error ? <ErrorNote error={q.error} /> : R && <>
          <div className={`execcall ${R.callout.tone}`}>{R.callout.text}</div>
          {R.battery && <div className="execbatt"><b>{R.battery.pct}% confident</b><Battery stages={R.battery.stages} small />
            <span className="hint">{R.battery.stages.length > 1 ? R.battery.stages.map(x => `${x.label} ${x.pct}%`).join(' → ') + ' · ' : ''}{100 - R.battery.pct}% not confident</span></div>}
          <h3>Key findings</h3><ul>{R.bullets.map((x, i) => <li key={i}>{x}</li>)}</ul>
          <h3>Priority actions <span className="hint">({R.actions.length})</span></h3>
          <ol>{R.actions.map(([k, v], i) => <li key={i}><span className="area">{k}:</span> {v}</li>)}</ol>
        </>}
      </div>
      <div className="foot"><span className="hint">The detailed report adds scope, every table, the source tasks and the audit trail.</span>
        <span className="footbtns"><button type="button" className="btn" disabled={!!busy} onClick={() => dl('html')}>{busy === 'html' ? 'Building…' : 'Download HTML'}</button>
          <button type="button" className="btn primary" disabled={!!busy} onClick={() => dl('docx')}>{busy === 'docx' ? 'Building the report…' : 'Generate detailed report (.docx)'}</button></span></div>
    </section>
  )
}

/* ---------------- rules & policies ---------------- */
export function PoliciesFab() {
  const { canEdit } = useAuth()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['policies'], queryFn: () => api.get<Policies>('/policies') })
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<Set<string>>(new Set())
  const [term, setTerm] = useState('')
  const save = useMutation({
    mutationFn: (on: string[]) => api.put<{ on: string[] }>('/policies', { on }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['policies'] }); qc.invalidateQueries({ queryKey: ['ws'] }); qc.invalidateQueries({ queryKey: ['overview'] }); setOpen(false); toast('Rules & policies applied') },
    onError: e => toast(String(e)),
  })
  const show = () => { if (q.data) { setDraft(new Set(q.data.on)); setTerm(''); setOpen(true) } }
  useEffect(() => { const h = () => show(); window.addEventListener('d360:policies', h); return () => window.removeEventListener('d360:policies', h) })
  useEffect(() => { document.body.classList.toggle('modal-open', open); const k = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    if (open) window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k) }, [open])
  const P = q.data
  const tested = new Set(P?.tested || [])
  const t = term.trim().toLowerCase()
  return <>
    <button type="button" className="polfab" onClick={show} aria-haspopup="dialog">§ Rules &amp; policies <span className="pcount">{P?.on.length ?? ''}</span></button>
    {open && P && <div className="polmodal" onClick={e => { if (e.target === e.currentTarget) setOpen(false) }}>
      <div className="poldlg" role="dialog" aria-modal="true" aria-labelledby="polTitle">
        <div className="polhead"><div><h2 id="polTitle">Rules &amp; policies</h2>
          <span className="hint">{draft.size} of {P.all.length} selected · {[...draft].filter(id => tested.has(id)).length} tested by Data360 today</span></div>
          <button type="button" className="linkbtn rm" onClick={() => setOpen(false)} aria-label="Close">✕</button></div>
        <div className="poltools"><input type="text" value={term} onChange={e => setTerm(e.target.value)} placeholder="Search rules, regulations or policies" aria-label="Search rules" autoFocus />
          <button type="button" className="btn small" onClick={() => setDraft(new Set(P.all))}>Select all</button>
          <button type="button" className="btn small" onClick={() => setDraft(new Set())}>Clear all</button>
          <button type="button" className="btn small" onClick={() => setDraft(new Set(P.tested))}>Only rules tested today</button></div>
        <div className="polnote">Typical rules for a Singapore-booked credit memo. Sample set: thresholds and applicability to be confirmed with your Credit Risk and Compliance teams.</div>
        <div className="polbody">
          {P.groups.map(g => { const vis = g.rules.filter(r => !t || [r.id, r.t, r.d, r.src, g.name].join(' ').toLowerCase().includes(t)); if (!vis.length) return null
            const n = g.rules.filter(r => draft.has(r.id)).length, all = n === g.rules.length
            return <fieldset className="polg" key={g.name}><legend><label><input type="checkbox" checked={all} ref={el => { if (el) el.indeterminate = n > 0 && !all }}
              onChange={() => { const d = new Set(draft); g.rules.forEach(r => all ? d.delete(r.id) : d.add(r.id)); setDraft(d) }} /> <b>{g.name}</b></label><span className="hint">{n} of {g.rules.length}</span></legend>
              {vis.map(r => <label className="polr" key={r.id}><input type="checkbox" checked={draft.has(r.id)} onChange={() => { const d = new Set(draft); d.has(r.id) ? d.delete(r.id) : d.add(r.id); setDraft(d) }} />
                <span className="pid">{r.id}</span><span className="pt"><b>{r.t}</b>{tested.has(r.id) && <span className="chip ok">Tested today</span>}<span className="hint">{r.d}</span><span className="psrc">{r.src}</span></span></label>)}
            </fieldset> })}
        </div>
        <div className="polfoot"><span className="hint">Rules switched off are not applied to the credit memo checks or the draft decision.</span>
          <span className="footbtns"><button type="button" className="btn" onClick={() => setOpen(false)}>Cancel</button>
            <button type="button" className="btn primary" disabled={!canEdit || save.isPending} title={canEdit ? '' : 'Viewers cannot change rules'} onClick={() => save.mutate([...draft])}>Apply</button></span></div>
      </div></div>}
  </>
}

export function Locked({ why, to }: { why: string; to: string }) {
  const nav = useNavigate()
  return <section className="panel"><div className="empty"><b>Locked</b><p className="hint" style={{ maxWidth: 560 }}>{why}</p>
    <button type="button" className="btn primary" onClick={() => nav(to)}>Back to the dashboard</button></div></section>
}
