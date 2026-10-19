// Fix plan: which uploaded files need fixing, what to change, who owns it and by when.
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, type FixView } from '../api'
import { Blocks } from '../components/sections'
import { ClientPicker, TopBar } from '../components/Shell'
import { ErrorNote, Spinner, toast } from '../components/ui'

const SEV = ['Critical', 'High', 'Medium', 'Low']

export default function FixPlan() {
  const { id } = useParams()
  const bid = Number(id)
  const nav = useNavigate()
  const [sp, setSp] = useSearchParams()
  const file = sp.get('file') || '', type = sp.get('type') || 'all'
  const q = useQuery({ queryKey: ['fix', bid, file, type], queryFn: () => api.get<FixView>(`/borrowers/${bid}/fix?type=${type}${file ? `&file=${file}` : ''}`), placeholderData: p => p })
  const [busy, setBusy] = useState(false)
  const P = q.data
  const pickFile = (k: string) => { setSp({ file: k }, { replace: true }); setTimeout(() => document.getElementById('fixDetail')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80) }
  const header = <TopBar back={{ to: `/console?b=${bid}`, label: '← Back' }} sub="Fix plan · Which files need fixing and what to change"
    right={<span className="dclient">Client <ClientPicker id={bid} onPick={x => nav(`/b/${x}/fix`)} /></span>} />
  if (q.isLoading) return <>{header}<Spinner /></>
  if (q.error) return <>{header}<ErrorNote error={q.error} /></>
  if (!P!.available) return <>{header}<section className="panel"><div className="summary"><div className="headline">The fix plan needs the Phase 1 Clean results.</div><p className="hint">{P!.why}</p></div></section></>
  if (P!.empty) return <>{header}<section className="panel"><div className="empty"><b>Nothing to fix</b><span className="hint">No changes, escalations or invalid values were found for {P!.c}.</span></div></section></>
  const D = P!.detail
  return (
    <div>
      {header}
      <div className="col">
        <section className="panel"><div className="summary"><Blocks blocks={[{ type: 'headline', text: P!.headline }, P!.kpis]} act={() => undefined} />
          <div className="fixflow" aria-label="How a fix flows">{['Fix in the source file', 'Owner confirms', 'Re-upload, re-run Collector and Clean', 'Confidence updates'].map((t, i) =>
            <span key={t} style={{ display: 'contents' }}>{i > 0 && <i aria-hidden="true">→</i>}<span><b>{i + 1}</b>{t}</span></span>)}</div></div></section>

        <section className="panel"><h2>File map <small>Colour shows the worst open issue; the bar shows the mix</small></h2>
          <div className="flegend">{SEV.map(s => <span key={s}><i className={`s-${s.toLowerCase()}`} />{s}</span>)}<span><i className="s-done" />Nothing open</span></div>
          {P!.groups.map(g => <div className="fgroup" key={g.label}><h3>{g.label} <span className="hint">{g.tiles.length} file{g.tiles.length > 1 ? 's' : ''}</span></h3>
            <div className="ftiles">{g.tiles.map(t => <button type="button" key={t.k} className={`ftile sev-${t.worst}${D?.k === t.k ? ' on' : ''}`} aria-pressed={D?.k === t.k} onClick={() => pickFile(t.k)}>
              <span className="fic" aria-hidden="true">{/\.csv$/i.test(t.name) ? 'CSV' : 'XLSX'}</span><span className="fn">{t.name}</span>
              <span className="fc"><b>{t.open}</b> to fix{t.done ? ` · ${t.done} done` : ''}</span>
              <div className="sevbar">{t.mix.filter(x => x.pct).map(x => <i key={x.s} className={`s-${x.s}`} style={{ width: `${x.pct}%` }} />)}</div></button>)}</div></div>)}
        </section>

        <section className="panel"><h2>Plan <small>What to fix first, by file</small></h2>
          <div className="lanes">{P!.lanes.map(l => <div className="lane" key={l.n}><div className="lh"><b>{l.n}</b><span className="hint">{l.w} · {l.count} fixes</span></div>
            {l.cards.length ? l.cards.map(c => <button type="button" key={c.k} className="lcard" onClick={() => pickFile(c.k)}><b>{c.name}</b><span className="hint">{c.what}</span><span className="hint">Due by {c.due}</span></button>)
              : <span className="hint">Nothing in this lane.</span>}</div>)}</div>
        </section>

        {D && <section className="panel" id="fixDetail"><h2>{D.name} <small>{D.folder}</small></h2>
          <div className="sec"><div className="hint">Sources in this file: {D.sources.join(', ')}</div>
            <div className="fixfilter">{D.types.filter(t => t.n).map(t => <button type="button" key={t.k} className={`chipbtn${D.type === t.k ? ' on' : ''}`}
              onClick={() => setSp({ file: D.k, type: t.k }, { replace: true })}>{t.t} <span>{t.n}</span></button>)}</div></div>
          <Blocks blocks={[D.table]} act={() => undefined} />
          <div className="foot"><span className="hint" role="status">The fix list is a new workbook with one sheet per file. Source files are never changed.</span>
            <button type="button" className="btn primary" disabled={busy} onClick={async () => { setBusy(true)
              try { await api.download(`/borrowers/${bid}/fix.xlsx`, 'Data360 Fix Plan.xlsx') } catch (e) { toast(String(e)) } finally { setBusy(false) } }}>{busy ? 'Building workbook…' : 'Download fix list (.xlsx)'}</button></div>
        </section>}
      </div>
    </div>
  )
}
