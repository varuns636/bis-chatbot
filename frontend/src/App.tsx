import { BrowserRouter, Route, Routes } from 'react-router'
import RequireSession from './components/RequireSession'
import { AuthProvider } from './hooks/auth'
import { BackendStatusProvider } from './hooks/backendStatus'
import Assistant from './pages/Assistant'
import Landing from './pages/Landing'
import Login from './pages/Login'
import NotFound from './pages/NotFound'

export default function App() {
  return (
    <AuthProvider>
      <BackendStatusProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route
              path="/assistant"
              element={
                <RequireSession>
                  <Assistant />
                </RequireSession>
              }
            />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </BackendStatusProvider>
    </AuthProvider>
  )
}
