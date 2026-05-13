import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { api } from '../services/api'

interface User {
  id: number
  email: string
  full_name: string | null
  is_active: boolean
  is_admin: boolean
  created_at: string
}

interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
  
  // Actions
  login: (email: string, password: string, turnstileToken?: string) => Promise<void>
  register: (email: string, password: string, verificationCode: string, fullName?: string, inviteCode?: string, turnstileToken?: string) => Promise<void>
  logout: () => void
  initializeAuth: () => void
  clearError: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      isAuthenticated: true,
      isLoading: false,
      error: null,

      login: async (email: string, password: string, turnstileToken?: string) => {
        set({ isLoading: true, error: null })
        try {
          const formData = new FormData()
          formData.append('username', email)
          formData.append('password', password)
          if (turnstileToken) {
            formData.append('turnstile_token', turnstileToken)
          }
          
          const response = await api.post('/auth/login', formData, {
            headers: {
              'Content-Type': 'application/x-www-form-urlencoded',
            },
          })
          
          const { access_token, user } = response.data
          set({
            user,
            token: access_token,
            isAuthenticated: true,
            isLoading: false,
          })
        } catch (error: any) {
          set({
            error: error.response?.data?.detail || 'Login failed',
            isLoading: false,
          })
          throw error
        }
      },

      register: async (email: string, password: string, verificationCode: string, fullName?: string, inviteCode?: string, turnstileToken?: string) => {
        set({ isLoading: true, error: null })
        try {
          const response = await api.post('/auth/register', {
            email,
            password,
            verification_code: verificationCode,
            full_name: fullName,
            invite_code: inviteCode,
            turnstile_token: turnstileToken,
          })
          
          const { access_token, user } = response.data
          set({
            user,
            token: access_token,
            isAuthenticated: true,
            isLoading: false,
          })
        } catch (error: any) {
          set({
            error: error.response?.data?.detail || 'Registration failed',
            isLoading: false,
          })
          throw error
        }
      },

      logout: () => {
        set({
          user: null,
          token: null,
          isAuthenticated: false,
          error: null,
        })
      },

      initializeAuth: () => {
        set({
          isAuthenticated: true,
          user: {
            id: 1,
            email: 'local@lambda.local',
            full_name: 'Local User',
            is_active: true,
            is_admin: false,
            created_at: new Date().toISOString(),
          },
        })
        return
        const { token } = get()
        if (token) {
          set({ isAuthenticated: true })
          // Optionally fetch user data
          api.get('/users/me', {
            headers: { Authorization: `Bearer ${token}` }
          }).then(response => {
            set({ user: response.data })
          }).catch(() => {
            get().logout()
          })
        }
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: 'lambda-auth-storage',
      partialize: (state) => ({ 
        token: state.token,
        user: state.user,
        isAuthenticated: state.isAuthenticated 
      }),
    }
  )
)
