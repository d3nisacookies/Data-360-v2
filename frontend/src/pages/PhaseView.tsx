// Phase 2 (steps 6–9) and Phase 3 (stages 10–13): pick what to create, run, review, sign off.
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, type Block, type PhaseView } from '../api'
import { useAuth } from '../auth'
import { Blocks, FootView, SectionView } from '../components/sections'
import { Locked, rememberClient, TopBar, useBorrowers } from '../components/Shell'
import { ErrorNote, Spinner, toast } from '../components/ui'

const SUB = { 2: 'Phase 2 · Improve & Plan · Identify gaps, build confidence and prioritise', 3: 'Phase 3 · Transform · Execute the roadmap to intelligent data and enterprise' }

export default function PhasePage({ phase }: { phase: 2 | 3 }) {
  const { id, step = '' } = useParams()
  const bid = Number(id)
  const nav = useNavigate()
  const qc = useQueryClient()
  const { canEdit } = useAuth()
  const list = useBorrowers()
  const key = ['ws', `p${phase}`, bid, step]
  const q = useQuery({ queryKey: key, queryFn: () => api.get<PhaseView>(`/borrowers/${bid}/p${phase}${step ? `?step=${step}` : ''}`) })
  const V = q.data
  const k = V?.step || step
  const [pick, setPick] = useState('')
  useEffect(() => { rememberClient(bid) }, [bid])
  const m = useMutation({
    mutationFn: (b: { action: string; arg?: unknown; value?: unknown }) => api.post<PhaseView>(`/borrowers/${bid}/p${phase}/action`, { ...b, step: k }),
    onSuccess: (v, b) => {
      qc.setQueryData(['ws', `p${phase}`, bid, step], v); qc.invalidateQueries({ queryKey: ['overview'] })
      if (b.action === 'run') { toast(`Step ${v.nav.find(x => x.k === v.step)?.n} · ${v.nav.find(x => x.k === v.step)?.t} ready`); setTimeout(() => document.getElementById('pres')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50) }
      if (b.action === 'p2.approve') toast('Roadmap approved · Phase 2 cleared, Phase 3 unlocked')
      if (b.action === 'complete') toast(v.nav.every(x => x.done) ? 'Phase 3 cleared · all phases complete' : 'Stage completed · next stage unlocked')
      if (b.action === 'plan') { toast('Project plan created'); setTimeout(() => document.getElementById('plan')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50) }
    },
    onError: e => toast(e instanceof Error ? e.message : String(e)),
  })
  const act = (action: string, arg?: unknown, value?: unknown) => m.mutateAsync({ action, arg, value }).catch(() => undefined)
  const go = (s: string) => { nav(`/b/${bid}/p${phase}/${s}`); window.scrollTo({ top: 0 }) }
  const name = list.data?.find(b => b.id === bid)?.name || ''
  const header = <TopBar back={{ to: `/console?b=${bid}`, label: '← Dashboard' }} sub={SUB[phase]}
    right={<><Link className="btn small report" to={`/b/${bid}/fix`}>Fix plan</Link>
      {V?.available && <ol className={`steps p${phase}steps`} aria-label={`Phase ${phase} steps`}>{V.nav.map(s => (
        <li key={s.k} className={s.k === V.step ? 'on' : ''} aria-current={s.k === V.step ? 'step' : undefined}>
          <button type="button" disabled={!s.can} title={s.can ? '' : s.why || 'Complete the previous stage first'} onClick={() => go(s.k)}><span className="n">{s.n}</span>{s.t}{s.done ? ' ✓' : ''}</button></li>))}</ol>}</>} />
  if (q.isLoading) return <>{header}<Spinner /></>
  if (q.error) return <>{header}<ErrorNote error={q.error} /></>
  if (!V!.available) return <>{header}<Locked why={V!.why!} to={`/console?b=${bid}`} /></>
  const S = V!.setup
  const locked = S.locked || !!(phase === 2 && V!.approved)
  const dis = m.isPending || !canEdit
  const base = `/borrowers/${bid}`
  return (
    <div>
      {header}
      <div className="screenhead"><span className={`crumb p${phase}c`}>{V!.crumb}</span><h1>{V!.h1}</h1>{name && <span className="hint">{name}</span>}</div>
      {phase === 3 && V!.track && <section className="panel" style={{ marginBottom: 18 }}><Blocks blocks={[V!.track as Block]} act={act} /><div className="p3init">{V!.init}</div></section>}
      <section className="panel">
        <h2>{phase === 2 ? V!.lbl : 'What to create'} <small>{S.count}</small></h2>
        <div className="sec"><ul className="tiles">
          {S.std.map((x, i) => <li key={x.name}><label htmlFor={`ps-${i}`}><input type="checkbox" id={`ps-${i}`} checked={x.on} disabled={dis || locked} onChange={() => act('sel.toggle', x.name)} />
            <span className="t">{x.name}</span><span className="s">{x.desc}</span></label></li>)}
          {S.extra.map((x, i) => <li key={x.name}><label htmlFor={`px-${i}`}><input type="checkbox" id={`px-${i}`} checked disabled /><span className="t">{x.name}</span><span className="s">{x.desc}</span></label>
            {!locked && !dis && <button type="button" className="linkbtn rm rmx" aria-label={`Remove ${x.name}`} onClick={() => act('extra.remove', x.name)}>×</button>}</li>)}
        </ul>
          <div className="pick narrow"><select value={pick} onChange={e => setPick(e.target.value)} aria-label="Add another item" disabled={dis || locked || !S.pick.length}>
            <option value="">Other: {S.pick.length} more</option>{S.pick.map(p => <option key={p}>{p}</option>)}</select>
            <button type="button" className="btn" disabled={dis || locked || !pick} onClick={() => { act('extra.add', pick); setPick('') }}>Add</button></div></div>
        <div className="runline">
          {m.isPending && <div className="prog"><span><span className="spin" aria-hidden /> Working…</span></div>}
          <span className="hint">{V!.scope}</span>
          <button type="button" className="btn primary" disabled={dis || (phase === 3 && !!V!.done)} onClick={() => act('run')}>{V!.verb}</button>
        </div>
      </section>
      <div className="col" id="pres" style={{ marginTop: 18 }}>
        {V!.sections.map(s => <SectionView key={s.title} s={s} act={act} busy={m.isPending} base={base} onNext={go} className={phase === 3 ? 'p3sec' : ''} />)}
        {phase === 2 && V!.approved && <section className="panel"><div className="secfoot"><span className="hint">Approved by {V!.approved.by} on {V!.approved.at}. Phase 2 cleared; Phase 3 unlocked.</span>
          <span className="footbtns"><Link className="btn primary" to={`/b/${bid}/p3`}>Go to Phase 3 →</Link></span></div></section>}
        {phase === 3 && V!.foot && <section className="panel">
          <FootView f={{ hint: V!.foot.hint, download: { label: 'Phase 3 report (.docx)', href: 'report/p3.docx' } }} act={act} busy={m.isPending} base={base}
            extra={<>
              <button type="button" className={`btn${V!.done ? ' primary' : ''}`} disabled={dis} onClick={() => act('plan')}>{V!.foot.plan ? 'Refresh project plan' : 'Create project plan'}</button>
              {!V!.done ? <button type="button" className="btn primary" disabled={dis || !!V!.foot.block} onClick={() => act('complete')}>Complete {V!.nav.find(x => x.k === V!.step)?.t}</button>
                : V!.nav.every(x => x.done) ? <Link className="btn" to={`/console?b=${bid}`}>Back to dashboard</Link>
                  : <button type="button" className="btn" onClick={() => go(V!.nav[V!.nav.findIndex(x => x.k === V!.step) + 1].k)}>Next stage →</button>}</>} />
        </section>}
        {phase === 3 && V!.plan && <SectionView s={V!.plan} act={act} busy={m.isPending} base={base} />}
      </div>
    </div>
  )
}
