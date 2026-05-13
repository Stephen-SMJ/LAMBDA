import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { useEffect } from 'react'
import { useAuthStore } from './store/authStore'
import { useThemeStore } from './store/themeStore'
import AnnouncementModal from './components/AnnouncementModal'

import ChatPage from './pages/Chat'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

// Protected route component
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}

function App() {
  const { initializeAuth } = useAuthStore()
  const { setTheme, isDark } = useThemeStore()
  const routerBasename = import.meta.env.BASE_URL === '/' ? undefined : import.meta.env.BASE_URL.replace(/\/$/, '')
  
  useEffect(() => {
    initializeAuth()
    // Initialize theme on mount
    setTheme(isDark)
  }, [])

  return (
    <QueryClientProvider client={queryClient}>
      <Router basename={routerBasename}>
        <Routes>
          <Route path="/login" element={<Navigate to="/" replace />} />
          <Route path="/register" element={<Navigate to="/" replace />} />
          <Route 
            path="/" 
            element={
              <ProtectedRoute>
                <ChatPage />
              </ProtectedRoute>
            } 
          />
          <Route 
            path="/chat/:conversationId" 
            element={
              <ProtectedRoute>
                <ChatPage />
              </ProtectedRoute>
            } 
          />
          <Route path="/admin" element={<Navigate to="/" replace />} />
          <Route path="/admin/conversations/:conversationId" element={<Navigate to="/" replace />} />
          <Route path="/cases" element={<Navigate to="/" replace />} />
          <Route path="/c/:slug" element={<Navigate to="/" replace />} />
          <Route path="/case-study/*" element={<Navigate to="/" replace />} />
        </Routes>
      </Router>
      <Toaster 
        position="top-center"
        toastOptions={{
          duration: 3000,
          style: {
            background: '#1e293b',
            color: '#f8fafc',
            border: '1px solid #334155',
          },
        }}
      />
      <AnnouncementModal />
    </QueryClientProvider>
  )
}

export default App
