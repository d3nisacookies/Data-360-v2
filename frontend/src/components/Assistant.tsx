// "Ask Data 360": a chat panel about the selected client. The model runs behind the API (local
// Ollama by default); the browser never holds a key, and names and IDs are redacted on the server.
import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'
import { api, getToken } from '../api'
import { lastClient } from './Shell'
import { toast } from './ui'

interface Status {
  provider: string; model: string; label: string; configured: boolean; missing: string; local: boolean; redaction: boolean
  borrower: { id: number; name: string } | null; enabled: boolean; can_toggle: boolean
}
interface Turn { role: 'user' | 'assistant'; content: string; err?: boolean; pending?: boolean; tools?: string[] }

const SUGGEST = ['Why is the credit memo decision what it is?', 'Which sources disagree on the facility amount?', 'Summarise the data quality for this client',
  'Which files need fixing first?', 'What does BCBS 239 expect for risk data?', 'Explain IFRS 9 stage 3 in plain terms']

function useClientId(): number | null {
  const loc = useLocation()
  const m = /^\/b\/(\d+)/.exec(loc.pathname)
  if (m) return Number(m[1])
  const b = new URLSearchParams(loc.search).get('b')
  return b ? Number(b) : lastClient()
}

function inline(s: string): ReactNode[] {
  return s.split(/(\*\*[^*]+\*\*|`[^`]+`)/).map((x, i) => x.startsWith('**') && x.endsWith('**') ? <b key={i}>{x.slice(2, -2)}</b>
    : x.startsWith('`') && x.endsWith('`') ? <code key={i}>{x.slice(1, -1)}</code> : <Fragment key={i}>{x}</Fragment>)
}
function Md({ text }: { text: string }) {
  const out: ReactNode[] = []
  let list: string[] = []
  const flush = () => { if (list.length) { out.push(<ul key={out.length}>{list.map((l, i) => <li key={i}>{inline(l)}</li>)}</ul>); list = [] } }
  for (const line of text.split('\n')) {
    const m = /^\s*(?:[-•*]|\d+\.)\s+(.*)/.exec(line)
    if (m) { list.push(m[1]); continue }
    flush()
    if (line.trim()) out.push(<p key={out.length}>{inline(line.replace(/^#+\s*/, ''))}</p>)
  }
  flush()
  return <>{out}</>
}

export default function Assistant() {
  const bid = useClientId()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [turns, setTurns] = useState<Record<number, Turn[]>>({})
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const ctl = useRef<AbortController | null>(null)
  const log = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const q = useQuery({ queryKey: ['assistant', bid], queryFn: () => api.get<Status>(`/assistant/status${bid ? `?borrower_id=${bid}` : ''}`), enabled: open })
  const S = q.data
  const T = (bid && turns[bid]) || []
  useEffect(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight }, [T, open])
  useEffect(() => { if (open) setTimeout(() => input.current?.focus(), 30)
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape' && open && !document.querySelector('.polmodal')) setOpen(false) }
    window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k) }, [open])

  const setT = (f: (t: Turn[]) => Turn[]) => bid && setTurns(all => ({ ...all, [bid]: f(all[bid] || []) }))
  async function ask(question: string) {
    question = question.trim()
    if (!question || busy || !bid) return
    const hist = [...T.filter(t => !t.pending && !t.err), { role: 'user' as const, content: question }].slice(-12).map(t => ({ role: t.role, content: t.content }))
    setT(t => [...t, { role: 'user', content: question }, { role: 'assistant', content: '', pending: true }])
    setText(''); setBusy(true)
    ctl.current = new AbortController()
    let ans: Turn
    try {
      const r = await fetch('/api/assistant/chat', { method: 'POST', signal: ctl.current.signal,
        headers: { 'Content-Type': 'application/json', ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}) },
        body: JSON.stringify({ borrower_id: bid, messages: hist }) })
      const j = await r.json().catch(() => ({}))
      ans = r.ok ? { role: 'assistant', content: j.answer, tools: j.tools } : { role: 'assistant', content: typeof j.detail === 'string' ? j.detail : `Something went wrong (${r.status}).`, err: true }
    } catch (e) {
      ans = { role: 'assistant', content: (e as Error).name === 'AbortError' ? 'Stopped.' : 'Could not reach the server.', err: (e as Error).name !== 'AbortError' }
    }
    setT(t => [...t.slice(0, -1), ans]); setBusy(false)
  }
  async function toggle(on: boolean) {
    if (!bid) return
    try { await api.put(`/assistant/clients/${bid}`, { enabled: on }); qc.invalidateQueries({ queryKey: ['assistant', bid] }); toast(on ? 'Assistant switched on for this client' : 'Assistant switched off for this client') }
    catch (e) { toast(String(e)) }
  }

  const ready = !!(S && S.configured && S.enabled && bid)
  const mode = !S ? 'Connecting…' : `${S.label}${S.model ? ` · ${S.model}` : ''}${S.redaction ? ' · names and IDs redacted' : ''}`
  return <>
    {!open && <button type="button" className="aifab" aria-expanded={false} onClick={() => setOpen(true)}>✦ Ask Data 360</button>}
    {open && <aside className="aipanel" aria-label="Data360 assistant">
      <div className="aihead"><div><b>Data360 assistant</b><span className="hint">{mode}</span></div>
        <span className="aihbtn">
          {S?.can_toggle && S.borrower && S.enabled && <button type="button" className="linkbtn" onClick={() => toggle(false)}>Switch off for this client</button>}
          <button type="button" className="linkbtn" disabled={busy} onClick={() => setT(() => [])}>Clear</button>
          <button type="button" className="linkbtn rm" aria-label="Close" onClick={() => setOpen(false)}>✕</button></span></div>
      <div className="ailog" ref={log} aria-live="polite">
        {!bid ? <div className="aiwelcome"><b>Choose a client first</b><span className="hint">Open a client in the console; the assistant answers about that client.</span></div>
          : S && !S.configured ? <div className="aikey"><b>The assistant is not set up on this server</b><span className="hint">{S.missing || 'AI_PROVIDER is off.'}</span></div>
          : S && !S.enabled ? <div className="aikey"><b>Switched off for {S.borrower?.name}</b>
              <span className="hint">Each client's data is only sent to the assistant once an administrator switches it on.{S.redaction ? ' Names, identifiers and personal details are replaced with tokens first.' : ''}{S.local ? ' The model runs on this server.' : ` Answers come from ${S.label}.`}</span>
              {S.can_toggle ? <button type="button" className="btn primary small" onClick={() => toggle(true)}>Switch on for {S.borrower?.name}</button> : <span className="hint">Ask an administrator to switch it on.</span>}</div>
          : !T.length ? <div className="aiwelcome"><b>Ask about the data or credit topics</b><span className="hint">Answers use the current results for {S?.borrower?.name || 'this client'}.</span>
              <div className="aisugg">{SUGGEST.map(s => <button key={s} type="button" className="chipbtn" disabled={!ready} onClick={() => ask(s)}>{s}</button>)}</div></div>
          : T.map((t, i) => <div key={i} className={`aimsg ${t.role}${t.err ? ' err' : ''}`}>{t.role === 'user' ? t.content : t.pending ? <span className="aithink">Thinking… a local model can take a minute.</span>
              : <><Md text={t.content} />{t.tools && t.tools.length > 0 && <div className="hint" style={{ marginTop: 4 }}>Looked up: {[...new Set(t.tools)].map(x => x.replace(/_/g, ' ')).join(', ')}</div>}</>}</div>)}
      </div>
      <div className="aiinput">
        <textarea ref={input} rows={2} value={text} disabled={!ready} placeholder="Ask about the data, the memo or a credit topic…" aria-label="Message"
          onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(text) } }} />
        {busy ? <button type="button" className="btn" onClick={() => ctl.current?.abort()}>Stop</button>
          : <button type="button" className="btn primary" disabled={!ready || !text.trim()} onClick={() => ask(text)}>Send</button>}
      </div>
      <div className="ainote hint">The assistant supports analysis; approvers make credit decisions.</div>
    </aside>}
  </>
}
