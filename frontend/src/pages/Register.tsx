import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { Mail, Lock, User, Eye, EyeOff, Loader2, KeyRound } from 'lucide-react'
import { motion } from 'framer-motion'
import { api } from '../services/api'
import TurnstileWidget from '../components/auth/TurnstileWidget'
import { useI18n } from '../i18n'

export default function RegisterPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [verificationCode, setVerificationCode] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [passwordError, setPasswordError] = useState('')
  const [verificationMessage, setVerificationMessage] = useState('')
  const [isSendingCode, setIsSendingCode] = useState(false)
  const [turnstileToken, setTurnstileToken] = useState('')
  const [turnstileKey, setTurnstileKey] = useState(0)
  const [turnstileEnabled, setTurnstileEnabled] = useState(false)
  const [turnstileSiteKey, setTurnstileSiteKey] = useState('')
  const { register, isLoading, error, clearError } = useAuthStore()
  const { t } = useI18n()
  const navigate = useNavigate()
  const handleTurnstileVerify = useCallback((token: string) => setTurnstileToken(token), [])
  const handleTurnstileExpire = useCallback(() => setTurnstileToken(''), [])

  const isStrongPassword = (value: string) =>
    value.length >= 8 && /[A-Za-z]/.test(value) && /\d/.test(value)

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

  const resetTurnstile = () => {
    setTurnstileToken('')
    setTurnstileKey((key) => key + 1)
  }

  const handleSendVerificationCode = async () => {
    clearError()
    setPasswordError('')
    setVerificationMessage('')

    if (!email.trim()) {
      setPasswordError(t('emailBeforeCode'))
      return
    }

    if (!inviteCode.trim()) {
      setPasswordError(t('inviteBeforeCode'))
      return
    }

    if (turnstileEnabled && !turnstileToken) {
      setPasswordError(t('humanBeforeCode'))
      return
    }

    setIsSendingCode(true)
    try {
      const response = await api.post('/auth/send-verification-code', {
        email,
        invite_code: inviteCode,
        turnstile_token: turnstileEnabled ? turnstileToken : undefined,
      })
      if (turnstileEnabled) resetTurnstile()
      setVerificationMessage(
        t('verificationSent', { minutes: response.data.expires_in_minutes })
      )
    } catch (sendError: any) {
      if (turnstileEnabled) resetTurnstile()
      setPasswordError(sendError.response?.data?.detail || t('verificationFailed'))
    } finally {
      setIsSendingCode(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    clearError()
    setPasswordError('')

    if (password !== confirmPassword) {
      setPasswordError(t('passwordMismatch'))
      return
    }

    if (!isStrongPassword(password)) {
      setPasswordError(t('passwordWeak'))
      return
    }

    if (!inviteCode.trim()) {
      setPasswordError(t('invitationRequired'))
      return
    }

    if (!verificationCode.trim()) {
      setPasswordError(t('verificationRequired'))
      return
    }

    if (turnstileEnabled && !turnstileToken) {
      setPasswordError(t('humanRequired'))
      return
    }

    try {
      await register(
        email,
        password,
        verificationCode,
        fullName || undefined,
        inviteCode,
        turnstileEnabled ? turnstileToken : undefined
      )
      navigate('/')
    } catch {
      if (turnstileEnabled) resetTurnstile()
      // Error is handled in store
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
          <h1 className="text-4xl font-black tracking-tight text-neutral-900 dark:text-white mb-2">{t('createAccount')}</h1>
          <p className="text-neutral-500 dark:text-neutral-400">{t('createAccountDescription')}</p>
        </div>

        {/* Register Form */}
        <div className="bg-white/90 dark:bg-neutral-900/90 border border-neutral-200/80 dark:border-neutral-700 rounded-[32px] p-8 shadow-2xl shadow-neutral-200/70 dark:shadow-black/30 backdrop-blur">
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Full Name */}
            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                {t('fullNameOptional')}
              </label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-400" />
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="John Doe"
                  className="w-full bg-white dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-600 rounded-2xl py-3 pl-11 pr-4 text-neutral-900 dark:text-white placeholder-neutral-400 focus:outline-none focus:ring-4 focus:ring-neutral-200 focus:border-neutral-400 transition-all"
                />
              </div>
            </div>

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

            {/* Password */}
            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                {t('password')}
              </label>
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
              <p className="mt-1 text-xs text-neutral-500">{t('passwordRule')}</p>
            </div>

            {/* Confirm Password */}
            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                {t('confirmPassword')}
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-400" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full bg-white dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-600 rounded-2xl py-3 pl-11 pr-4 text-neutral-900 dark:text-white placeholder-neutral-400 focus:outline-none focus:ring-4 focus:ring-neutral-200 focus:border-neutral-400 transition-all"
                  required
                />
              </div>
            </div>

            {/* Invitation Code */}
            <div>
              <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300 mb-2">
                {t('invitationCode')} <span className="text-red-500">*</span>
              </label>
              <div className="relative">
                <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-400" />
                <input
                  type="text"
                  value={inviteCode}
                  onChange={(e) => setInviteCode(e.target.value)}
                  placeholder={t('invitationPlaceholder')}
                  className="w-full bg-white dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-600 rounded-2xl py-3 pl-11 pr-4 text-neutral-900 dark:text-white placeholder-neutral-400 focus:outline-none focus:ring-4 focus:ring-neutral-200 focus:border-neutral-400 transition-all"
                  required
                />
              </div>
              <p className="text-xs text-neutral-500 mt-1">
                {t('invitationRequiredHint')}
              </p>
            </div>

            {/* Verification Code */}
            <div>
              <div className="flex items-center justify-between mb-2 gap-3">
                <label className="block text-sm font-medium text-neutral-700 dark:text-neutral-300">
                  {t('verificationCode')} <span className="text-red-500">*</span>
                </label>
                <button
                  type="button"
                  onClick={handleSendVerificationCode}
                  disabled={isSendingCode}
                  className="text-xs font-medium text-blue-600 hover:text-blue-700 disabled:text-neutral-400 transition-colors"
                >
                  {isSendingCode ? t('sending') : t('sendCode')}
                </button>
              </div>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-400" />
                <input
                  type="text"
                  inputMode="numeric"
                  value={verificationCode}
                  onChange={(e) => setVerificationCode(e.target.value)}
                  placeholder={t('codePlaceholder')}
                  className="w-full bg-white dark:bg-neutral-900 border border-neutral-300 dark:border-neutral-600 rounded-2xl py-3 pl-11 pr-4 text-neutral-900 dark:text-white placeholder-neutral-400 focus:outline-none focus:ring-4 focus:ring-neutral-200 focus:border-neutral-400 transition-all"
                  required
                />
              </div>
              {verificationMessage && (
                <p className="text-xs text-green-600 mt-1">{verificationMessage}</p>
              )}
            </div>

            {/* Error Messages */}
            {(error || passwordError) && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-600 dark:text-red-400 text-sm"
              >
                {error || passwordError}
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
              disabled={isLoading || (turnstileEnabled && !turnstileToken)}
              className="w-full bg-neutral-950 dark:bg-white hover:bg-neutral-800 dark:hover:bg-neutral-200 text-white dark:text-neutral-950 font-semibold py-3.5 rounded-2xl transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 shadow-lg"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  {t('creatingAccount')}
                </>
              ) : (
                t('createAccount')
              )}
            </button>
          </form>

          {/* Divider */}
          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-neutral-200 dark:border-neutral-600"></div>
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-neutral-50 dark:bg-neutral-800 text-neutral-400">{t('or')}</span>
            </div>
          </div>

          {/* Login Link */}
          <p className="text-center text-neutral-500 dark:text-neutral-400">
            {t('haveAccount')}{' '}
            <Link to="/login" className="text-neutral-900 dark:text-white font-medium hover:underline transition-colors">
              {t('signIn')}
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
