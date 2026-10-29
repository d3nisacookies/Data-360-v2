import { useEffect, useRef, useState, type DragEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, type BorrowerRow, type FieldDef, type Mapping, type ScanOutcome, type ScanReport, type ScanStatus, type UploadRow } from '../api'
import { useAuth } from '../auth'
import { Chip, ErrorNote, Spinner, toast, when } from '../components/ui'

const STATUS: Record<UploadRow['status'], [string, 'ok' | 'warn' | 'bad' | 'idle']> = {
  ingested: ['Loaded', 'ok'], needs_mapping: ['Needs your review', 'warn'], failed: ['Failed', 'bad'], detected: ['Detected', 'idle'],
}
const DICT_ROLES: [string, string][] = [['id', 'Element ID'], ['source', 'Data source'], ['category', 'Category'], ['subcategory', 'Sub-category'],
  ['element', 'Data element'], ['dtype', 'Data type'], ['value', 'Value'], ['structure', 'Structure'], ['sensitivity', 'Sensitivity'], ['borrower', 'Borrower name']]
const MISSING: Record<string, string> = { borrower: 'Choose which borrower this file is for, or map a borrower column.',
  source: 'Name the source system or feed, or map a source column.', fields: 'Map at least one data column.' }

export default function Upload() {
  const { canEdit } = useAuth()
  const qc = useQueryClient()
  const [over, setOver] = useState(false)
  const [open, setOpen] = useState<number | null>(null)
  const [borrower, setBorrower] = useState('')
  const [source, setSource] = useState('')
  const input = useRef<HTMLInputElement>(null)
  const list = useQuery({ queryKey: ['uploads'], queryFn: () => api.get<UploadRow[]>('/uploads') })
  const send = useMutation({
    mutationFn: (files: File[]) => {
      const fd = new FormData()
      files.forEach(f => fd.append('files', f))
      fd.append('borrower', borrower); fd.append('source', source)
      return api.form<UploadRow[]>('/uploads', fd)
    },
    onSuccess: res => {
      qc.invalidateQueries({ queryKey: ['uploads'] }); qc.invalidateQueries({ queryKey: ['borrowers'] })
      const ok = res.filter(r => r.status === 'ingested').length, rev = res.filter(r => r.status === 'needs_mapping')
      toast(`${ok} loaded${rev.length ? `, ${rev.length} need review` : ''}${res.some(r => r.duplicate) ? ' (duplicates skipped)' : ''}`)
      if (rev.length) setOpen(rev[0].id)
    },
  })
  const pick = (fl: FileList | null) => { if (fl && fl.length) send.mutate(Array.from(fl)) }
  const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files) }
  const rows = list.data || []

  return (
    <div className="stack">
      <div><h1>Upload files</h1><p className="hint">Excel (.xlsx, .xlsm) or CSV, up to 50 MB each. Files are stored as uploaded; nothing is changed in them.</p></div>
      {canEdit ? (
        <section className="panel">
          <div className="pb stack">
            <div className={`drop${over ? ' over' : ''}`} onClick={() => input.current?.click()} onDragOver={e => { e.preventDefault(); setOver(true) }}
              onDragLeave={() => setOver(false)} onDrop={onDrop} role="button" tabIndex={0}
              onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && input.current?.click()} aria-label="Choose files to upload">
              <b>{send.isPending ? 'Reading files…' : 'Drop files here or click to choose'}</b>
              <span className="hint">Data360 detects the layout, maps the columns and recognises borrowers. Anything it is unsure about waits for you to review.</span>
              {send.isPending && <span className="spin" aria-hidden />}
            </div>
            <input ref={input} type="file" multiple accept=".xlsx,.xlsm,.csv" hidden onChange={e => { pick(e.target.files); e.target.value = '' }} />
            <details>
              <summary className="hint" style={{ cursor: 'pointer' }}>Optional: files without a borrower or source column</summary>
              <div className="row" style={{ marginTop: 10, alignItems: 'end' }}>
                <label className="f grow"><span className="lbl">Borrower</span><input type="text" value={borrower} onChange={e => setBorrower(e.target.value)} placeholder="e.g. HarbourVest" /></label>
                <label className="f grow"><span className="lbl">Source system or feed</span><input type="text" value={source} onChange={e => setSource(e.target.value)} placeholder="e.g. Loan systems, Bloomberg" /></label>
              </div>
            </details>
            <ErrorNote error={send.error} />
          </div>
        </section>
      ) : <div className="callout">Your role can view uploads but not add them.</div>}

      <ScanPanel canEdit={canEdit} />

      {open !== null && <MappingEditor key={open} id={open} onClose={() => setOpen(null)} />}
      <section className="panel">
        <div className="ph"><h2>Files</h2><span className="hint">{rows.length} uploaded</span></div>
        {list.isLoading ? <div className="pb"><Spinner /></div> : !rows.length ? <div className="pb hint">No files yet.</div> : (
          <div className="tblwrap" style={{ border: 0, borderRadius: 0, maxHeight: 'none' }}>
            <table>
              <thead><tr><th>File</th><th>Layout</th><th>Status</th><th>Result</th><th>Uploaded</th><th></th></tr></thead>
              <tbody>
                {rows.map(u => (
                  <tr key={u.id}>
                    <td style={{ maxWidth: 420 }}><b>{u.filename}</b>{u.source_path && <div className="hint mono" title="Found by the folder scan" style={{ wordBreak: 'break-all' }}>Scan · {u.source_path}</div>}{u.error && <div className="hint bad">{u.error}</div>}</td>
                    <td>{u.format === 'dictionary' ? 'Data dictionary' : u.format === 'records' ? 'Records' : '—'}{u.mapping?.sheet && <div className="hint">Sheet: {u.mapping.sheet}</div>}</td>
                    <td><Chip kind={STATUS[u.status][1]}>{STATUS[u.status][0]}</Chip></td>
                    <td className="hint">{u.status === 'ingested' ? <>{u.summary.observations?.toLocaleString()} values · {(u.summary.borrowers || []).length > 2 ? `${u.summary.borrowers!.length} borrowers` : (u.summary.borrowers || []).map((b, i) =>
                      <span key={b.id}>{i ? ', ' : ''}<Link to={`/b/${b.id}/p1/source`}>{b.name}</Link></span>)}</> : '—'}</td>
                    <td className="hint">{when(u.created_at)}</td>
                    <td><div className="row" style={{ gap: 6, flexWrap: 'nowrap' }}>
                      {canEdit && u.status !== 'failed' && <button className="btn small" onClick={() => setOpen(open === u.id ? null : u.id)}>{u.status === 'needs_mapping' ? 'Review' : 'Mapping'}</button>}
                    </div></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

function MappingEditor({ id, onClose }: { id: number; onClose: () => void }) {
  const qc = useQueryClient()
  const u = useQuery({ queryKey: ['upload', id], queryFn: () => api.get<UploadRow>(`/uploads/${id}`) })
  const fields = useQuery({ queryKey: ['fields'], queryFn: () => api.get<FieldDef[]>('/fields'), staleTime: Infinity })
  const borrowers = useQuery({ queryKey: ['borrowers'], queryFn: () => api.get<BorrowerRow[]>('/borrowers') })
  const [m, setM] = useState<Mapping | null>(null)
  const [loadedFor, setLoadedFor] = useState<string>('')
  const data = u.data
  const key = data ? `${data.id}:${data.mapping.sheet}:${data.mapping.format}` : ''
  if (data && key !== loadedFor) { setM(structuredClone(data.mapping)); setLoadedFor(key) }

  const sheet = useMutation({
    mutationFn: (s: string) => api.post<UploadRow>(`/uploads/${id}/sheet`, { sheet: s }),
    onSuccess: r => qc.setQueryData(['upload', id], r),
  })
  const go = useMutation({
    mutationFn: () => api.post<UploadRow>(`/uploads/${id}/ingest`, { mapping: m }),
    onSuccess: r => {
      toast(`Loaded ${r.summary.observations?.toLocaleString()} values`)
      qc.invalidateQueries({ queryKey: ['uploads'] }); qc.invalidateQueries({ queryKey: ['borrowers'] }); qc.invalidateQueries({ queryKey: ['upload', id] })
      onClose()
    },
  })
  const ready = !!(data && m)
  useEffect(() => { if (ready) document.getElementById('mapping-editor')?.scrollIntoView({ block: 'start' }) }, [ready])
  const del = useMutation({
    mutationFn: () => api.del(`/uploads/${id}`),
    onSuccess: () => { toast('File removed'); qc.invalidateQueries({ queryKey: ['uploads'] }); qc.invalidateQueries({ queryKey: ['borrowers'] }); onClose() },
  })
  if (!data || !m) return <section className="panel"><div className="pb"><Spinner /></div></section>
  const setCol = (i: number, patch: Partial<Mapping['columns'][number]>) => setM({ ...m, columns: m.columns.map((c, j) => j === i ? { ...c, ...patch } : c) })
  const setDef = (k: keyof Mapping['defaults'], v: string) => setM({ ...m, defaults: { ...m.defaults, [k]: v } })
  const mapped = new Set(m.columns.map(c => m.format === 'dictionary' ? c.role : c.field).filter(Boolean))
  const needBorrower = !mapped.has(m.format === 'dictionary' ? 'borrower' : 'Borrower_Name')
  const needSource = !mapped.has(m.format === 'dictionary' ? 'source' : 'External_Source')
  const blocked = (needBorrower && !m.defaults.borrower.trim()) || (needSource && !m.defaults.source.trim())

  return (
    <section className="panel" id="mapping-editor" aria-label={`Mapping for ${data.filename}`}>
      <div className="ph">
        <div><h2>Review mapping · {data.filename}</h2>
          <p className="hint">{m.format === 'dictionary' ? 'Data-dictionary layout: one row per data element.' : 'Record layout: one row per source record. Map each column to a Data360 field, or leave it unmapped to keep it as-is.'}</p></div>
        <button className="linkbtn" onClick={onClose}>Close</button>
      </div>
      <div className="pb stack">
        {m.missing?.length > 0 && data.status !== 'ingested' && <div className="callout warn">{m.missing.map(x => MISSING[x] || x).join(' ')}</div>}
        {m.uncertain && m.uncertain.length > 0 && <div className="callout">Check these guesses: {m.uncertain.join(', ')}.</div>}
        <div className="row" style={{ alignItems: 'end' }}>
          <label className="f" style={{ minWidth: 220 }}><span className="lbl">Sheet</span>
            <select value={m.sheet} onChange={e => sheet.mutate(e.target.value)}>
              {(data.mapping.sheets || [{ name: m.sheet, rows: m.rows }]).map(s => <option key={s.name} value={s.name}>{s.name} ({s.rows} rows)</option>)}
            </select></label>
          {needBorrower && <label className="f grow"><span className="lbl">Borrower for every row</span>
            <input type="text" list="d360-borrowers" value={m.defaults.borrower} onChange={e => setDef('borrower', e.target.value)} placeholder="Type or pick a borrower" />
            <datalist id="d360-borrowers">{(borrowers.data || []).map(b => <option key={b.id} value={b.name} />)}</datalist></label>}
          {needSource && <label className="f grow"><span className="lbl">Source system or feed</span>
            <input type="text" value={m.defaults.source} onChange={e => setDef('source', e.target.value)} placeholder="e.g. Bloomberg" /></label>}
          <label className="f" style={{ minWidth: 170 }}><span className="lbl">Zone</span>
            <select value={m.defaults.zone} onChange={e => setDef('zone', e.target.value)}>
              {['Internal', 'External', 'Internal / External'].map(z => <option key={z}>{z}</option>)}
            </select></label>
        </div>
        <div className="tblwrap">
          <table>
            <thead><tr><th>Column in file</th><th>{m.format === 'dictionary' ? 'Role' : 'Data360 field'}</th><th>How</th><th>Sample values</th></tr></thead>
            <tbody>
              {m.columns.map((c, i) => (
                <tr key={i}>
                  <td><b>{c.header || <span className="hint">(blank)</span>}</b></td>
                  <td style={{ minWidth: 220 }}>
                    {m.format === 'dictionary' ? (
                      <select value={c.role || ''} onChange={e => setCol(i, { role: e.target.value || null })} aria-label={`Role for ${c.header}`}>
                        <option value="">Not used</option>{DICT_ROLES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                      </select>
                    ) : (
                      <select value={c.field || ''} onChange={e => setCol(i, { field: e.target.value || null, how: 'manual', confidence: 1 })} aria-label={`Field for ${c.header}`}>
                        <option value="">Keep as-is (unmapped)</option>
                        {(fields.data || []).map(f => <option key={f.key} value={f.key}>{f.label}{f.critical ? ' *' : ''}</option>)}
                      </select>
                    )}
                  </td>
                  <td className="hint">{m.format === 'dictionary' ? '' : c.how === 'exact' ? 'Exact name' : c.how === 'synonym' ? 'Known synonym' : c.how === 'fuzzy' ? `Close match (${Math.round((c.confidence || 0) * 100)}%)` : c.how === 'manual' ? 'Set by you' : '—'}</td>
                  <td className="mono hint">{(data.preview?.rows || []).slice(0, 3).map(r => r[i]).filter(Boolean).join(' · ').slice(0, 90)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ErrorNote error={go.error || sheet.error || del.error} />
      </div>
      <div className="pf">
        <button className="btn danger" onClick={() => { if (window.confirm('Remove this file and its data?')) del.mutate() }}>Remove file</button>
        <span className="grow" />
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn primary" disabled={blocked || go.isPending} onClick={() => go.mutate()}>{go.isPending ? 'Loading…' : data.status === 'ingested' ? 'Reload with this mapping' : 'Load data'}</button>
      </div>
    </section>
  )
}

const OUT: Record<ScanOutcome, [string, 'ok' | 'warn' | 'bad' | 'info' | 'idle', string]> = {
  loaded: ['Loaded', 'ok', 'Read and loaded, like an upload'],
  duplicate: ['Duplicate', 'idle', 'Same file already loaded; skipped'],
  not_recognised: ['Not recognised', 'warn', 'Not loan data, or the borrower could not be worked out; not loaded'],
  not_read_yet: ['For the AI Collector', 'info', 'Documents (PDF, Word, email, text) the AI Collector will read'],
  failed: ['Failed', 'bad', 'Could not be opened'],
}

function ScanPanel({ canEdit }: { canEdit: boolean }) {
  const qc = useQueryClient()
  const [show, setShow] = useState<ScanOutcome | 'all'>('all')
  const st = useQuery({ queryKey: ['scan'], queryFn: () => api.get<ScanStatus>('/scan') })
  const run = useMutation({
    mutationFn: () => api.post<ScanReport>('/scan'),
    onSuccess: r => {
      qc.setQueryData<ScanStatus>(['scan'], old => old ? { ...old, last: r } : old)
      qc.invalidateQueries({ queryKey: ['uploads'] }); qc.invalidateQueries({ queryKey: ['borrowers'] })
      toast(`Scan finished: ${r.counts.loaded} loaded, ${r.counts.duplicate} duplicates, ${r.counts.not_read_yet} documents for the AI Collector`)
    },
  })
  const S = st.data, R = S?.last
  const download = () => {
    if (!R) return
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([JSON.stringify(R, null, 1)], { type: 'application/json' }))
    a.download = 'data360-scan-report.json'; a.click(); URL.revokeObjectURL(a.href)
  }
  const files = R ? R.files.filter(f => show === 'all' || f.outcome === show) : []
  return (
    <section className="panel" aria-labelledby="scanh">
      <div className="ph"><h2 id="scanh">Scan a folder</h2>
        <span className="hint">{!S ? 'Checking…' : S.available ? <>Folder <code className="mono">{S.root}</code>{S.readonly ? ' · read-only' : ''}</> : 'No folder connected'}</span></div>
      <div className="pb stack">
        <p className="hint" style={{ margin: 0 }}>Data360 looks through the connected folder and its subfolders, loads the spreadsheets and CSVs it can read,
          skips copies it already has, and lists documents for the AI Collector. It only reads: nothing in the folder is changed.
          Hidden and system folders (AppData, .cache) and Office lock files are skipped.</p>
        {S && !S.available && <div className="callout">{S.note || 'The scan folder cannot be read.'} In <code>.env</code>, set <code>SCAN_HOST_DIR</code> to the folder,
          for example <code>C:/Data360-test</code>, then run <code>docker compose up -d</code>.</div>}
        <div className="row" style={{ gap: 10, alignItems: 'center' }}>
          {canEdit && <button type="button" className="btn primary" disabled={!S?.available || run.isPending} onClick={() => run.mutate()}>
            {run.isPending ? 'Scanning…' : R ? 'Scan again' : 'Scan folder'}</button>}
          {R && <button type="button" className="btn" onClick={download}>Download report (.json)</button>}
          {R && <span className="hint">Last scan {when(R.at)} by {R.by} · {R.found} files in {R.seconds}s{R.truncated ? ' · stopped at the file limit' : ''}</span>}
        </div>
        <ErrorNote error={run.error} />
        {R && <>
          <div className="dkpis" style={{ marginBottom: 0 }}>
            {(Object.keys(OUT) as ScanOutcome[]).map(k => (
              <button key={k} type="button" className="kpi" title={OUT[k][2]} aria-pressed={show === k} onClick={() => setShow(show === k ? 'all' : k)}
                style={{ textAlign: 'left', cursor: 'pointer', font: 'inherit', color: 'inherit', outline: show === k ? '2px solid var(--teal)' : undefined }}>
                <div className="v">{R.counts[k] ?? 0}</div><div className="k">{OUT[k][0]}</div></button>))}
          </div>
          <p className="hint" style={{ margin: 0 }}>Borrowers in the scanned files: {R.borrowers.join(' · ') || 'none'}.
            {' '}Skipped without reading: {Object.entries(R.skipped).map(([k, v]) => `${v} ${k}`).join(', ')}.</p>
          <div className="tblwrap" style={{ maxHeight: 420 }}>
            <table>
              <thead><tr><th>File</th><th>Type</th><th>Outcome</th><th>Detail</th></tr></thead>
              <tbody>{files.map(f => (
                <tr key={f.path}>
                  <td className="mono" style={{ wordBreak: 'break-all' }}>{f.path}</td>
                  <td>{f.kind}</td>
                  <td><Chip kind={OUT[f.outcome][1]}>{OUT[f.outcome][0]}</Chip></td>
                  <td className="hint">{f.outcome === 'loaded' ? `${(f.values ?? 0).toLocaleString()} values · ${(f.borrowers || []).length > 2 ? `${f.borrowers!.length} borrowers` : (f.borrowers || []).join(', ')}` : f.note || '—'}</td>
                </tr>))}</tbody>
            </table>
          </div>
        </>}
      </div>
    </section>
  )
}
