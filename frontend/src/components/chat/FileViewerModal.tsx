import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, FileText, Image, File, Download, Eye, ArrowLeft, ExternalLink } from 'lucide-react'
import { api } from '../../services/api'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import { useI18n } from '../../i18n'

interface FileInfo {
  name: string
  url: string
  path?: string
  type: string
}

interface FileViewerModalProps {
  isOpen: boolean
  onClose: () => void
  files: FileInfo[]
}

const API_BASE_URL = import.meta.env.VITE_API_URL || ''

const withApiBase = (url: string | undefined): string | undefined => {
  if (!url) return url
  if (url.startsWith('/api/')) return `${API_BASE_URL}${url}`
  try {
    const parsed = new URL(url, window.location.origin)
    if (parsed.origin === window.location.origin && parsed.pathname.startsWith('/api/')) {
      return `${API_BASE_URL}${parsed.pathname}${parsed.search}${parsed.hash}`
    }
  } catch {
    // Keep non-URL strings unchanged.
  }
  return url
}

const getContentReference = (file: FileInfo): string | undefined => {
  // Local file APIs return a preview URL plus the original path. When asking
  // /files/content for text, pass the original path to avoid proxying a proxy.
  if (file.url?.startsWith('/api/') && file.path) return file.path
  return file.url
}

// Helper to ensure HTTPS URL
const toHttps = (url: string | undefined): string | undefined => {
  if (!url) return url
  return url.startsWith('http://') ? url.replace('http://', 'https://') : url
}

const toProxyUrl = (url: string | undefined): string | undefined => {
  const httpsUrl = toHttps(withApiBase(url))
  if (!httpsUrl) return httpsUrl
  if (httpsUrl.includes('/api/v1/files/content')) return httpsUrl
  if (!httpsUrl.startsWith('http')) return httpsUrl
  return `${API_BASE_URL}/api/v1/files/proxy?url=${encodeURIComponent(httpsUrl)}`
}

const isMarkdownFile = (filename: string): boolean => {
  const lower = filename.toLowerCase()
  return lower.endsWith('.md') || lower.endsWith('.markdown')
}

const markdownComponents = {
  img: ({ src, alt }: any) => (
    <span className="my-4 flex justify-center">
      <img
        src={toProxyUrl(src)}
        alt={alt || ''}
        className="h-auto max-w-[80%] rounded-lg"
      />
    </span>
  ),
}

export default function FileViewerModal({ isOpen, onClose, files }: FileViewerModalProps) {
  const [selectedFile, setSelectedFile] = useState<FileInfo | null>(null)
  const [fileContent, setFileContent] = useState('')
  const [loadingContent, setLoadingContent] = useState(false)
  const [isMobileViewport, setIsMobileViewport] = useState(() => window.innerWidth < 768)
  const { t } = useI18n()

  useEffect(() => {
    const handleResize = () => setIsMobileViewport(window.innerWidth < 768)
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  // Reset state when modal opens/closes or files change (new conversation)
  useEffect(() => {
    if (!isOpen) {
      // Delay reset to allow exit animation
      const timer = setTimeout(() => {
        setSelectedFile(null)
        setFileContent('')
      }, 200)
      return () => clearTimeout(timer)
    }
  }, [isOpen])

  // Reset when files prop changes (different conversation)
  useEffect(() => {
    setSelectedFile(null)
    setFileContent('')
  }, [files])

  useEffect(() => {
    if (isOpen && files.length === 1 && canPreview(files[0].name)) {
      setSelectedFile(files[0])
    }
  }, [isOpen, files])

  // Load file content when selected file changes
  useEffect(() => {
    if (selectedFile && getFileType(selectedFile.name) === 'text') {
      loadFileContent(selectedFile)
    }
  }, [selectedFile])

  const loadFileContent = async (file: FileInfo) => {
    setLoadingContent(true)
    try {
      const fileUrl = toHttps(withApiBase(getContentReference(file)))
      if (!fileUrl) {
        setFileContent(t('noUrlAvailableShort'))
        return
      }
      
      // Use backend proxy to avoid CORS
      const response = await api.get('/files/content', {
        params: { url: fileUrl },
        responseType: 'text'
      })
      setFileContent(response.data)
    } catch (error) {
      console.error('Failed to load file content:', error)
      setFileContent(t('fileLoadFailed'))
    } finally {
      setLoadingContent(false)
    }
  }

  if (!isOpen) return null

  const downloadFile = async (file: FileInfo) => {
    if (isMarkdownFile(file.name)) {
      try {
        const response = await api.get('/files/package-markdown', {
          params: { url: getContentReference(file) || file.url, filename: file.name },
          responseType: 'blob'
        })
        const blob = new Blob([response.data], { type: 'application/zip' })
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${file.name.replace(/\.(md|markdown)$/i, '') || 'report'}.zip`
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
      } catch (error) {
        console.error('Failed to package markdown:', error)
      }
      return
    }

    const directUrl = toProxyUrl(file.url)
    if (directUrl) {
      window.open(directUrl, '_blank', 'noopener,noreferrer')
    }
  }

  const getFileIcon = (type: string) => {
    if (type === 'image') return <Image className="w-5 h-5" />
    if (type === 'data') return <FileText className="w-5 h-5" />
    return <File className="w-5 h-5" />
  }

  const getFileType = (filename: string): string => {
    const ext = filename.split('.').pop()?.toLowerCase() || ''
    if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp'].includes(ext)) return 'image'
    if (['md', 'txt', 'csv', 'json', 'html', 'xml'].includes(ext)) return 'text'
    if (['pdf'].includes(ext)) return 'pdf'
    return 'other'
  }

  const canPreview = (filename: string): boolean => {
    const type = getFileType(filename)
    return ['image', 'text', 'pdf'].includes(type)
  }

  const renderPreview = (file: FileInfo) => {
    const type = getFileType(file.name)
    const fileUrl = toProxyUrl(file.url) || ''
    
    if (type === 'image') {
      return (
        <div className="flex flex-col items-center">
          <img
            src={fileUrl}
            alt={file.name}
            className="max-w-full max-h-[60vh] object-contain rounded-lg"
          />
          <a
            href={fileUrl}
            download={file.name}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-4 flex items-center gap-2 px-4 py-2 bg-neutral-100 dark:bg-neutral-800 hover:bg-neutral-200 dark:hover:bg-neutral-700 rounded-lg transition-colors"
          >
            <Download className="w-4 h-4" />
            <span>{t('download')}</span>
          </a>
        </div>
      )
    }
    
    if (type === 'pdf') {
      if (isMobileViewport) {
        return (
          <div className="flex min-h-[46vh] w-full flex-col items-center justify-center rounded-2xl border border-neutral-200 bg-neutral-50 p-6 text-center dark:border-neutral-700 dark:bg-neutral-800">
            <div className="mb-4 rounded-2xl bg-white p-4 text-neutral-700 shadow-sm dark:bg-neutral-900 dark:text-neutral-200">
              <FileText className="h-10 w-10" />
            </div>
            <h3 className="max-w-full truncate text-base font-semibold text-neutral-900 dark:text-neutral-100">
              {file.name}
            </h3>
            <p className="mt-2 max-w-sm text-sm text-neutral-500 dark:text-neutral-400">
              {t('mobilePdfHint')}
            </p>
            <div className="mt-5 flex flex-col gap-2 sm:flex-row">
              <a
                href={fileUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-neutral-950 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-neutral-800 dark:bg-white dark:text-neutral-950 dark:hover:bg-neutral-200"
              >
                <ExternalLink className="w-4 h-4" />
                {t('preview')}
              </a>
              <a
                href={fileUrl}
                download={file.name}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-4 py-2.5 text-sm font-medium text-neutral-700 ring-1 ring-neutral-200 transition-colors hover:bg-neutral-100 dark:bg-neutral-900 dark:text-neutral-200 dark:ring-neutral-700 dark:hover:bg-neutral-700"
              >
                <Download className="w-4 h-4" />
                {t('download')}
              </a>
            </div>
          </div>
        )
      }

      return (
        <div className="flex flex-col items-center w-full">
          <iframe
            src={fileUrl}
            className="w-full h-[70vh] rounded-lg border border-neutral-200 dark:border-neutral-700"
            title={file.name}
          />
          <a
            href={fileUrl}
            download={file.name}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-4 flex items-center gap-2 px-4 py-2 bg-neutral-100 dark:bg-neutral-800 hover:bg-neutral-200 dark:hover:bg-neutral-700 rounded-lg transition-colors"
          >
            <Download className="w-4 h-4" />
            <span>{t('download')}</span>
          </a>
        </div>
      )
    }
    
    if (type === 'text') {
      const isMd = isMarkdownFile(file.name)
      return (
        <div className="flex flex-col items-center w-full">
          <div className="w-full h-[60vh] bg-neutral-100 dark:bg-neutral-800 rounded-lg p-4 overflow-auto">
            {loadingContent ? (
              <div className="flex items-center justify-center h-full">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-neutral-500"></div>
              </div>
            ) : isMd ? (
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]} components={markdownComponents}>
                  {fileContent}
                </ReactMarkdown>
              </div>
            ) : (
              <pre className="text-sm whitespace-pre-wrap font-mono text-neutral-800 dark:text-neutral-200">
                {fileContent}
              </pre>
            )}
          </div>
          <button
            onClick={() => void downloadFile(file)}
            className="mt-4 flex items-center gap-2 px-4 py-2 bg-neutral-100 dark:bg-neutral-800 hover:bg-neutral-200 dark:hover:bg-neutral-700 rounded-lg transition-colors"
          >
            <Download className="w-4 h-4" />
            <span>{isMd ? t('downloadZip') : t('download')}</span>
          </button>
        </div>
      )
    }
    
    // Other files - cannot preview
    return (
      <div className="flex flex-col items-center justify-center h-[40vh]">
        <File className="w-16 h-16 text-neutral-400 mb-4" />
        <p className="text-neutral-500 mb-4">{t('fileCannotPreview')}</p>
        <a
          href={fileUrl}
          download={file.name}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors"
        >
          <Download className="w-4 h-4" />
          <span>{t('download')}</span>
        </a>
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-3 backdrop-blur-sm sm:p-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="flex max-h-[92dvh] w-full max-w-5xl flex-col rounded-2xl bg-white shadow-2xl dark:bg-neutral-900 sm:max-h-[86vh]"
      >
        {/* Header */}
        <div className="flex items-center justify-between gap-3 border-b border-neutral-200 px-4 py-3 dark:border-neutral-800 sm:px-6 sm:py-4">
          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
            {selectedFile && (
              <button
                onClick={() => {
                  setSelectedFile(null)
                  setFileContent('')
                }}
                className="p-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-lg transition-colors"
                title={t('backToList')}
              >
                <ArrowLeft className="w-5 h-5 text-neutral-500" />
              </button>
            )}
            <h2 className="truncate text-lg font-semibold text-neutral-900 dark:text-neutral-100">
              {selectedFile ? selectedFile.name : t('generatedFiles', { count: files.length })}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-neutral-500" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4 sm:p-6">
          <AnimatePresence mode="wait">
            {selectedFile ? (
              <motion.div
                key="preview"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
              >
                {renderPreview(selectedFile)}
              </motion.div>
            ) : (
              <motion.div
                key="list"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="space-y-4"
              >
                {files.some((file) => getFileType(file.name) === 'image') && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {files.filter((file) => getFileType(file.name) === 'image').map((file, index) => {
                  const fileUrl = toProxyUrl(file.url)

                  return (
                    <motion.div
                      key={index}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: index * 0.05 }}
                      className="overflow-hidden rounded-xl border border-neutral-200 bg-neutral-50 shadow-sm transition-colors hover:border-neutral-300 dark:border-neutral-700 dark:bg-neutral-800 dark:hover:border-neutral-600 group"
                    >
                      <div className="px-3 py-2 border-b border-neutral-200 dark:border-neutral-700">
                        <p className="font-medium text-sm text-neutral-900 dark:text-neutral-100 truncate" title={file.name}>
                          {file.name}
                        </p>
                        <p className="text-xs text-neutral-500 capitalize">{file.type}</p>
                      </div>
                      <div className="relative aspect-video bg-white dark:bg-neutral-900">
                        <img
                          src={fileUrl}
                          alt={file.name}
                          className="h-full w-full object-contain"
                          loading="lazy"
                        />
                        <div className="absolute inset-0 flex items-center justify-center gap-2 bg-black/0 opacity-0 transition-all group-hover:bg-black/25 group-hover:opacity-100">
                          <button
                            onClick={() => setSelectedFile(file)}
                            className="rounded-full bg-white/95 p-2 text-neutral-700 shadow-lg transition-colors hover:bg-white dark:bg-neutral-900/95 dark:text-neutral-200 dark:hover:bg-neutral-800"
                            title={t('preview')}
                            type="button"
                          >
                            <Eye className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => void downloadFile(file)}
                            className="rounded-full bg-white/95 p-2 text-neutral-700 shadow-lg transition-colors hover:bg-white dark:bg-neutral-900/95 dark:text-neutral-200 dark:hover:bg-neutral-800"
                            title={t('download')}
                            type="button"
                          >
                            <Download className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  )
                    })}
                  </div>
                )}

                {files.some((file) => getFileType(file.name) !== 'image') && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {files.filter((file) => getFileType(file.name) !== 'image').map((file, index) => (
                      <motion.div
                        key={`${file.url}-${file.name}`}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: index * 0.05 }}
                        className="flex items-center gap-3 p-4 bg-neutral-50 dark:bg-neutral-800 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors group"
                      >
                        <div className="p-2 bg-white dark:bg-neutral-700 rounded-lg text-neutral-500">
                          {getFileIcon(file.type)}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-neutral-900 dark:text-neutral-100 truncate">
                            {file.name}
                          </p>
                          <p className="text-xs text-neutral-500 capitalize">{file.type}</p>
                        </div>
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          {canPreview(file.name) && (
                            <button
                              onClick={() => setSelectedFile(file)}
                              className="p-2 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded-lg transition-colors"
                              title={t('preview')}
                            >
                              <Eye className="w-4 h-4 text-neutral-600 dark:text-neutral-400" />
                            </button>
                          )}
                          <button
                            onClick={() => void downloadFile(file)}
                            className="p-2 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded-lg transition-colors"
                            title={t('download')}
                          >
                            <Download className="w-4 h-4 text-neutral-600 dark:text-neutral-400" />
                          </button>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  )
}
