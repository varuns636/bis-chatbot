import { BrowserRouter, Route, Routes } from 'react-router'
import { BackendStatusProvider } from './hooks/backendStatus'
import Assistant from './pages/Assistant'
import Landing from './pages/Landing'
import NotFound from './pages/NotFound'

export default function App() {
  return (
    <BackendStatusProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/assistant" element={<Assistant />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </BackendStatusProvider>
  )
}
