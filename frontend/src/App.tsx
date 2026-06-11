import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { useEffect } from 'react'
import { useThemeStore } from './store/themeStore'

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
  const { setTheme, isDark } = useThemeStore()
  const routerBasename = import.meta.env.BASE_URL === '/' ? undefined : import.meta.env.BASE_URL.replace(/\/$/, '')
  
  useEffect(() => {
    // Initialize theme on mount
    setTheme(isDark)
  }, [])

  return (
    <QueryClientProvider client={queryClient}>
      <Router basename={routerBasename}>
        <Routes>
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
          <Route path="*" element={<ChatPage />} />
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
    </QueryClientProvider>
  )
}

export default App
