import { StrictMode, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes, useParams } from 'react-router-dom'
import './styles.css'
import { AuthProvider, useAuth } from './auth'
import Layout from './components/Layout'
import Login from './pages/Login'
import Home from './pages/Home'
import Console from './pages/Console'
import Upload from './pages/Upload'
import Phase1 from './pages/Phase1'
import PhasePage from './pages/PhaseView'
import FixPlan from './pages/FixPlan'
import Admin from './pages/Admin'

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } })

function OldBorrower() {
  const { id, step } = useParams()
  return <Navigate to={`/b/${id}/p1/${step || 'source'}`} replace />
}

function Guard({ children }: { children: ReactNode }) {
  const { user, ready } = useAuth()
  if (!ready) return null
  return user ? <>{children}</> : <Navigate to="/login" replace />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route element={<Guard><Layout /></Guard>}>
              <Route index element={<Home />} />
              <Route path="console" element={<Console />} />
              <Route path="upload" element={<Upload />} />
              <Route path="b/:id/p1/:step?" element={<Phase1 />} />
              <Route path="b/:id/p2/:step?" element={<PhasePage key="p2" phase={2} />} />
              <Route path="b/:id/p3/:step?" element={<PhasePage key="p3" phase={3} />} />
              <Route path="b/:id/fix" element={<FixPlan />} />
              <Route path="borrowers/:id/:step?" element={<OldBorrower />} />
              <Route path="admin" element={<Admin />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
)
