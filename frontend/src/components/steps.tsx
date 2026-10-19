import { useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Meta, type PickGroup, type Run } from '../api'
import { useAuth } from '../auth'

/* ---------------- shared step plumbing ---------------- */
export function useStep<T>(bid: number, step: string) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['run', bid, step], queryFn: () => api.get<Run<T> | null>(`/borrowers/${bid}/${step}`) })
  const m = useMutation({
    mutationFn: (body: { selected?: string[]; extra?: string[]; ref_date?: string; sources?: string[]; outputs?: string[]; attributes?: string[]; requested?: string[] }) => api.post<Run<T>>(`/borrowers/${bid}/${step}`, body),
    onSuccess: r => {
      qc.setQueryData(['run', bid, step], r)
      qc.invalidateQueries({ queryKey: ['borrower', bid] }); qc.invalidateQueries({ queryKey: ['borrowers'] })
      ;['collect', 'seek', 'assess', 'clean', 'normalise'].filter(s => s !== step).forEach(s => qc.invalidateQueries({ queryKey: ['run', bid, s] }))
    },
  })
  return { q, m }
}
export const useMeta = () => useQuery({ queryKey: ['meta'], queryFn: () => api.get<Meta>('/meta'), staleTime: Infinity })

export function Setup({ title, items, sel, setSel, onRun, running, hint, children, pick, extra = [], setExtra }: {
  title: string; items: Record<string, string>; sel: string[]; setSel: (s: string[]) => void; onRun: () => void; running: boolean; hint: string; children?: ReactNode
  pick?: PickGroup[]; extra?: string[]; setExtra?: (s: string[]) => void
}) {
  const { canEdit } = useAuth()
  const [p, setP] = useState('')
  const left = (pick || []).map(g => ({ ...g, items: g.items.filter(i => !extra.includes(i.n)) })).filter(g => g.items.length)
  const nLeft = left.reduce((t, g) => t + g.items.length, 0)
  const desc = (n: string) => (pick || []).flatMap(g => g.items.map(i => ({ ...i, cat: g.cat }))).find(i => i.n === n)
  return (
    <section className="panel">
      <div className="ph"><h2>{title}</h2><span className="hint">{sel.length} selected</span></div>
      <div className="pb stack">
        <p className="hint">{hint}</p>
        <ul className="checks">{Object.entries(items).map(([k, v]) => (
          <li key={k}><label><input type="checkbox" checked={sel.includes(k)} onChange={e => setSel(e.target.checked ? [...sel, k] : sel.filter(x => x !== k))} />
            <span className="t">{k}</span><span className="s">{v}</span></label></li>))}
          {extra.map(n => <li key={n}><label><input type="checkbox" checked disabled /><span className="t">{n}</span><span className="s">{desc(n)?.cat}: {desc(n)?.d}</span></label>
            <button type="button" className="linkbtn rm" aria-label={`Remove ${n}`} onClick={() => setExtra?.(extra.filter(x => x !== n))}>×</button></li>)}</ul>
        {pick && setExtra && <div className="pick"><select value={p} onChange={e => setP(e.target.value)} aria-label="Add another item" disabled={!nLeft}>
          <option value="">Other: {nLeft} more</option>{left.map(g => <optgroup key={g.cat} label={g.cat}>{g.items.map(i => <option key={i.n} value={i.n}>{i.n}</option>)}</optgroup>)}</select>
          <button type="button" className="btn" disabled={!p} onClick={() => { setExtra([...extra, p]); setP('') }}>Add</button></div>}
        {children}
      </div>
      <div className="pf">{canEdit ? <button className="btn primary" disabled={running || (!sel.length && !extra.length)} onClick={onRun}>{running ? <><span className="spin" aria-hidden /> Running…</> : `Run ${title.split(' ')[0]}`}</button>
        : <span className="hint">Viewers can see results but not run steps.</span>}</div>
    </section>
  )
}

export function Stale({ r, label }: { r: { stale: boolean; stale_reason?: string } | null | undefined; label: string }) {
  if (!r?.stale) return null
  return <div className="callout warn">{r.stale_reason || 'New files were uploaded after this run'}. Run {label} again to update the results.</div>
}

