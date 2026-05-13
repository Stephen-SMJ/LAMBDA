import { useState, useEffect, useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  PanelRightClose, 
  PanelRightOpen,
  Terminal, 
  FolderOpen,
  Download,
  FileText,
  Image as ImageIcon,
  File,
  CheckCircle2,
  XCircle,
  Loader2,
  ChevronDown,
  ChevronRight,
  Package,
  Eye,
  X,
  FileCode
} from 'lucide-react'
import { api } from '../../services/api'
import type { ToolCallInfo } from '../../pages/Chat'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import { useI18n } from '../../i18n'

interface RightPanelProps {
  isOpen: boolean
  onToggle: () => void
  toolCalls: ToolCallInfo[]
  isStreaming: boolean
  sessionId?: string
}

interface FileItem {
  name: string
  path: string
  url?: string
  size: number
  modified: number
  type: string
  category: string
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

const getContentReference = (file: FileItem): string | undefined => {
  if (file.url?.startsWith('/api/')) return file.path
  return file.url || file.path
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

export default function RightPanel({ 
  isOpen, 
  onToggle, 
  toolCalls, 
  isStreaming,
  sessionId 
}: RightPanelProps) {
  const [activeTab, setActiveTab] = useState<'execution' | 'files'>('execution')
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set())
  const [files, setFiles] = useState<FileItem[]>([])
  const [loadingFiles, setLoadingFiles] = useState(false)
  const { t } = useI18n()
  
  // Markdown preview state
  const [previewFile, setPreviewFile] = useState<FileItem | null>(null)
  const [previewContent, setPreviewContent] = useState('')
  const [loadingPreview, setLoadingPreview] = useState(false)

  // Process files to ensure HTTPS (using useMemo to avoid direct mutation)
  const processedFiles = useMemo(() => {
    return files.map(file => ({
      ...file,
      path: toHttps(withApiBase(file.path)) || file.path,
      url: toHttps(withApiBase(file.url)) || file.url,
      proxyUrl: toProxyUrl(file.url || file.path)
    }))
  }, [files])

  // Reset preview when session changes
  useEffect(() => {
    setPreviewFile(null)
    setPreviewContent('')
    setFiles([])
  }, [sessionId])

  // Fetch files when session changes or tab switches to files
  useEffect(() => {
    if (sessionId && activeTab === 'files') {
      fetchFiles()
    }
  }, [sessionId, activeTab])

  // Auto-refresh files when streaming completes
  useEffect(() => {
    if (!isStreaming && sessionId && activeTab === 'files') {
      const timer = setTimeout(() => {
        fetchFiles()
      }, 2000)
      return () => clearTimeout(timer)
    }
  }, [isStreaming, sessionId, activeTab])

  // Fetch files from API
  const fetchFiles = async () => {
    if (!sessionId) return
    setLoadingFiles(true)
    try {
      const response = await api.get(`/files/session/${sessionId}`)
      if (response.data?.files) {
        setFiles(response.data.files)
      }
    } catch (error) {
      console.error('Failed to fetch files:', error)
    } finally {
      setLoadingFiles(false)
    }
  }

  // Fetch and preview markdown file (using backend proxy to avoid CORS)
  const previewMarkdown = async (file: FileItem) => {
    // Clear previous content first to avoid showing old file
    setPreviewContent('')
    setPreviewFile(file)
    setLoadingPreview(true)
    try {
      // Use the original URL from the file (processedFiles has HTTPS)
      const fileUrl = getContentReference(file)
      if (!fileUrl) {
        setPreviewContent(t('noUrlAvailable'))
        return
      }
      // Use backend proxy to avoid CORS issues with OSS
      const response = await api.get('/files/content', {
        params: { url: fileUrl },
        responseType: 'text'
      })
      setPreviewContent(response.data)
    } catch (error) {
      console.error('Failed to preview markdown:', error)
      setPreviewContent(t('previewLoadFailed'))
    } finally {
      setLoadingPreview(false)
    }
  }

  // Toggle step expansion
  const toggleStep = (index: number) => {
    const newExpanded = new Set(expandedSteps)
    if (newExpanded.has(index)) {
      newExpanded.delete(index)
    } else {
      newExpanded.add(index)
    }
    setExpandedSteps(newExpanded)
  }

  // Format file size
  const formatSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  }

  // Get file icon
  const getFileIcon = (category: string) => {
    switch (category) {
      case 'image':
        return <ImageIcon className="w-4 h-4 text-purple-500" />
      case 'pdf':
        return <FileText className="w-4 h-4 text-red-500" />
      case 'latex':
      case '.tex':
        return <FileText className="w-4 h-4 text-blue-500" />
      case 'uploaded':
        return <File className="w-4 h-4 text-green-500" />
      default:
        return <File className="w-4 h-4 text-neutral-500" />
    }
  }

  // Download all files as zip
  const downloadAll = async () => {
    if (!sessionId) return
    try {
      const response = await api.post(`/files/package/${sessionId}`, {}, {
        responseType: 'blob'
      })
      const blob = new Blob([response.data], { type: 'application/zip' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${sessionId}_package.zip`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error) {
      console.error('Failed to download package:', error)
    }
  }

  // Download single file
  const downloadFile = async (file: FileItem) => {
    if (isMarkdown(file)) {
      try {
        const response = await api.get('/files/package-markdown', {
          params: { url: getContentReference(file), filename: file.name },
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

    const url = toProxyUrl(file.url || file.path)
    if (url) {
      window.open(url, '_blank', 'noopener,noreferrer')
    }
  }

  // Check if file is markdown
  const isMarkdown = (file: FileItem) => {
    return file.name.toLowerCase().endsWith('.md') || 
           file.name.toLowerCase().endsWith('.markdown')
  }

  if (!isOpen) {
    return (
      <button
        onClick={onToggle}
        className="fixed right-4 top-20 z-50 flex items-center gap-2 rounded-full border border-neutral-200 bg-white px-3 py-2 text-sm font-medium text-neutral-700 shadow-lg transition-colors hover:bg-neutral-100 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-200 dark:hover:bg-neutral-700"
        title={t('openLogsFilesPanel')}
      >
        <PanelRightOpen className="h-4 w-4" />
        <span>{t('logsAndFiles')}</span>
      </button>
    )
  }

  return (
    <motion.div
      initial={{ width: 0, opacity: 0 }}
      animate={{ width: 340, opacity: 1 }}
      exit={{ width: 0, opacity: 0 }}
      className="h-full bg-neutral-50 dark:bg-neutral-900 border-l border-neutral-200 dark:border-neutral-800 flex flex-col flex-shrink-0"
    >
      {/* Header */}
      <div className="h-14 border-b border-neutral-200 dark:border-neutral-800 flex items-center justify-between px-4">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('execution')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'execution'
                ? 'bg-neutral-200 dark:bg-neutral-800 text-neutral-900 dark:text-white'
                : 'text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300'
            }`}
          >
            <Terminal className="w-4 h-4" />
            {t('analysisDetails')}
          </button>
          <button
            onClick={() => setActiveTab('files')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'files'
                ? 'bg-neutral-200 dark:bg-neutral-800 text-neutral-900 dark:text-white'
                : 'text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300'
            }`}
          >
            <FolderOpen className="w-4 h-4" />
            {t('files')}
          </button>
        </div>
        <button
          onClick={onToggle}
          className="p-1.5 hover:bg-neutral-200 dark:hover:bg-neutral-800 rounded-lg transition-colors"
        >
          <PanelRightClose className="w-4 h-4 text-neutral-500" />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <AnimatePresence mode="wait">
          {activeTab === 'execution' ? (
            <motion.div
              key="execution"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="p-4 space-y-3"
            >
              {isStreaming && toolCalls.length === 0 && (
                <div className="flex items-center gap-2 text-neutral-500 text-sm">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {t('initializing')}
                </div>
              )}

              {toolCalls.map((tc, index) => (
                <div
                  key={tc.id || index}
                  className="border border-neutral-200 dark:border-neutral-700 rounded-lg overflow-hidden bg-white dark:bg-neutral-800"
                >
                  {/* Step Header */}
                  <button
                    onClick={() => toggleStep(index)}
                    className="w-full px-3 py-2 flex items-center justify-between bg-neutral-50 dark:bg-neutral-800 hover:bg-neutral-100 dark:hover:bg-neutral-700/50 transition-colors cursor-pointer border-b border-neutral-200 dark:border-neutral-700 last:border-b-0"
                    type="button"
                  >
                    <div className="flex items-center gap-2">
                      {tc.status === 'pending' && <Loader2 className="w-4 h-4 text-neutral-400 animate-spin" />}
                      {tc.status === 'completed' && <CheckCircle2 className="w-4 h-4 text-green-500" />}
                      {tc.status === 'error' && <XCircle className="w-4 h-4 text-red-500" />}
                      <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
                        {tc.name}
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className="text-xs text-neutral-400">
                        {expandedSteps.has(index) ? t('hide') : t('show')}
                      </span>
                      {expandedSteps.has(index) ? (
                        <ChevronDown className="w-4 h-4 text-neutral-500" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-neutral-500" />
                      )}
                    </div>
                  </button>

                  {/* Step Details */}
                  {expandedSteps.has(index) && (
                    <div className="border-t border-neutral-200 dark:border-neutral-700 overflow-hidden">
                      <div className="p-3 space-y-2 text-xs">
                          {/* Arguments */}
                          <div>
                            <span className="text-neutral-500 font-medium">{t('arguments')}</span>
                            <pre className="mt-1 p-2 bg-neutral-100 dark:bg-neutral-900 rounded text-neutral-700 dark:text-neutral-300 overflow-x-auto">
                              {JSON.stringify(JSON.parse(tc.arguments || '{}'), null, 2)}
                            </pre>
                          </div>

                          {/* Result */}
                          {tc.result && (
                            <div>
                              <span className="text-neutral-500 font-medium">{t('result')}</span>
                              {(tc.result.stdout || tc.result.output) && (
                                <pre className="mt-1 p-2 bg-neutral-100 dark:bg-neutral-900 rounded text-green-600 dark:text-green-400 overflow-x-auto max-h-32">
                                  {tc.result.stdout || tc.result.output}
                                </pre>
                              )}
                              {tc.result.content_preview && (
                                <>
                                  <span className="mt-2 block text-neutral-500 font-medium">{t('writtenContentPreview')}:</span>
                                  <pre className="mt-1 p-2 bg-neutral-100 dark:bg-neutral-900 rounded text-neutral-700 dark:text-neutral-300 overflow-x-auto max-h-48">
                                    {tc.result.content_preview}
                                  </pre>
                                </>
                              )}
                              {tc.result.stderr && (
                                <pre className="mt-1 p-2 bg-neutral-100 dark:bg-neutral-900 rounded text-red-600 dark:text-red-400 overflow-x-auto max-h-32">
                                  {tc.result.stderr}
                                </pre>
                              )}
                              {tc.result.images && tc.result.images.length > 0 && (
                                <div className="mt-2 flex flex-wrap gap-2">
                                  {tc.result.images.map((img: string, i: number) => (
                                    <a
                                      key={i}
                                      href={img}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="text-blue-500 hover:underline"
                                    >
                                      {t('imageLabel', { index: i + 1 })}
                                    </a>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                ))}

              {toolCalls.length === 0 && !isStreaming && (
                <div className="text-center text-neutral-400 text-sm py-8">
                  {t('noAnalysisDetails')}
                </div>
              )}
            </motion.div>
          ) : (
            <motion.div
              key="files"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="p-4"
            >
              {/* Refresh & Download All Buttons */}
              <div className="flex gap-2 mb-4">
                <button
                  onClick={fetchFiles}
                  disabled={loadingFiles}
                  className="flex-1 flex items-center justify-center gap-2 px-3 py-2 bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 rounded-lg hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors text-sm font-medium disabled:opacity-50"
                >
                  {loadingFiles ? <Loader2 className="w-4 h-4 animate-spin" /> : <FolderOpen className="w-4 h-4" />}
                  {t('refresh')}
                </button>
                {files.length > 0 && (
                  <button
                    onClick={downloadAll}
                    className="flex items-center justify-center gap-2 px-3 py-2 bg-neutral-900 dark:bg-white text-white dark:text-neutral-900 rounded-lg hover:bg-neutral-700 dark:hover:bg-neutral-200 transition-colors"
                  >
                    <Package className="w-4 h-4" />
                  </button>
                )}
              </div>

              {/* Markdown Preview - Only in Files Tab */}
              {previewFile && (
                <div className="mb-4 border border-neutral-200 dark:border-neutral-700 rounded-lg bg-white dark:bg-neutral-800 overflow-hidden">
                  <div className="flex items-center justify-between px-3 py-2 bg-neutral-100 dark:bg-neutral-700 border-b border-neutral-200 dark:border-neutral-600">
                    <div className="flex items-center gap-2">
                      <FileCode className="w-4 h-4 text-blue-500" />
                      <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300 truncate max-w-[200px]">
                        {previewFile.name}
                      </span>
                    </div>
                    <button
                      onClick={() => {
                        setPreviewFile(null)
                        setPreviewContent('')
                      }}
                      className="p-1 hover:bg-neutral-200 dark:hover:bg-neutral-600 rounded transition-colors"
                    >
                      <X className="w-4 h-4 text-neutral-500" />
                    </button>
                  </div>
                  <div className="p-3 max-h-64 overflow-y-auto">
                    {loadingPreview ? (
                      <div className="flex items-center justify-center py-4">
                        <Loader2 className="w-5 h-5 animate-spin text-neutral-400" />
                      </div>
                    ) : (
                      <div className="prose prose-sm dark:prose-invert max-w-none">
                        <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]} components={markdownComponents}>
                          {previewContent}
                        </ReactMarkdown>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* File List */}
              <div className="space-y-3">
                {processedFiles.map((file) => {
                  const isImage = file.category === 'image'
                  const fileUrl = file.proxyUrl || file.path

                  return (
                    <div
                      key={file.path}
                      className={
                        isImage
                          ? 'overflow-hidden rounded-xl border border-neutral-200 bg-white shadow-sm transition-colors hover:border-neutral-300 dark:border-neutral-700 dark:bg-neutral-800 dark:hover:border-neutral-600 group'
                          : 'flex items-center gap-3 p-3 bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-lg hover:border-neutral-300 dark:hover:border-neutral-600 transition-colors'
                      }
                    >
                      {isImage ? (
                        <>
                          <div className="px-3 py-2 border-b border-neutral-200 dark:border-neutral-700">
                            <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300 truncate" title={file.name}>
                              {file.name}
                            </p>
                            <p className="text-xs text-neutral-400">
                              {formatSize(file.size)} • {file.category}
                            </p>
                          </div>
                          <div className="relative aspect-video bg-neutral-50 dark:bg-neutral-900">
                            <img
                              src={fileUrl}
                              alt={file.name}
                              className="h-full w-full object-contain"
                              loading="lazy"
                            />
                            <div className="absolute inset-0 flex items-center justify-center gap-2 bg-black/0 opacity-0 transition-all group-hover:bg-black/25 group-hover:opacity-100">
                              <a
                                href={fileUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="rounded-full bg-white/95 p-2 text-neutral-700 shadow-lg transition-colors hover:bg-white dark:bg-neutral-900/95 dark:text-neutral-200 dark:hover:bg-neutral-800"
                                title={t('preview')}
                              >
                                <Eye className="w-4 h-4" />
                              </a>
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
                        </>
                      ) : (
                        <>
                          {getFileIcon(file.category)}
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300 truncate">
                              {file.name}
                            </p>
                            <p className="text-xs text-neutral-400">
                              {formatSize(file.size)} • {file.category}
                            </p>
                          </div>
                          <div className="flex items-center gap-1">
                            {isMarkdown(file) && (
                              <button
                                onClick={() => previewMarkdown(file)}
                                className="p-1.5 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded transition-colors"
                                title={t('preview')}
                              >
                                <Eye className="w-4 h-4 text-blue-500" />
                              </button>
                            )}
                            <button
                              onClick={() => void downloadFile(file)}
                              className="p-1.5 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded transition-colors"
                              title={t('download')}
                            >
                              <Download className="w-4 h-4 text-neutral-500" />
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  )
                })}

                {processedFiles.length === 0 && !loadingFiles && (
                  <div className="text-center text-neutral-400 text-sm py-8">
                    {t('noFilesSession')}
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  )
}
