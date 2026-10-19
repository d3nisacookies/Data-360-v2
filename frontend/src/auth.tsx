import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, getToken, setToken, type User } from './api'

interface AuthCtx { user: User | null; ready: boolean; login: (e: string, p: string) => Promise<void>; logout: () => void; canEdit: boolean }
const Ctx = createContext<AuthCtx>(null as unknown as AuthCtx)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)
  useEffect(() => {
    if (!getToken()) { setReady(true); return }
    api.get<User>('/auth/me').then(setUser).catch(() => setToken(null)).finally(() => setReady(true))
  }, [])
  const login = async (email: string, password: string) => {
    const r = await api.login(email, password)
    setToken(r.access_token)
    setUser(r.user)
  }
  const logout = () => { setToken(null); setUser(null) }
  return <Ctx.Provider value={{ user, ready, login, logout, canEdit: !!user && user.role !== 'viewer' }}>{children}</Ctx.Provider>
}

export const useAuth = () => useContext(Ctx)
