import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth'
import Assistant from './Assistant'
import { PoliciesFab } from './Shell'
import { Toaster } from './ui'

type Theme = 'auto' | 'light' | 'dark'

export default function Layout() {
  const { user, logout } = useAuth()
  const [theme, setTheme] = useState<Theme>(() => { try { return (localStorage.getItem('d360.theme') as Theme) || 'auto' } catch { return 'auto' } })
  useEffect(() => {
    const el = document.documentElement
    theme === 'auto' ? el.removeAttribute('data-theme') : el.setAttribute('data-theme', theme)
    try { localStorage.setItem('d360.theme', theme) } catch { /* ignore */ }
  }, [theme])
  const next: Record<Theme, Theme> = { auto: 'light', light: 'dark', dark: 'auto' }
  return (
    <>
      <header className="sitenav" role="navigation" aria-label="Main">
        <NavLink to="/" end className="sn-logo">
          <img src="/logo-mark.png" alt="" width={76} height={38} />
          <span className="sn-text"><b>Data360</b><span>Trusted data for credit decisions</span></span>
        </NavLink>
        <nav className="main">
          <NavLink to="/" end>About</NavLink>
          <NavLink to="/console">Console</NavLink>
          <NavLink to="/upload">Upload files</NavLink>
          {user?.role === 'admin' && <NavLink to="/admin">Users &amp; audit</NavLink>}
        </nav>
        <span className="who">
          <button type="button" className="sn-btn" onClick={() => setTheme(next[theme])} aria-label="Change theme">
            Theme: {theme === 'auto' ? 'System' : theme === 'light' ? 'Light' : 'Dark'}</button>
          <span className="sn-user">{user?.email} · {user?.role}</span>
          <button type="button" className="sn-btn" onClick={logout}>Sign out</button>
        </span>
      </header>
      <div className="wrap">
        <main><Outlet /></main>
      </div>
      <PoliciesFab />
      <Assistant />
      <Toaster />
    </>
  )
}
