// Draws the screens the API describes (credit memo, Phase 2, Phase 3, project plans) in the
// console's look. Buttons, selects and inputs call `act(action, arg, value)`, which posts to the
// API and redraws with the refreshed screen.
import { Fragment, useEffect, useState, type ReactNode } from 'react'
import { api, type Block, type Cell, type Foot, type Sec } from '../api'
import { useAuth } from '../auth'
import { Bold, MiniBar, toast } from './ui'

export type Act = (action: string, arg?: unknown, value?: unknown) => void | Promise<unknown>

/* eslint-disable @typescript-eslint/no-explicit-any */
export function CellView({ c, act, busy }: { c: Cell; act: Act; busy?: boolean }): ReactNode {
  const { canEdit } = useAuth()
  if (c === null || c === undefined) return null
  if (typeof c !== 'object') return <>{String(c)}</>
  const x = c as any
  switch (x.t) {
    case 'chip': return <span className={`chip ${x.kind}`}>{x.text}</span>
    case 'bold': return <><b>{x.text}</b>{x.hint ? <div className="hint">{x.hint}</div> : null}</>
    case 'mono': return <span className="mono">{x.text}</span>
    case 'hint': return <span className="hint">{x.text}</span>
    case 'cell': return <span title={x.title || undefined}>{x.strong ? <b>{x.text}</b> : x.text}</span>
    case 'span': return <span className={x.cls}>{x.text}</span>
    case 'bar': return <><MiniBar pct={x.pct} tone={x.tone || undefined} />{x.text ? <span className="hint">{x.text}</span> : null}</>
    case 'uplift': return <div className="uplift"><i className="now" style={{ width: `${x.now}%` }} /><i className="up" style={{ left: `${x.now}%`, width: `${Math.max(0, x.to - x.now)}%`, ...(x.tone ? { background: `var(--${x.tone})` } : {}) }} /></div>
    case 'group': return <span className="cellgrp">{x.items.map((y: Cell, i: number) => <Fragment key={i}><CellView c={y} act={act} busy={busy} /></Fragment>)}</span>
    case 'btn':
      return <button type="button" className={`btn small${x.primary ? ' primary' : ''}`} disabled={x.disabled || busy || !canEdit}
        onClick={() => { if (x.confirm && !window.confirm(x.confirm)) return; act(x.action, x.arg) }}>{x.label}</button>
    case 'select':
      return <select value={x.value} disabled={x.disabled || busy || !canEdit} aria-label={x.placeholder} onChange={e => act(x.action, x.arg, e.target.value)}>
        <option value="">{x.placeholder}</option>{x.options.map((o: string) => <option key={o}>{o}</option>)}</select>
    case 'num': return <NumInput x={x} act={act} disabled={x.disabled || busy || !canEdit} />
    default: return <>{x.text ?? ''}</>
  }
}

function NumInput({ x, act, disabled }: { x: any; act: Act; disabled: boolean }) {
  const [v, setV] = useState(String(x.value))
  useEffect(() => setV(String(x.value)), [x.value])
  const commit = () => { if (v !== String(x.value) && v.trim() !== '') act(x.action, x.arg, Number(v)) }
  return <input type="number" min={0} step={x.step} value={v} disabled={disabled} aria-label={x.label || String(x.arg)}
    onChange={e => setV(e.target.value)} onBlur={commit} onKeyDown={e => { if (e.key === 'Enter') commit() }} />
}

function TableView({ b, act, busy, filter }: { b: Block; act: Act; busy?: boolean; filter?: string }) {
  const num: number[] = b.num || []
  const heat = b.rows.some((r: Cell[]) => r.some(c => c && typeof c === 'object' && String((c as any).cls || '').startsWith('hc')))
  const rows = filter ? b.rows.filter((r: Cell[]) => JSON.stringify(r).toLowerCase().includes(filter.toLowerCase())) : b.rows
  return (
    <div className={`tblwrap${b.flat ? ' flat' : ''}`}>
      <table className={heat ? 'heat' : undefined}>
        <thead><tr>{b.head.map((h: string, i: number) => <th key={i} className={num.includes(i) ? 'num' : undefined}>{h}</th>)}</tr></thead>
        <tbody>
          {rows.length ? rows.map((r: Cell[], i: number) => (
            <tr key={i} className={b.rowClass?.[b.rows.indexOf(r)] || undefined}>
              {r.map((c, j) => { const x = c as any
                const cls = [num.includes(j) ? 'num' : '', x && typeof x === 'object' && x.t === 'cell' ? x.cls : ''].filter(Boolean).join(' ')
                return <td key={j} className={cls || undefined} colSpan={x && typeof x === 'object' && x.colspan ? x.colspan : undefined}><CellView c={c} act={act} busy={busy} /></td> })}
            </tr>))
            : <tr><td colSpan={b.head.length} className="hint">Nothing to show.</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

function Bars({ items }: { items: any[] }) {
  return <div className="bars">{items.map((x, i) => <div className="br" key={i}><span>{x.label}{x.sub ? <small>{x.sub}</small> : null}</span><MiniBar pct={x.pct} tone={x.tone} /><b>{x.value}</b></div>)}</div>
}

/** One block. `zone` tells the caller which wrapper it belongs in. */
function zoneOf(b: Block): 'summary' | 'flat' | 'pad' {
  if (['headline', 'kpis', 'decision'].includes(b.type)) return 'summary'
  if ((b.type === 'table' && b.flat) || ['cards', 'details', 'html', 'search', 'range', 'polnote', 'ptrack'].includes(b.type)) return 'flat'
  return 'pad'
}

function BlockView({ b, act, busy, state }: { b: Block; act: Act; busy?: boolean; state: { filter: string; setFilter: (s: string) => void } }): ReactNode {
  const { canEdit } = useAuth()
  switch (b.type) {
    case 'headline': return <div className="headline"><Bold text={b.text} /></div>
    case 'kpis': return <div className={`kpis${b.five ? ' five' : ''}`}>{b.items.map((k: any, i: number) =>
      <div className="kpi" key={i}><div className={`v${String(k.v).length > 12 ? ' sm' : ''}`} style={k.tone ? { color: `var(--${k.tone})` } : undefined}>{k.v}</div><div className="k">{k.k}</div></div>)}</div>
    case 'decision': return <div className={`cmdec ${b.tone || ''}`}><span className="hint">{b.label}</span><b>{b.value}</b>{b.why ? <span>{b.why}</span> : null}</div>
    case 'table': return <TableView b={b} act={act} busy={busy} filter={b.filterable ? state.filter : undefined} />
    case 'h3': return <h3>{b.text}</h3>
    case 'hint': return <p className={`hint${b.tone ? ' ' + b.tone : ''}`}>{b.text}</p>
    case 'notes': return <ul className="notes">{b.items.map((t: string, i: number) => <li key={i}>{t}</li>)}</ul>
    case 'bars': return <Bars items={b.items} />
    case 'polnote': return <div className="polnote" style={{ marginTop: 12 }}>{b.text} <button type="button" className="linkbtn" onClick={() => window.dispatchEvent(new Event('d360:policies'))}>Change</button></div>
    case 'twocol': return <div className="cm2col">{b.cols.map((c: any, i: number) => <div key={i}><h3>{c.title}</h3>
      {b.ordered ? <ol>{c.items.map((t: string, j: number) => <li key={j}>{t}</li>)}</ol> : <ul>{c.items.map((t: string, j: number) => <li key={j}>{t}</li>)}</ul>}</div>)}</div>
    case 'cards': return <div className="dcards">{b.items.map((d: any, i: number) => (
      <div key={i} className={`dcard ${d.rate || ''}`}>
        <div className="dtop"><span className="dn">{d.title}</span>{d.chip && <span className={`chip ${d.chip[0]}`}>{d.chip[1]}</span>}</div>
        {d.hint && <div className="hint">{d.hint}</div>}
        {d.details && <details><summary className="linkbtn">{d.details.label}</summary><TableView b={{ type: 'table', head: d.details.head, rows: d.details.rows }} act={act} /></details>}
        {d.btn && <CellView c={d.btn} act={act} busy={busy} />}
      </div>))}</div>
    case 'matrix': return <div className="matrix" role="img" aria-label="Impact and effort matrix">
      {b.quads.map((q: any) => <div key={q.q} className={`mq ${q.cls}`}><div className="mqh"><b>{q.q}</b><span className="hint">{q.d}</span></div>
        {q.items.length ? q.items.map((r: any) => <span key={r.id} className="mchip" title={r.t}>{r.id}</span>) : <span className="hint">None</span>}</div>)}
      <span className="axis y">Impact ↑</span><span className="axis x">Effort →</span></div>
    case 'gantt': return <div className="gantt" role="img" aria-label="Initiative timeline across Phase 3 horizons">
      <div className="gh"><span /><div className="gscale">{b.scale.map((h: any) => <span key={h.n} style={{ width: `${(h.e - h.s) / b.W * 100}%` }}>{h.n}<small>{h.s}–{h.e === 18 ? '12+' : h.e} m</small></span>)}</div></div>
      {b.rows.map((r: any) => <div className="gr" key={r.name}><span className="gl"><b>{r.name}</b><small>{r.sub}</small></span>
        <div className="gtrack"><i style={{ left: `${r.start / b.W * 100}%`, width: `${(r.end - r.start) / b.W * 100}%` }}><em>{r.start}–{r.end === 18 ? '12+' : r.end} m</em></i></div></div>)}</div>
    case 'pgantt': return <div className="pgantt" style={{ ['--wk' as string]: `${100 / Math.max(1, b.weeks.length)}%` }} role="img" aria-label="Project plan Gantt chart">
      <div className="pgr head"><span /><div className="pgw">{b.weeks.map((w: string, i: number) => <span key={i}>{w}</span>)}</div></div>
      {b.rows.map((r: any, i: number) => r.ws ? <div className="pgr ws" key={i}><span><b>{r.ws}</b></span><div className="pgt" /></div>
        : <div className="pgr" key={i}><span className="pgl" title={r.label}>{r.label}</span><div className="pgt"><i className={`${r.ms ? 'ms' : ''}${r.done ? ' done' : ''}`} style={{ left: `${r.left}%`, width: `${r.width}%` }} title={r.title} /></div></div>)}</div>
    case 'radio': return <div className="scopes" role="radiogroup" aria-label="Scope">{b.options.map((o: any) => (
      <label key={o.k} className={b.value === o.k ? 'on' : ''}><input type="radio" name={b.action} checked={b.value === o.k} disabled={b.disabled || busy || !canEdit} onChange={() => act(b.action, null, o.k)} />
        <span><b>{o.t}</b><span className="hint">{o.d}</span></span></label>))}</div>
    case 'assume': return <div className="assume">{b.items.map((x: any, i: number) => <label key={i}><span>{x.label}{x.unit ? <> <em>{x.unit}</em></> : null}</span><CellView c={{ ...x.input, label: x.label }} act={act} busy={busy} /></label>)}</div>
    case 'range': return <RangeInput b={b} act={act} disabled={busy || !canEdit} />
    case 'search': return <SearchInput b={b} act={act} />
    case 'filter': return <input type="search" placeholder={b.placeholder} value={state.filter} onChange={e => state.setFilter(e.target.value)} aria-label={b.placeholder} />
    case 'ptrack': return <div className="p3track">{b.items.map((x: any, i: number) => <div key={i}><span className="hint">{x.label}</span><b className={x.small ? 'sm' : undefined}>{x.value}</b>
      {x.sub && <span className="hint">{x.sub}</span>}{x.pct !== undefined && <MiniBar pct={x.pct} tone="ph3" />}</div>)}</div>
    case 'html': return <div className="cmprev"><article className="rdoc" dangerouslySetInnerHTML={{ __html: b.html }} /></div>
    case 'details': return <DetailsBlock b={b} act={act} busy={busy} />
    case 'approvals': return <Approvals b={b} act={act} busy={busy} />
    case 'edit': return <EditBox b={b} act={act} busy={busy} />
    default: return null
  }
}

function RangeInput({ b, act, disabled }: { b: Block; act: Act; disabled: boolean }) {
  const [v, setV] = useState(b.value)
  useEffect(() => setV(b.value), [b.value])
  return <div className="sec"><label className="thr">{b.label} <input type="range" min={b.min} max={b.max} step={b.step} value={v} disabled={disabled}
    onChange={e => setV(Number(e.target.value))} onMouseUp={() => act(b.action, null, v)} onTouchEnd={() => act(b.action, null, v)} onKeyUp={() => act(b.action, null, v)} aria-label={b.label} /><b>{v}</b></label></div>
}

function SearchInput({ b, act }: { b: Block; act: Act }) {
  const [v, setV] = useState(b.value)
  useEffect(() => { if (v === b.value) return; const t = setTimeout(() => act(b.action, null, v), 350); return () => clearTimeout(t) }, [v]) // eslint-disable-line react-hooks/exhaustive-deps
  return <div className="sec"><input type="search" value={v} placeholder={b.placeholder} aria-label="Search business terms" onChange={e => setV(e.target.value)} /></div>
}

function DetailsBlock({ b, act, busy }: { b: Block; act: Act; busy?: boolean }) {
  const [filter, setFilter] = useState('')
  const blocks = b.blocks.map((x: Block) => x.type === 'table' && b.blocks.some((y: Block) => y.type === 'filter') ? { ...x, filterable: true, flat: true } : x)
  return <details className="trail"><summary><h2>{b.summary}</h2></summary>
    <Blocks blocks={blocks} act={act} busy={busy} filter={filter} setFilter={setFilter} /></details>
}

function Approvals({ b, act, busy }: { b: Block; act: Act; busy?: boolean }) {
  const { canEdit } = useAuth()
  return <div className="tblwrap"><table className="cmappr"><thead><tr><th>Approver</th><th>Name</th><th>Decision</th><th>Comment</th><th>Date</th></tr></thead><tbody>
    {b.rows.map((a: any) => <tr key={a.i}><td><b>{a.role}</b></td>
      <td><TextCommit value={a.name} placeholder="Name" disabled={b.locked || busy || !canEdit} label={`${a.role} name`} onCommit={v => act('approval', { i: a.i, field: 'name', value: v })} /></td>
      <td><select value={a.decision} disabled={!a.can || busy || !canEdit} aria-label={`${a.role} decision`} onChange={e => act('approval', { i: a.i, field: 'decision', value: e.target.value })}>
        <option value="">{a.i === b.next ? 'Choose…' : 'Pending'}</option>{b.decisions.map((d: string) => <option key={d}>{d}</option>)}</select></td>
      <td><TextCommit value={a.comment} placeholder="Comment" disabled={b.locked || busy || !canEdit} label={`${a.role} comment`} onCommit={v => act('approval', { i: a.i, field: 'comment', value: v })} /></td>
      <td className="mono">{a.date || '—'}</td></tr>)}</tbody></table></div>
}

function TextCommit({ value, placeholder, disabled, label, onCommit }: { value: string; placeholder: string; disabled?: boolean; label: string; onCommit: (v: string) => void }) {
  const [v, setV] = useState(value)
  useEffect(() => setV(value), [value])
  return <input type="text" value={v} placeholder={placeholder} disabled={disabled} aria-label={label} onChange={e => setV(e.target.value)}
    onBlur={() => { if (v !== value) onCommit(v) }} onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }} />
}

function EditBox({ b, act, busy }: { b: Block; act: Act; busy?: boolean }) {
  const { canEdit } = useAuth()
  const [k, setK] = useState(''); const [to, setTo] = useState(''); const [why, setWhy] = useState('')
  const dis = b.disabled || busy || !canEdit
  return <div className="cmedit">
    <select value={k} disabled={dis} aria-label="Field to edit" onChange={e => { setK(e.target.value); setTo(b.fields.find((f: any) => f.key === e.target.value)?.v || '') }}>
      <option value="">Choose a field…</option>{b.fields.map((f: any) => <option key={f.key} value={f.key}>{f.label}</option>)}</select>
    <input type="text" value={to} placeholder="New value" disabled={dis} aria-label="New value" onChange={e => setTo(e.target.value)} />
    <input type="text" value={why} placeholder="Reason (required)" disabled={dis} aria-label="Reason" onChange={e => setWhy(e.target.value)} />
    <button type="button" className="btn" disabled={dis} onClick={async () => {
      if (!k || !to.trim()) return toast('Choose a field and enter a new value')
      if (!why.trim()) return toast('Give a reason for the edit')
      await act('edit', { key: k, to, reason: why }); setK(''); setTo(''); setWhy('')
    }}>Apply edit</button></div>
}

export function Blocks({ blocks, act, busy, filter = '', setFilter = () => {} }: { blocks: Block[]; act: Act; busy?: boolean; filter?: string; setFilter?: (s: string) => void }) {
  // group consecutive blocks into the console's wrappers: summary, padded issues area, or full-width
  const groups: { zone: string; items: Block[] }[] = []
  for (const b of blocks) {
    const z = zoneOf(b)
    const last = groups[groups.length - 1]
    if (last && last.zone === z && z !== 'flat') last.items.push(b)
    else groups.push({ zone: z, items: [b] })
  }
  const state = { filter, setFilter }
  return <>{groups.map((g, i) => {
    const inner = g.items.map((b, j) => <Fragment key={j}><BlockView b={b} act={act} busy={busy} state={state} /></Fragment>)
    if (g.zone === 'summary') return <div className="summary" key={i}>{inner}</div>
    if (g.zone === 'pad') return <div className="issues" style={i === 0 ? { paddingTop: 14 } : undefined} key={i}>{inner}</div>
    if (g.items[0].type === 'filter' || g.items[0].type === 'search' || g.items[0].type === 'range') return <div className="sec" key={i}>{inner}</div>
    return <Fragment key={i}>{inner}</Fragment>
  })}</>
}

export function FootView({ f, act, busy, base, onNext, extra }: { f: Foot; act: Act; busy?: boolean; base: string; onNext?: (step: string) => void; extra?: ReactNode }) {
  const { canEdit } = useAuth()
  const [name, setName] = useState('')
  const [dl, setDl] = useState('')
  const download = async (href: string, label: string) => {
    setDl(href)
    try { await api.download(`${base}/${href}`, label) } catch (e) { toast(e instanceof Error ? e.message : String(e)) } finally { setDl('') }
  }
  const dls = [...(f.download ? [f.download] : []), ...(f.downloads || [])]
  return <div className="secfoot"><span className="hint" role="status">{f.hint}</span>
    <span className="footbtns">
      {dls.map(d => <button key={d.href} type="button" className={`btn${'primary' in d && d.primary ? ' primary' : ''}`} disabled={!!dl} onClick={() => download(d.href, d.label)}>{dl === d.href ? 'Building…' : d.label}</button>)}
      {(f.buttons || []).map((c, i) => <Fragment key={i}><CellView c={c} act={act} busy={busy} /></Fragment>)}
      {f.approve && canEdit && <span className="approve"><input type="text" value={name} onChange={e => setName(e.target.value)} placeholder={f.approve.placeholder} aria-label={f.approve.placeholder} />
        <button type="button" className="btn primary" disabled={busy} onClick={() => { if (!name.trim()) return toast('Enter the approver name'); act(f.approve!.action, null, name.trim()) }}>{f.approve.label}</button></span>}
      {f.next && onNext && <button type="button" className="btn primary" onClick={() => onNext(f.next!.step)}>{f.next.label}</button>}
      {extra}
    </span></div>
}

export function SectionView({ s, act, busy, base, onNext, className = '' }: { s: Sec; act: Act; busy?: boolean; base: string; onNext?: (step: string) => void; className?: string }) {
  const [filter, setFilter] = useState('')
  return (
    <section className={`panel ${className}`} id={s.id || undefined}>
      <h2>{s.title} <small>{s.sub}</small></h2>
      <Blocks blocks={s.blocks} act={act} busy={busy} filter={filter} setFilter={setFilter} />
      {s.foot && <FootView f={s.foot} act={act} busy={busy} base={base} onNext={onNext} />}
    </section>
  )
}
