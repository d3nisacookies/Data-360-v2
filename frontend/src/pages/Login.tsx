import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth'
import { ErrorNote } from '../components/ui'

export default function Login() {
  const { user, login } = useAuth()
  const [email, setEmail] = useState('')
  const [pw, setPw] = useState('')
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  if (user) return <Navigate to="/" replace />
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true); setErr(null)
    try { await login(email, pw) } catch (x) { setErr(x) } finally { setBusy(false) }
  }
  return (
    <div className="login">
      <form className="panel" onSubmit={submit}>
        <div className="ph"><div><h1>Data360</h1><p className="hint">Prepare trusted data for credit memos</p></div></div>
        <div className="pb stack">
          <label className="f"><span className="lbl">Email</span>
            <input type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} required /></label>
          <label className="f"><span className="lbl">Password</span>
            <input type="password" autoComplete="current-password" value={pw} onChange={e => setPw(e.target.value)} required /></label>
          <ErrorNote error={err} />
        </div>
        <div className="pf"><button className="btn primary" type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button></div>
      </form>
    </div>
  )
}
