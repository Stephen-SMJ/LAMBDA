import { useState, useRef, useCallback, useEffect } from 'react'
import type { ReactNode } from 'react'
import { Send, Paperclip, X, FileText, BookOpen, FileText as FileIcon, Square } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import toast from 'react-hot-toast'
import { exportNotebook, exportReport } from '../../services/export'
import { useI18n } from '../../i18n'

interface ChatInputProps {
  onSendMessage: (message: string, files?: File[], analysisMode?: string) => void
  onStop?: () => void
  isStreaming?: boolean
  disabled?: boolean
  placeholder?: string
  conversationId?: string
  variant?: 'default' | 'hero'
  className?: string
  heroControls?: ReactNode
}

const MAX_UPLOAD_SIZE_BYTES = 30 * 1024 * 1024
const BLOCKED_UPLOAD_EXTENSIONS = new Set([
  '.app', '.apk', '.bat', '.bin', '.bash', '.cmd', '.com', '.cpl', '.dll',
  '.dmg', '.elf', '.exe', '.gadget', '.hta', '.jar', '.js', '.jse', '.lnk',
  '.msi', '.msp', '.pif', '.ps1', '.py', '.rb', '.reg', '.run', '.scr',
  '.sh', '.so', '.sys', '.vb', '.vbe', '.vbs', '.ws', '.wsf', '.zsh',
])

const getFileExtension = (filename: string) => {
  const dotIndex = filename.lastIndexOf('.')
  return dotIndex >= 0 ? filename.slice(dotIndex).toLowerCase() : ''
}

export default function ChatInput({
  onSendMessage,
  onStop,
  isStreaming = false,
  disabled,
  placeholder,
  conversationId,
  variant = 'default',
  className = '',
  heroControls,
}: ChatInputProps) {
  const [message, setMessage] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const [showExportMenu, setShowExportMenu] = useState(false)
  const [exportingItem, setExportingItem] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const exportMenuRef = useRef<HTMLDivElement>(null)
  const exportButtonRef = useRef<HTMLButtonElement>(null)
  const { t } = useI18n()

  useEffect(() => {
    if (!showExportMenu) return

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node
      if (exportMenuRef.current?.contains(target) || exportButtonRef.current?.contains(target)) {
        return
      }
      setShowExportMenu(false)
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [showExportMenu])

  const adjustTextareaHeight = () => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
    }
  }

  const handleSubmit = () => {
    if (!message.trim() && files.length === 0) return
    if (disabled) return

    onSendMessage(message, files.length > 0 ? files : undefined)
    setMessage('')
    setFiles([])
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const addFiles = useCallback((incomingFiles: File[]) => {
    const validFiles: File[] = []

    incomingFiles.forEach((file) => {
      const ext = getFileExtension(file.name)
      if (file.size > MAX_UPLOAD_SIZE_BYTES) {
        toast.error(t('fileTooLarge', { name: file.name }))
        return
      }
      if (BLOCKED_UPLOAD_EXTENSIONS.has(ext)) {
        toast.error(t('fileNotAllowed', { name: file.name }))
        return
      }
      validFiles.push(file)
    })

    if (validFiles.length > 0) {
      setFiles((prev) => [...prev, ...validFiles])
    }
  }, [t])

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files || [])
    addFiles(selectedFiles)
    // Reset input value so the same file can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleRemoveFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
    // Reset input value so the same file can be selected again after removal
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const droppedFiles = Array.from(e.dataTransfer.files)
    addFiles(droppedFiles)
  }, [addFiles])

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleExportNotebook = async () => {
    if (!conversationId) return
    setExportingItem('notebook')
    try {
      await exportNotebook(conversationId)
      toast.success(t('notebookExported'))
    } catch (error) {
      toast.error(t('notebookExportFailed'))
      console.error('Export failed:', error)
    }
    setExportingItem(null)
    setShowExportMenu(false)
  }

  const handleExportReport = async (format: 'md' | 'pdf' | 'zip' | 'slides' = 'zip') => {
    if (!conversationId) return
    setExportingItem(format)
    try {
      await exportReport(conversationId, format)
      toast.success(t('reportExported', { format: format.toUpperCase() }))
    } catch (error) {
      toast.error(t('reportExportFailed'))
      console.error('Export failed:', error)
    }
    setExportingItem(null)
    setShowExportMenu(false)
  }

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  return (
    <div
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      className={`relative transition-all ${isDragging ? 'scale-[1.02]' : ''} ${className}`}
    >
      {/* Drag Overlay */}
      <AnimatePresence>
        {isDragging && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 -m-4 bg-neutral-100 dark:bg-neutral-800/50 border-2 border-dashed border-neutral-300 dark:border-neutral-600 rounded-2xl flex items-center justify-center z-10"
          >
            <p className="text-neutral-500 font-medium">{t('dropFiles')}</p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* File Preview */}
      <AnimatePresence>
        {files.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="flex flex-wrap gap-2 mb-3"
          >
            {files.map((file, index) => (
              <motion.div
                key={`${file.name}-${file.size}-${file.lastModified}`}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                className="flex items-center gap-2 px-3 py-1.5 bg-neutral-100 dark:bg-neutral-800 rounded-lg text-sm"
              >
                <FileText className="w-4 h-4 text-neutral-500" />
                <span className="text-neutral-700 dark:text-neutral-300 truncate max-w-[150px]">{file.name}</span>
                <span className="text-neutral-400 text-xs">{formatFileSize(file.size)}</span>
                <button
                  onClick={() => handleRemoveFile(index)}
                  className="ml-1 p-0.5 hover:bg-neutral-200 dark:hover:bg-neutral-700 rounded transition-colors"
                >
                  <X className="w-3 h-3 text-neutral-400" />
                </button>
              </motion.div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Export Menu */}
      <AnimatePresence>
        {showExportMenu && conversationId && (
          <motion.div
            ref={exportMenuRef}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="absolute bottom-full right-0 mb-2 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-xl shadow-lg p-2 z-20 min-w-[220px]"
          >
            <div className="px-3 py-1 text-xs font-medium text-neutral-400 uppercase tracking-wider">
              {t('exports')}
            </div>
            <button
              onClick={handleExportNotebook}
              disabled={!!exportingItem}
              className="flex items-center gap-2 w-full px-3 py-2 text-sm text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg transition-colors text-left mt-1"
            >
              <BookOpen className="w-4 h-4" />
              {exportingItem === 'notebook' ? t('exporting') : 'Jupyter Notebook (.ipynb)'}
            </button>
            <div className="border-t border-neutral-200 dark:border-neutral-700 my-1" />
            <div className="px-3 py-1 text-xs font-medium text-neutral-400 uppercase tracking-wider">
              {t('reports')}
            </div>
            <button
              onClick={() => handleExportReport('zip')}
              disabled={!!exportingItem}
              className="flex items-center gap-2 w-full px-3 py-2 text-sm text-neutral-700 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg transition-colors text-left mt-1"
            >
              <FileIcon className="w-4 h-4" />
              {exportingItem === 'zip' ? t('generating') : 'Report Bundle (.zip)'}
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Input Container */}
      <div className={`relative bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 shadow-sm ${
        variant === 'hero'
          ? 'rounded-[28px] bg-white/95 shadow-2xl shadow-neutral-200/80 backdrop-blur dark:bg-neutral-800/95 dark:shadow-black/20'
          : 'rounded-2xl'
      }`}>
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => {
            setMessage(e.target.value)
            adjustTextareaHeight()
          }}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || t('messagePlaceholder')}
          disabled={disabled}
          rows={variant === 'hero' ? 2 : 1}
          className={`w-full bg-transparent border-0 text-neutral-900 dark:text-neutral-100 placeholder-neutral-400 focus:outline-none focus:ring-0 resize-none max-h-[220px] ${
            variant === 'hero'
              ? 'rounded-[28px] px-4 py-4 pb-16 pr-28 text-base min-h-[128px] sm:px-6 sm:py-6 sm:pb-16 sm:pr-36 sm:text-lg sm:min-h-[150px]'
              : 'rounded-2xl px-4 py-3.5 pr-32 min-h-[52px]'
          }`}
        />

        {variant === 'hero' && heroControls && (
          <div className="absolute left-3 right-14 bottom-2 flex min-w-0 items-center gap-2 sm:left-4 sm:right-14">
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled}
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-neutral-500 transition-colors hover:bg-neutral-100 hover:text-neutral-800 disabled:opacity-50 dark:text-neutral-400 dark:hover:bg-neutral-700 dark:hover:text-neutral-100"
              title={t('attachFiles')}
              type="button"
            >
              <Paperclip className="w-5 h-5" />
            </button>
            {heroControls}
          </div>
        )}

        {/* Actions */}
        <div className="absolute right-2 bottom-2 flex items-center gap-1">
          {/* Export Button (only when conversation exists) */}
          {conversationId && (
            <button
              ref={exportButtonRef}
              onClick={() => setShowExportMenu(!showExportMenu)}
              disabled={disabled}
              className="p-2 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg transition-colors disabled:opacity-50"
              title={t('export')}
            >
              <BookOpen className="w-5 h-5" />
            </button>
          )}

          {/* File Upload */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            onChange={handleFileSelect}
            className="hidden"
          />
          {variant !== 'hero' && (
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled}
              className="p-2 text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-lg transition-colors disabled:opacity-50"
              title={t('attachFiles')}
              type="button"
            >
              <Paperclip className="w-5 h-5" />
            </button>
          )}

          {/* Send Button */}
          <button
            onClick={isStreaming ? onStop : handleSubmit}
            disabled={isStreaming ? false : disabled || (!message.trim() && files.length === 0)}
            className={`p-2 rounded-lg transition-all ${
              isStreaming
                ? 'bg-red-500 hover:bg-red-600 text-white'
                : 'bg-neutral-900 dark:bg-white hover:bg-neutral-700 dark:hover:bg-neutral-200 disabled:bg-neutral-200 dark:disabled:bg-neutral-700 disabled:opacity-50 text-white dark:text-neutral-900'
            }`}
            title={isStreaming ? t('stopExecution') : t('send')}
          >
            {isStreaming ? (
              <Square className="w-5 h-5 fill-current" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
