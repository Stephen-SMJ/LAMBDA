import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { Mail, Lock, Eye, EyeOff, Loader2, KeyRound } from 'lucide-react'
import { motion } from 'framer-motion'
import TurnstileWidget from '../components/auth/TurnstileWidget'
import { useI18n } from '../i18n'
import { api } from '../services/api'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [resetCode, setResetCode] = useState('')
  const [resetPassword, setResetPassword] = useState('')
  const [confirmResetPassword, setConfirmResetPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [isResetMode, setIsResetMode] = useState(false)
  const [resetMessage, setResetMessage] = useState('')
  const [resetError, setResetError] = useState('')
  const [isSendingResetCode, setIsSendingResetCode] = useState(false)
  const [isResettingPassword, setIsResettingPassword] = useState(false)
  const [turnstileToken, setTurnstileToken] = useState('')
  const [turnstileKey, setTurnstileKey] = useState(0)
  const [turnstileEnabled, setTurnstileEnabled] = useState(false)
  const [turnstileSiteKey, setTurnstileSiteKey] = useState('')
  const { login, isLoading, error, clearError } = useAuthStore()
  const { t } = useI18n()
  const navigate = useNavigate()
  const handleTurnstileVerify = useCallback((token: string) => setTurnstileToken(token), [])
  const handleTurnstileExpire = useCallback(() => setTurnstileToken(''), [])
  const isStrongPassword = (value: string) =>
    value.length >= 8 && /[A-Za-z]/.test(value) && /\d/.test(value)

  const resetTurnstile = () => {
    setTurnstileToken('')
    setTurnstileKey((key) => key + 1)
  }

  useEffect(() => {
    let cancelled = false
    fetch('/api/v1/public/config')
      .then((response) => response.ok ? response.json() : null)
      .then((config) => {
        if (cancelled || !config) return
        setTurnstileEnabled(Boolean(config.turnstile_enabled))
        setTurnstileSiteKey(config.turnstile_site_key || '')
      })
      .catch(() => {
        if (!cancelled) {
          setTurnstileEnabled(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    clearError()
    if (turnstileEnabled && !turnstileToken) {
      return
    }
    try {
      await login(email, password, turnstileEnabled ? turnstileToken : undefined)
      navigate('/')
    } catch {
      resetTurnstile()
      // Error is handled in store
    }
  }

  const handleSendResetCode = async () => {
    clearError()
    setResetError('')
    setResetMessage('')
    if (!email.trim()) {
      setResetError(t('emailBeforeCode'))
      return
    }
    if (turnstileEnabled && !turnstileToken) {
      setResetError(t('humanBeforeCode'))
      return
    }
    setIsSendingResetCode(true)
    try {
      const response = await api.post('/auth/send-password-reset-code', {
        email,
        turnstile_token: turnstileEnabled ? turnstileToken : undefined,
      })
      if (turnstileEnabled) resetTurnstile()
      setResetMessage(t('resetCodeSent', { minutes: response.data.expires_in_minutes }))
    } catch (sendError: any) {
      if (turnstileEnabled) resetTurnstile()
      setResetError(sendError.response?.data?.detail || t('verificationFailed'))
    } finally {
      setIsSendingResetCode(false)
    }
  }

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    clearError()
    setResetError('')
    setResetMessage('')
    if (!resetCode.trim()) {
      setResetError(t('verificationRequired'))
      return
    }
    if (resetPassword !== confirmResetPassword) {
      setResetError(t('passwordMismatch'))
      return
    }
    if (!isStrongPassword(resetPassword)) {
      setResetError(t('passwordWeak'))
      return
    }
    if (turnstileEnabled && !turnstileToken) {
      setResetError(t('humanRequired'))
      return
    }
    setIsResettingPassword(true)
    try {
      await api.post('/auth/reset-password', {
        email,
        verification_code: resetCode,
        new_password: resetPassword,
        turnstile_token: turnstileEnabled ? turnstileToken : undefined,
      })
      if (turnstileEnabled) resetTurnstile()
      setPassword('')
      setResetCode('')
      setResetPassword('')
      setConfirmResetPassword('')
      setIsResetMode(false)
      setResetMessage(t('passwordResetSuccess'))
    } catch (resetErr: any) {
      if (turnstileEnabled) resetTurnstile()
      setResetError(resetErr.response?.data?.detail || t('passwordResetFailed'))
    } finally {
      setIsResettingPassword(false)
    }
  }

  return (
    <div className="min-h-screen overflow-y-auto bg-[radial-gradient(circle_at_top_left,_#f5f5f4,_transparent_34%),radial-gradient(circle_at_bottom_right,_#e5e7eb,_transparent_30%),#ffffff] flex items-center justify-center px-4 py-10 dark:bg-neutral-950">
      {/* Background decoration - subtle */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute left-1/2 top-16 h-72 w-72 -translate-x-1/2 rounded-full bg-neutral-100 blur-3xl dark:bg-neutral-800/50" />
        <div className="absolute bottom-16 right-16 h-64 w-64 rounded-full bg-blue-50 blur-3xl dark:bg-blue-950/20" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-md relative z-10"
      >
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-20 h-20 mb-4">
            <img 
              src="/LAMBDA_logo.gif" 
              alt="LAMBDA" 
              className="w-20 h-20 object-contain rounded-xl"
            />
          </div>
          <h1 className="text-4xl font-black tracking-tight text-neutral-900 dark:text-white mb-2">{t('welcomeBack')}</h1>
          <p className="text-neutral-500 dark:text-neutral-400">{t('signInContinue')}</p>
        </div>

        {/* Login Form */}
        <div className="bg-white/90 dark:bg-neutral-900/90 border border-neutral-200/80 dark:border-neutral-700 rounded-[32px] p-8 shadow-2xl shadow-neutral-200/70 dark:shadow-black/30 backdrop-blur">
          <form onSubmit={isResetMode ? handleResetPassword : handleSubmit} className="space-y-5">
            {/* Email */}
            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                {t('email')}
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-400" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full bg-white dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-600 rounded-2xl py-3 pl-11 pr-4 text-neutral-900 dark:text-white placeholder-neutral-400 focus:outline-none focus:ring-4 focus:ring-neutral-200 focus:border-neutral-400 transition-all"
                  required
                />
              </div>
            </div>

            {!isResetMode ? (
              <div>
                <div className="mb-2 flex items-center justify-between gap-3">
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
                    {t('password')}
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      clearError()
                      setResetError('')
                      setResetMessage('')
                      setIsResetMode(true)
                    }}
                    className="text-xs font-medium text-blue-600 hover:text-blue-700"
                  >
                    {t('forgotPassword')}
                  </button>
                </div>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-400" />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full bg-white dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-600 rounded-2xl py-3 pl-11 pr-11 text-neutral-900 dark:text-white placeholder-neutral-400 focus:outline-none focus:ring-4 focus:ring-neutral-200 focus:border-neutral-400 transition-all"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
                  >
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div>
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
                      {t('verificationCode')}
                    </label>
                    <button
                      type="button"
                      onClick={handleSendResetCode}
                      disabled={isSendingResetCode}
                      className="text-xs font-medium text-blue-600 hover:text-blue-700 disabled:text-neutral-400"
                    >
                      {isSendingResetCode ? t('sending') : t('sendCode')}
                    </button>
                  </div>
                  <div className="relative">
                    <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-400" />
                    <input
                      type="text"
                      inputMode="numeric"
                      value={resetCode}
                      onChange={(e) => setResetCode(e.target.value)}
                      placeholder={t('codePlaceholder')}
                      className="w-full bg-white dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-600 rounded-2xl py-3 pl-11 pr-4 text-neutral-900 dark:text-white placeholder-neutral-400 focus:outline-none focus:ring-4 focus:ring-neutral-200 focus:border-neutral-400 transition-all"
                      required
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                    {t('newPassword')}
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-400" />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={resetPassword}
                      onChange={(e) => setResetPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full bg-white dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-600 rounded-2xl py-3 pl-11 pr-11 text-neutral-900 dark:text-white placeholder-neutral-400 focus:outline-none focus:ring-4 focus:ring-neutral-200 focus:border-neutral-400 transition-all"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
                    >
                      {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                  <p className="mt-1 text-xs text-neutral-500">{t('passwordRule')}</p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                    {t('confirmPassword')}
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-400" />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={confirmResetPassword}
                      onChange={(e) => setConfirmResetPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full bg-white dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-600 rounded-2xl py-3 pl-11 pr-4 text-neutral-900 dark:text-white placeholder-neutral-400 focus:outline-none focus:ring-4 focus:ring-neutral-200 focus:border-neutral-400 transition-all"
                      required
                    />
                  </div>
                </div>
              </>
            )}

            {/* Error Message */}
            {(error || resetError || resetMessage) && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`p-3 rounded-lg text-sm ${
                  resetMessage && !error && !resetError
                    ? 'bg-green-500/10 border border-green-500/20 text-green-700 dark:text-green-400'
                    : 'bg-red-500/10 border border-red-500/20 text-red-600 dark:text-red-400'
                }`}
              >
                {error || resetError || resetMessage}
              </motion.div>
            )}

            {turnstileEnabled && turnstileSiteKey && (
              <TurnstileWidget
                key={turnstileKey}
                siteKey={turnstileSiteKey}
                onVerify={handleTurnstileVerify}
                onExpire={handleTurnstileExpire}
              />
            )}

            {/* Submit Button */}
            <button
              type="submit"
              disabled={isLoading || isResettingPassword || (turnstileEnabled && !turnstileToken)}
              className="w-full bg-neutral-950 dark:bg-white hover:bg-neutral-800 dark:hover:bg-neutral-200 text-white dark:text-neutral-950 font-semibold py-3.5 rounded-2xl transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 shadow-lg"
            >
              {isLoading || isResettingPassword ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  {isResetMode ? t('resettingPassword') : t('signingIn')}
                </>
              ) : (
                isResetMode ? t('resetPassword') : t('signIn')
              )}
            </button>
          </form>

          {isResetMode && (
            <button
              type="button"
              onClick={() => {
                setIsResetMode(false)
                setResetError('')
                setResetMessage('')
              }}
              className="mt-4 w-full text-center text-sm font-medium text-neutral-500 hover:text-neutral-900 dark:hover:text-white"
            >
              {t('backToSignIn')}
            </button>
          )}

          {/* Divider */}
          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-neutral-300 dark:border-neutral-600"></div>
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-neutral-50 dark:bg-neutral-800 text-neutral-500">{t('or')}</span>
            </div>
          </div>

          {/* Register Link */}
          <p className="text-center text-neutral-600 dark:text-neutral-400">
            {t('noAccount')}{' '}
            <Link to="/register" className="text-neutral-900 dark:text-white hover:underline font-medium transition-colors">
              {t('signUp')}
            </Link>
          </p>
        </div>

        {/* Footer */}
        <p className="text-center text-neutral-400 text-sm mt-8">
          © 2024 LAMBDA. All rights reserved.
        </p>
      </motion.div>
    </div>
  )
}
