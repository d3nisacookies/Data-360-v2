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
}
export interface LogRow { n: number; action: string; record: string; field: string; from: string; to: string; reason: string; source: string; by: string }
export interface Escalation { item: string; why: string; owner: string; due: string }
export interface CleanResult {
  selected: string[]; log: LogRow[]; escalations: Escalation[]; kept: number; total: number; version: string
  summary: Record<string, { n: number; text: string; rows?: { field: string; status: string; golden: string | null; source: string | null; detail: string }[]; decisions?: { field: string; chosen: string; why: string; replaced: string[] }[] }>
  golden: Record<string, Golden | null>
}
export interface NormResult { selected: string[]; version: string; out: Record<string, { n: number; text: string; head: string[]; rows: (string | number)[][] }> }
export interface Run<T> { id: number; step: string; at: string; by: string | null; params: unknown; result: T; stale: boolean; stale_reason?: string }
export interface PickCat { cat: string; use: string; src: string[]; attrs: string[] }
export interface Meta {
  assess: Record<string, string>; clean: Record<string, string>; normalise: Record<string, string>; reference_date: string
  outputs: Record<string, string>; standard_outputs: string[]; attributes: Record<string, string>; standard_attributes: string[]; pick_sources: PickCat[]
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
  created_at: string; ingested_at: string | null; error: string; mapping: Mapping; duplicate?: boolean
  summary: { observations?: number; records?: number; borrowers?: { id: number; name: string }[]; sources?: string[]; skipped_rows?: number }
  preview?: { headers: string[]; rows: (string | null)[][] } | null
}
export interface FieldDef { key: string; label: string; type: string; critical: boolean; section: string; synonyms: string[] }
