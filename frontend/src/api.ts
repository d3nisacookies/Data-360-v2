// Thin fetch wrapper: adds the token, turns API errors into readable messages.
const TOKEN_KEY = 'd360.token'

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(t: string | null) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* private mode */ }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

async function handle<T>(r: Response): Promise<T> {
  if (r.status === 401 && getToken()) { setToken(null); window.location.href = '/login' }
  if (!r.ok) {
    let msg = r.statusText
    try {
      const j = await r.json()
      msg = typeof j.detail === 'string' ? j.detail : Array.isArray(j.detail) ? j.detail.map((d: { msg: string }) => d.msg).join('; ') : msg
    } catch { /* not json */ }
    throw new ApiError(r.status, msg || `Request failed (${r.status})`)
  }
  const ct = r.headers.get('content-type') || ''
  return (ct.includes('json') ? r.json() : r.blob()) as Promise<T>
}

function headers(extra?: Record<string, string>): Record<string, string> {
  const t = getToken()
  return { ...(t ? { Authorization: `Bearer ${t}` } : {}), ...extra }
}

export const api = {
  get: <T>(p: string) => fetch(`/api${p}`, { headers: headers() }).then(r => handle<T>(r)),
  post: <T>(p: string, body?: unknown) =>
    fetch(`/api${p}`, { method: 'POST', headers: headers({ 'Content-Type': 'application/json' }), body: JSON.stringify(body ?? {}) }).then(r => handle<T>(r)),
  put: <T>(p: string, body: unknown) =>
    fetch(`/api${p}`, { method: 'PUT', headers: headers({ 'Content-Type': 'application/json' }), body: JSON.stringify(body) }).then(r => handle<T>(r)),
  patch: <T>(p: string, body: unknown) =>
    fetch(`/api${p}`, { method: 'PATCH', headers: headers({ 'Content-Type': 'application/json' }), body: JSON.stringify(body) }).then(r => handle<T>(r)),
  del: <T>(p: string) => fetch(`/api${p}`, { method: 'DELETE', headers: headers() }).then(r => handle<T>(r)),
  form: <T>(p: string, fd: FormData) => fetch(`/api${p}`, { method: 'POST', headers: headers(), body: fd }).then(r => handle<T>(r)),
  login: (email: string, password: string) => {
    const fd = new URLSearchParams({ username: email, password })
    return fetch('/api/auth/login', { method: 'POST', body: fd }).then(r => handle<{ access_token: string; user: User }>(r))
  },
  download: async (p: string, fallbackName: string) => {
    const r = await fetch(`/api${p}`, { headers: headers() })
    if (!r.ok) return handle(r)
    const cd = r.headers.get('content-disposition') || ''
    const name = /filename="([^"]+)"/.exec(cd)?.[1] || fallbackName
    const url = URL.createObjectURL(await r.blob())
    const a = Object.assign(document.createElement('a'), { href: url, download: name })
    document.body.appendChild(a); a.click(); a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 2000)
  },
}

// ---------- types ----------
export type Role = 'admin' | 'analyst' | 'viewer'
export interface User { id: number; email: string; name: string; role: Role; active: boolean }
export interface StepState { run_id: number; at: string; stale: boolean; by: string | null; stale_reason?: string }
export interface Steps { collect: StepState | null; seek: StepState | null; assess: StepState | null; clean: StepState | null; normalise: StepState | null }
export interface Overall { score: number | null; rating: Rating; cap: string }
export type Rating = 'high' | 'med' | 'low' | 'na'
export interface BorrowerRow {
  id: number; name: string; aliases: string[]; facility_ids: string[]; observations: number; sources: number
  steps: Steps; confidence: Overall | null
}
export interface SourceRow { source: string; zone: string; records: number; elements: number; newest: string | null; flags: number }
export interface BorrowerDetail {
  id: number; name: string; aliases: string[]; facility_ids: string[]; sources: SourceRow[]
  uploads: { id: number; filename: string; at: string }[]; steps: Steps; version: string; reference_date: string; scope: string[] | null
}
export interface Issue { issue: string; where: string; detail: string }
export interface Dim { score: number | null; rating: Rating; basis: string; issues: Issue[]; question: string; before: number | null }
export interface Golden { value: string; display: string; source: string; record: string; as_of: string | null; why: string; rule: string; support: string[] }
export interface AssessResult {
  borrower: string; version: string; selected: string[]; ref_date: string; overall: Overall
  stages: { key: string; label: string; version: string; dims: Record<string, number | null>; score: number | null; rating: Rating; cap: string }[]
  dims: Record<string, Dim>; counts: { records: number; elements: number; sources: number; removed: number }
  provider_flags: Record<string, number>; golden: Record<string, Golden | null>
  inputs?: { collector: boolean; seeker: boolean; scope: string[] | null }
  crit?: Record<string, Crit>
}
export interface LogRow { n: number; action: string; record: string; field: string; from: string; to: string; reason: string; source: string; by: string }
export interface Escalation { item: string; why: string; owner: string; due: string }
export interface CleanResult {
  selected: string[]; log: LogRow[]; escalations: Escalation[]; kept: number; total: number; version: string
  summary: Record<string, { n: number; text: string; rows?: { field: string; status: string; golden: string | null; source: string | null; detail: string }[]; decisions?: { field: string; chosen: string; why: string; replaced: string[] }[] }>
  golden: Record<string, Golden | null>
  picks?: Record<string, { text: string }>
}
export interface NormResult { picks?: Record<string, { text: string }>; selected: string[]; version: string; out: Record<string, { n: number; text: string; head: string[]; rows: (string | number)[][] }> }
export interface Run<T> { id: number; step: string; at: string; by: string | null; params: unknown; result: T; stale: boolean; stale_reason?: string }
export interface PickGroup { cat: string; items: { n: string; d: string }[] }
export interface Crit { score: number | null; basis: string; needs: string; status: string; cat: string }
export interface PickCat { cat: string; use: string; src: string[]; attrs: string[] }
export interface Meta {
  assess: Record<string, string>; clean: Record<string, string>; normalise: Record<string, string>; reference_date: string
  outputs: Record<string, string>; standard_outputs: string[]; attributes: Record<string, string>; standard_attributes: string[]; pick_sources: PickCat[]
  picks: Record<'assess' | 'clean' | 'normalise', PickGroup[]>
}
export interface CovGroup { label: string; source: string; n: number; in_scope: boolean; uploaded: boolean; held_elsewhere: number; field?: string }
export interface Coverage { output: string; desc: string; status: 'ok' | 'part' | 'none'; groups: CovGroup[]; hit: number; total: number; addable: string[]; missing: string[] }
export interface Location { source: string; in_scope: boolean; zone: string; records: number; elements: number; categories: [string, number][]; restricted: number; newest: string | null }
export interface CollectResult {
  sources: string[]; outputs: string[]; available: string[]; coverage: Coverage[]; locations: Location[]
  counts: { locations: number; records: number; elements: number; restricted: number; full: number }
}
export type SeekStatus = 'ok' | 'multi' | 'conf' | 'indirect' | 'pending' | 'miss'
export interface SeekHit { location: string; zone: string; field: string; value: string; record: string; as_of: string | null; flag: string }
export interface SeekAttr {
  attribute: string; status: SeekStatus; hits: SeekHit[]; values: { value: string; count: number; locations: string[] }[]; locations: string[]
  requested_from: string[]; field: string | null; note: string; potential: string; suppliers: string[]
}
export interface SeekResult { attributes: string[]; requested: string[]; results: SeekAttr[]; locations: number
  counts: { total: number; found: number; conflict: number; gap: number; pending: number } }
export interface MapCol { header: string; field?: string | null; confidence?: number; how?: string; role?: string | null; include?: boolean }
export interface Mapping {
  format: 'records' | 'dictionary' | 'unknown'; sheet: string; header_row: number; columns: MapCol[]
  defaults: { source: string; zone: string; borrower: string }; missing: string[]; rows: number; uncertain?: string[]
  sheets?: { name: string; rows: number; format?: string }[]; error?: string
}
export interface UploadRow {
  id: number; filename: string; status: 'detected' | 'needs_mapping' | 'ingested' | 'failed'; format: string; size: number
  created_at: string; ingested_at: string | null; error: string; mapping: Mapping; duplicate?: boolean; source_path?: string | null
  summary: { observations?: number; records?: number; borrowers?: { id: number; name: string }[]; sources?: string[]; skipped_rows?: number }
  preview?: { headers: string[]; rows: (string | null)[][] } | null
}
export type ScanOutcome = 'loaded' | 'duplicate' | 'not_recognised' | 'not_read_yet' | 'failed'
export interface ScanFile { path: string; kind: string; size?: number; modified?: string; outcome: ScanOutcome; note?: string; borrowers?: string[]; sources?: string[]; values?: number; upload_id?: number }
export interface ScanReport {
  root: string; at: string; by: string; seconds: number; found: number; truncated: boolean; borrowers: string[]
  counts: Record<ScanOutcome, number>; skipped: Record<string, number>; files: ScanFile[]
}
export interface ScanStatus { root: string; available: boolean; readonly: boolean; note: string; last: ScanReport | null }
export interface FieldDef { key: string; label: string; type: string; critical: boolean; section: string; synonyms: string[] }

// ---------- later steps (memo, Phase 2, Phase 3): server-described screens ----------
/* eslint-disable @typescript-eslint/no-explicit-any */
export type Cell = string | number | null | { t: string; [k: string]: any }
export interface Block { type: string; [k: string]: any }
export interface Foot {
  hint?: string; next?: { label: string; step: string }; buttons?: Cell[]
  download?: { label: string; href: string }; downloads?: { label: string; href: string; primary?: boolean }[]
  approve?: { action: string; label: string; placeholder: string }
}
export interface Sec { title: string; sub: string; blocks: Block[]; foot?: Foot | null; id?: string | null }
export interface Battery { pct: number; rating: Rating; cap: string; provisional: boolean; stages: { label: string; pct: number }[]; breakdown: { head: string[]; rows: string[][] } | null }
export interface StepPill { k?: string; go?: string; n: string; t: string; d: string; done: boolean; part: boolean }
export interface Overview {
  borrower: { id: number; name: string; facility_ids: string[] }; gates: { p1: boolean; p2: boolean; p3: boolean; open: Record<string, boolean> }
  kpis: { v: string; k: string; sm: boolean }[]; phases: { id: number; steps: StepPill[] }[]; battery: Battery | null; rules_on: number
}
export interface SetupList { std: { name: string; desc: string; on: boolean }[]; extra: { name: string; desc: string }[]; pick: string[]; count: string; locked: boolean }
export interface MemoView {
  available: boolean; why?: string; scope?: string; status?: string; version?: string; decision?: string; retained?: any
  setup?: { core: { no: string; t: string; d: string; on: boolean }[]; extra: { no: string; t: string; d: string }[]; pick: { no: string; t: string }[]; count: string
    stages: { k: number; n: string; t: string; d: string; done: boolean }[]; done: number }
  sections?: Sec[]
}
export interface PhaseView {
  available: boolean; why?: string; step: string; nav: { k: string; n: string; t: string; can: boolean; done: boolean; why?: string }[]
  crumb: string; h1: string; lbl?: string; setup: SetupList; scope: string; verb: string; sections: Sec[]
  approved?: { by: string; at: string } | null; track?: Block; init?: string; done?: string | null; has_result?: boolean
  foot?: { hint: string; block: string; plan: boolean }; plan?: Sec
}
export interface Policy { id: string; t: string; d: string; src: string; g: string }
export interface Policies { groups: { name: string; rules: Policy[] }[]; tested: string[]; on: string[]; all: string[] }
export interface FixView {
  available: boolean; why?: string; empty?: boolean; c: string; headline: string; kpis: Block
  groups: { label: string; tiles: { k: string; name: string; worst: string; open: number; done: number; mix: { s: string; pct: number }[]; on: boolean }[] }[]
  lanes: { n: string; w: string; count: number; cards: { k: string; name: string; what: string; due: string }[] }[]
  detail: { k: string; name: string; folder: string; sources: string[]; type: string; types: { k: string; t: string; n: number }[]; table: Block } | null
}
export interface ExecReport {
  callout: { tone: string; text: string }; battery: { pct: number; stages: { label: string; pct: number }[] } | null; bullets: string[]; actions: [string, string][]; file: string
  tasks: { cat: any[]; own: { name: string; kind: string; owner: string; steward: string; assigned: string }[]; flow: { name: string; steps: string[]; method: string }[]
    ref: { name: string; cycle: string; last: string | null; age: number | null; stale: number; status: string; basis: string }[]; n: number; el: number; gaps: number; owner_choices: string[] }
}
