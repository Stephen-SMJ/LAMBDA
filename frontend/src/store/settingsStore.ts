import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface SettingsState {
  language: 'en' | 'zh'
  // Settings modal visibility
  isSettingsOpen: boolean
  setLanguage: (language: 'en' | 'zh') => void
  openSettings: () => void
  closeSettings: () => void
  toggleSettings: () => void
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      language: 'en',
      // Settings modal state
      isSettingsOpen: false,
      setLanguage: (language) => set({ language }),
      openSettings: () => set({ isSettingsOpen: true }),
      closeSettings: () => set({ isSettingsOpen: false }),
      toggleSettings: () => set((state) => ({ isSettingsOpen: !state.isSettingsOpen })),
    }),
    {
      name: 'lambda-settings',
      partialize: (state) => ({ language: state.language }),
    }
  )
)
