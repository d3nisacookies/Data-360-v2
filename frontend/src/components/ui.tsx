import { useEffect, useState, type ReactNode } from 'react'
import type { Rating } from '../api'

export const RATE_LABEL: Record<Rating, string> = { high: 'High', med: 'Medium', low: 'Low', na: 'Not scored' }
const RATE_CHIP: Record<Rating, string> = { high: 'ok', med: 'warn', low: 'bad', na: 'idle' }

export function RateChip({ r }: { r: Rating }) {
  return <span className={`chip ${RATE_CHIP[r]}`}>{RATE_LABEL[r]}</span>
}

export function Chip({ kind, children }: { kind: 'ok' | 'warn' | 'bad' | 'info' | 'idle'; children: ReactNode }) {
  return <span className={`chip ${kind}`}>{children}</span>
}

export function Ring({ score, rating }: { score: number | null; rating: Rating }) {
  return <div className={`ring ${rating}`} style={{ ['--p' as string]: score ?? 0 }} role="img" aria-label={`Confidence ${score ?? 'not scored'} of 100`}><b>{score ?? '—'}</b></div>
}

export function Table({ head, rows, mono = [], empty = 'Nothing to show.' }: { head: string[]; rows: ReactNode[][]; mono?: number[]; empty?: string }) {
  return (
    <div className="tblwrap">
      <table>
        <thead><tr>{head.map(h => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>
          {rows.length ? rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className={mono.includes(j) ? 'mono' : undefined}>{c}</td>)}</tr>)
            : <tr><td colSpan={head.length} className="hint">{empty}</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null
  return <div className="callout bad" role="alert">{error instanceof Error ? error.message : String(error)}</div>
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return <span className="hint"><span className="spin" aria-hidden /> {label}…</span>
}

let toastSet: ((s: string) => void) | null = null
export function toast(msg: string) { toastSet?.(msg) }
export function Toaster() {
  const [msg, setMsg] = useState('')
  useEffect(() => { toastSet = setMsg; return () => { toastSet = null } }, [])
  useEffect(() => { if (!msg) return; const t = setTimeout(() => setMsg(''), 3200); return () => clearTimeout(t) }, [msg])
  return msg ? <div className="toast" role="status">{msg}</div> : null
}

export const when = (iso: string) => new Date(iso).toLocaleString('en-SG', { dateStyle: 'medium', timeStyle: 'short' })

export function Battery({ stages, small }: { stages: { label: string; pct: number }[]; small?: boolean }) {
  const last = stages[stages.length - 1].pct
  return (
    <div className={`battery${small ? ' sm' : ''}`} role="img" aria-label={stages.map(x => `${x.label} ${x.pct}%`).join(', ') + `, not confident ${100 - last}%`}>
      <div className="cell">
        {stages.map((x, i) => { const gain = i ? Math.max(0, x.pct - stages[i - 1].pct) : x.pct
          return gain ? <i key={i} className={`g g${i}`} style={{ width: `${gain}%` }} title={`${x.label}${i ? ' +' + gain : ' ' + x.pct}%`}>{gain >= 6 ? (i ? '+' + gain : x.pct + '%') : ''}</i> : null })}
        {last < 100 && <i className="r" style={{ width: `${100 - last}%` }}>{100 - last >= 6 ? `${100 - last}%` : ''}</i>}
      </div><span className="nub" />
    </div>
  )
}

export function MiniBar({ pct, tone }: { pct: number; tone?: string }) {
  return <div className="minibar wide"><i style={{ width: `${Math.max(0, Math.min(100, pct))}%`, ...(tone ? { background: `var(--${tone})` } : {}) }} /></div>
}

export function Bold({ text }: { text: string }) {
  // **bold** segments from server-written headlines
  return <>{text.split(/(\*\*[^*]+\*\*)/).map((s, i) => s.startsWith('**') ? <b key={i}>{s.slice(2, -2)}</b> : s)}</>
}
