// Step 5 · Credit memo: choose sections, run the five build stages, review, approve and retain.
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type MemoView } from '../api'
import { useAuth } from '../auth'
import { SectionView } from '../components/sections'
import { ErrorNote, Spinner, toast } from '../components/ui'

export default function MemoStep({ bid, name }: { bid: number; name: string }) {
  const { canEdit } = useAuth()
  const qc = useQueryClient()
  const key = ['ws', 'memo', bid]
  const q = useQuery({ queryKey: key, queryFn: () => api.get<MemoView>(`/borrowers/${bid}/memo`) })
  const [pick, setPick] = useState('')
  const m = useMutation({
    mutationFn: (b: { action: string; arg?: unknown; value?: unknown }) => api.post<MemoView>(`/borrowers/${bid}/memo/action`, b),
    onSuccess: (v, b) => {
      qc.setQueryData(key, v); qc.invalidateQueries({ queryKey: ['overview'] })
      if (b.action === 'run') { toast(`Credit memo built: ${v.decision}`); setTimeout(() => document.getElementById('cm1')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50) }
      if (b.action === 'retain') toast(`Memo retained as ${v.retained?.version} · Phase 1 cleared, Phase 2 unlocked`)
      if (b.action === 'edit') toast('Edit applied and logged')
    },
    onError: e => toast(e instanceof Error ? e.message : String(e)),
  })
  const act = (action: string, arg?: unknown, value?: unknown) => m.mutateAsync({ action, arg, value }).catch(() => undefined)
  if (q.isLoading) return <Spinner />
  if (q.error) return <ErrorNote error={q.error} />
  const V = q.data!
  if (!V.available) return <section className="panel"><div className="empty"><b>Not ready yet</b><p className="hint" style={{ maxWidth: 560 }}>{V.why}</p></div></section>
  const S = V.setup!
  const locked = !!V.retained
  const dis = m.isPending || locked || !canEdit
  return (
    <div>
      <section className="panel">
        <h2>Memo sections <small>{S.count}</small></h2>
        <div className="sec">
          <ul className="tiles">
            {S.core.map(s => <li key={s.no}><label htmlFor={`cm-${s.no}`}><input type="checkbox" id={`cm-${s.no}`} checked={s.on} disabled={dis} onChange={() => act('sec.toggle', s.no)} />
              <span className="t">{s.no}. {s.t}</span><span className="s">{s.d}</span></label></li>)}
            {S.extra.map(s => <li key={s.no}><label htmlFor={`cmx-${s.no}`}><input type="checkbox" id={`cmx-${s.no}`} checked disabled />
              <span className="t">{/^[A-D]$/.test(s.no) ? '' : s.no + '. '}{s.t}</span><span className="s">{s.d}</span></label>
              {!dis && <button type="button" className="linkbtn rm rmx" aria-label={`Remove ${s.t}`} onClick={() => act('sec.remove', s.no)}>×</button>}</li>)}
          </ul>
          <div className="pick narrow"><select value={pick} onChange={e => setPick(e.target.value)} aria-label="Add another memo section" disabled={dis || !S.pick.length}>
            <option value="">Other: {S.pick.length} more sections</option>{S.pick.length > 1 && <option value="*">All {S.pick.length} remaining sections</option>}
            {S.pick.map(p => <option key={p.no} value={p.no}>{p.t}</option>)}</select>
            <button type="button" className="btn" disabled={dis || !pick} onClick={() => { act('sec.add', pick); setPick('') }}>Add</button></div>
        </div>
        <div className="sec"><span className="lbl">Build stages <em>Run one at a time, or all five</em></span>
          <ol className="cmstages">{S.stages.map(s => { const can = S.done >= s.k - 1
            return <li key={s.k} className={s.done ? 'done' : ''}><div className="cmn">{s.n}</div><div className="cmt">{s.t}</div><div className="hint">{s.d}</div>
              <div className="cmf">{s.done ? <span className="chip ok">Done</span> : <span className="chip idle">Not run</span>}
                <button type="button" className="btn small" disabled={dis || !can} title={can ? '' : `Run ${S.stages[s.k - 2]?.n} first`} onClick={() => act('run', { from: s.k, to: s.k })}>{s.done ? 'Run again' : 'Run'}</button></div></li> })}</ol></div>
        <div className="runline">
          {m.isPending && <div className="prog"><span><span className="spin" aria-hidden /> Working…</span></div>}
          <span className="hint">{locked ? `Retained ${V.retained.version} · ${V.status}. Re-run Clean or Normalise to start a new version.` : V.scope}</span>
          <button type="button" className="btn primary" disabled={dis} onClick={() => act('run', { from: 1, to: 5 })}>Build credit memo (all 5)</button>
        </div>
      </section>
      <div className="col" style={{ marginTop: 18 }}>
        {(V.sections || []).map(s => <SectionView key={s.title} s={s} act={act} busy={m.isPending} base={`/borrowers/${bid}`} />)}
      </div>
      <p className="hint" style={{ marginTop: 12 }}>Memo for {name}. Generated files are new copies; your source files are never changed.</p>
    </div>
  )
}
