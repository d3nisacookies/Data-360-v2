import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Navigate } from 'react-router-dom'
import { api, type Role, type User } from '../api'
import { useAuth } from '../auth'
import { Chip, ErrorNote, Spinner, Table, toast, when } from '../components/ui'

interface Ev { id: number; at: string; user: string; action: string; target: string; details: Record<string, unknown> }

export default function Admin() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const users = useQuery({ queryKey: ['users'], queryFn: () => api.get<User[]>('/users'), enabled: user?.role === 'admin' })
  const audit = useQuery({ queryKey: ['audit'], queryFn: () => api.get<Ev[]>('/audit?limit=300'), enabled: user?.role === 'admin' })
  const [f, setF] = useState({ email: '', name: '', password: '', role: 'analyst' as Role })
  const add = useMutation({
    mutationFn: () => api.post<User>('/users', f),
    onSuccess: u => { toast(`Added ${u.email}`); setF({ email: '', name: '', password: '', role: 'analyst' }); qc.invalidateQueries({ queryKey: ['users'] }) },
  })
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<User> }) => api.patch<User>(`/users/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
  if (user?.role !== 'admin') return <Navigate to="/" replace />
  const submit = (e: FormEvent) => { e.preventDefault(); add.mutate() }
  return (
    <div className="stack">
      <h1>Users &amp; audit</h1>
      <section className="panel">
        <div className="ph"><h2>Users</h2><span className="hint">Admin: everything · Analyst: upload and run steps · Viewer: read only</span></div>
        <div className="pb stack">
          {users.isLoading ? <Spinner /> : <Table head={['Email', 'Name', 'Role', 'Status', '']} rows={(users.data || []).map(u => [
            u.email, u.name || '—',
            <select value={u.role} aria-label={`Role for ${u.email}`} disabled={u.id === user.id} onChange={e => patch.mutate({ id: u.id, body: { role: e.target.value as Role } })}>
              {['admin', 'analyst', 'viewer'].map(r => <option key={r}>{r}</option>)}</select>,
            u.active ? <Chip kind="ok">Active</Chip> : <Chip kind="idle">Deactivated</Chip>,
            u.id !== user.id && <button className="btn small" onClick={() => patch.mutate({ id: u.id, body: { active: !u.active } })}>{u.active ? 'Deactivate' : 'Reactivate'}</button>,
          ])} />}
          <form className="row" style={{ alignItems: 'end' }} onSubmit={submit}>
            <label className="f grow"><span className="lbl">Email</span><input type="email" required value={f.email} onChange={e => setF({ ...f, email: e.target.value })} /></label>
            <label className="f grow"><span className="lbl">Name</span><input type="text" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></label>
            <label className="f grow"><span className="lbl">Temporary password</span><input type="password" minLength={8} required value={f.password} onChange={e => setF({ ...f, password: e.target.value })} /></label>
            <label className="f"><span className="lbl">Role</span><select value={f.role} onChange={e => setF({ ...f, role: e.target.value as Role })}>{['analyst', 'viewer', 'admin'].map(r => <option key={r}>{r}</option>)}</select></label>
            <button className="btn primary" type="submit" disabled={add.isPending}>Add user</button>
          </form>
          <ErrorNote error={add.error || patch.error} />
        </div>
      </section>
      <section className="panel">
        <div className="ph"><h2>Audit log</h2><span className="hint">Every sign-in, upload, run, export and user change</span></div>
        <div className="pb">{audit.isLoading ? <Spinner /> : <Table head={['When', 'User', 'Action', 'Target', 'Details']} mono={[4]}
          rows={(audit.data || []).map(e => [when(e.at), e.user, e.action, e.target,
            Object.entries(e.details).filter(([, v]) => v !== null && v !== undefined).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : typeof v === 'object' ? JSON.stringify(v) : v}`).join(' · ')])} />}</div>
      </section>
    </div>
  )
}
