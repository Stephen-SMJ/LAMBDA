import { useThemeStore } from '../../store/themeStore'
import { useSettingsStore } from '../../store/settingsStore'
import { useI18n } from '../../i18n'
import { X, Sun, Moon, Languages } from 'lucide-react'

interface SettingsModalProps {
  isOpen: boolean
  onClose: () => void
}

export default function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
  const { isDark, toggleTheme } = useThemeStore()
  const { language, setLanguage } = useSettingsStore()
  const { t } = useI18n()

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white dark:bg-neutral-900 rounded-xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-200 dark:border-neutral-800">
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            {t('settings')}
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-neutral-500" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          <div className="rounded-2xl border border-neutral-200 bg-neutral-50 p-4 dark:border-neutral-800 dark:bg-neutral-800/50">
            <p className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">LAMBDA Local</p>
            <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
              Single-user local mode. No login or cloud account is required.
            </p>
          </div>

          {/* Language Section */}
          <div>
            <h3 className="text-sm font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-3">
              {t('language')}
            </h3>
            <div className="grid grid-cols-2 gap-2">
              {[
                { value: 'en' as const, label: t('english') },
                { value: 'zh' as const, label: t('chinese') },
              ].map((option) => {
                const isSelected = language === option.value
                return (
                  <button
                    key={option.value}
                    onClick={() => setLanguage(option.value)}
                    className={`flex items-center justify-center gap-2 rounded-xl border px-3 py-3 text-sm font-medium transition-all ${
                      isSelected
                        ? 'border-blue-500 bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-300'
                        : 'border-neutral-200 text-neutral-700 hover:bg-neutral-50 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-800'
                    }`}
                  >
                    <Languages className="h-4 w-4" />
                    {option.label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Theme Section */}
          <div>
            <h3 className="text-sm font-medium text-neutral-500 dark:text-neutral-400 uppercase tracking-wider mb-3">
              {t('theme')}
            </h3>
            <div className="space-y-2">
              <button
                onClick={() => isDark && toggleTheme()}
                className={`w-full flex items-center gap-3 p-3 rounded-lg border transition-all ${
                  !isDark
                    ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                    : 'border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-800'
                }`}
              >
                <div className={`p-2 rounded-lg ${
                  !isDark 
                    ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400' 
                    : 'bg-neutral-100 dark:bg-neutral-800 text-neutral-500'
                }`}>
                  <Sun className="w-5 h-5" />
                </div>
                <div className="flex-1 text-left">
                  <p className={`font-medium ${
                    !isDark 
                      ? 'text-blue-700 dark:text-blue-400' 
                      : 'text-neutral-700 dark:text-neutral-300'
                  }`}>
                    {t('light')}
                  </p>
                  <p className="text-sm text-neutral-500 dark:text-neutral-400">
                    {t('lightDescription')}
                  </p>
                </div>
                {!isDark && (
                  <div className="w-2 h-2 rounded-full bg-blue-500" />
                )}
              </button>

              <button
                onClick={() => !isDark && toggleTheme()}
                className={`w-full flex items-center gap-3 p-3 rounded-lg border transition-all ${
                  isDark
                    ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                    : 'border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-800'
                }`}
              >
                <div className={`p-2 rounded-lg ${
                  isDark 
                    ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400' 
                    : 'bg-neutral-100 dark:bg-neutral-800 text-neutral-500'
                }`}>
                  <Moon className="w-5 h-5" />
                </div>
                <div className="flex-1 text-left">
                  <p className={`font-medium ${
                    isDark 
                      ? 'text-blue-700 dark:text-blue-400' 
                      : 'text-neutral-700 dark:text-neutral-300'
                  }`}>
                    {t('dark')}
                  </p>
                  <p className="text-sm text-neutral-500 dark:text-neutral-400">
                    {t('darkDescription')}
                  </p>
                </div>
                {isDark && (
                  <div className="w-2 h-2 rounded-full bg-blue-500" />
                )}
              </button>
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}
