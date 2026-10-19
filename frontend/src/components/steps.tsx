import type { ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Meta, type Run } from '../api'
import { useAuth } from '../auth'

/* ---------------- shared step plumbing ---------------- */
export function useStep<T>(bid: number, step: string) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['run', bid, step], queryFn: () => api.get<Run<T> | null>(`/borrowers/${bid}/${step}`) })
  const m = useMutation({
    mutationFn: (body: { selected?: string[]; ref_date?: string; sources?: string[]; outputs?: string[]; attributes?: string[]; requested?: string[] }) => api.post<Run<T>>(`/borrowers/${bid}/${step}`, body),
    onSuccess: r => {
      qc.setQueryData(['run', bid, step], r)
      qc.invalidateQueries({ queryKey: ['borrower', bid] }); qc.invalidateQueries({ queryKey: ['borrowers'] })
      ;['collect', 'seek', 'assess', 'clean', 'normalise'].filter(s => s !== step).forEach(s => qc.invalidateQueries({ queryKey: ['run', bid, s] }))
    },
  })
  return { q, m }
}
export const useMeta = () => useQuery({ queryKey: ['meta'], queryFn: () => api.get<Meta>('/meta'), staleTime: Infinity })

export function Setup({ title, items, sel, setSel, onRun, running, hint, children }: {
  title: string; items: Record<string, string>; sel: string[]; setSel: (s: string[]) => void; onRun: () => void; running: boolean; hint: string; children?: ReactNode
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

export function Stale({ r, label }: { r: { stale: boolean; stale_reason?: string } | null | undefined; label: string }) {
  if (!r?.stale) return null
  return <div className="note warn">{r.stale_reason || 'New files were uploaded after this run'}. Run {label} again to update the results.</div>
}

