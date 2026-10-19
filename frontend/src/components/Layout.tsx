import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth'
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
      <div className="banner">Data360 · prepared data supports analysis; approvers make credit decisions</div>
      <div className="wrap">
        <header className="top">
          <Link to="/" className="brand"><b>Data360</b><span>Credit memo data workflow</span></Link>
          <nav className="main" aria-label="Main">
            <NavLink to="/" end>Borrowers</NavLink>
            <NavLink to="/upload">Upload files</NavLink>
            {user?.role === 'admin' && <NavLink to="/admin">Users &amp; audit</NavLink>}
          </nav>
          <div className="who">
            <button type="button" className="btn small" onClick={() => setTheme(next[theme])} aria-label="Change theme">
              Theme: {theme === 'auto' ? 'System' : theme === 'light' ? 'Light' : 'Dark'}
            </button>
            <span>{user?.email} · {user?.role}</span>
            <button type="button" className="linkbtn" onClick={logout}>Sign out</button>
          </div>
        </header>
        <main><Outlet /></main>
      </div>
      <Toaster />
    </>
  )
}
