import { useState } from 'react'
import { motion } from 'framer-motion'
import { 
  Terminal, 
  ChevronDown, 
  ChevronUp, 
  CheckCircle2, 
  XCircle, 
  Loader2,
  Play,
  Code2,
  Image as ImageIcon,
  Files,
  Search,
  ListTodo
} from 'lucide-react'
import type { ToolCallInfo } from '../../pages/Chat'
import { useI18n } from '../../i18n'

interface ToolCallItemProps {
  toolCall: ToolCallInfo
}

const API_BASE_URL = import.meta.env.VITE_API_URL || ''

const toProxyUrl = (url: string): string => {
  if (url.startsWith('/api/')) return `${API_BASE_URL}${url}`
  try {
    const parsed = new URL(url, window.location.origin)
    if (parsed.origin === window.location.origin && parsed.pathname.startsWith('/api/')) {
      return `${API_BASE_URL}${parsed.pathname}${parsed.search}${parsed.hash}`
    }
  } catch {
    // Keep non-URL strings unchanged.
  }
  if (url.includes('/api/v1/files/content')) return url
  if (!url.startsWith('http')) return url
  const httpsUrl = url.startsWith('http://') ? url.replace('http://', 'https://') : url
  return `${API_BASE_URL}/api/v1/files/proxy?url=${encodeURIComponent(httpsUrl)}`
}

const TodoChecklist = ({ todos }: { todos: Array<{ id?: number; content: string; status: string }> }) => {
  const completed = todos.filter((todo) => todo.status === 'completed').length
  const total = todos.length
  const { t } = useI18n()

  return (
    <div className="rounded-xl border border-neutral-200 bg-white p-2 shadow-sm dark:border-neutral-700 dark:bg-neutral-900/40">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <div className="text-xs font-semibold text-neutral-900 dark:text-white">{t('taskPlan')}</div>
          <div className="text-[11px] text-neutral-400">{t('taskCompleted', { completed, total })}</div>
        </div>
        <div className="rounded-full bg-neutral-100 px-2 py-0.5 text-[11px] font-medium text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300">
          {total ? Math.round((completed / total) * 100) : 0}%
        </div>
      </div>
      <div className="space-y-1.5">
        {todos.map((todo, index) => {
          const isDone = todo.status === 'completed'
          const isActive = todo.status === 'in_progress'
          return (
            <div
              key={`${todo.id || index}-${todo.content}`}
              className={`flex items-start gap-2 rounded-lg border px-2.5 py-1.5 transition-colors ${
                isActive
                  ? 'border-blue-200 bg-blue-50/70 dark:border-blue-900/60 dark:bg-blue-950/20'
                  : isDone
                    ? 'border-neutral-100 bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-800/40'
                    : 'border-neutral-100 bg-white dark:border-neutral-800 dark:bg-neutral-900'
              }`}
            >
              <div className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                isDone
                  ? 'border-green-500 bg-green-500 text-white'
                  : isActive
                    ? 'border-blue-500 bg-blue-500 text-white'
                    : 'border-neutral-300 bg-white dark:border-neutral-600 dark:bg-neutral-900'
              }`}>
                {isDone && <CheckCircle2 className="h-3 w-3" />}
                {isActive && <Loader2 className="h-3 w-3 animate-spin" />}
              </div>
              <div className="min-w-0 flex-1">
                <div className={`text-xs leading-5 ${
                  isDone
                    ? 'text-neutral-400 line-through'
                    : 'text-neutral-800 dark:text-neutral-100'
                }`}>
                  {todo.content}
                </div>
                <div className="text-[10px] uppercase tracking-[0.12em] text-neutral-400">
                  {todo.status.replace('_', ' ')}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

const normalizeText = (value: unknown): string => {
  if (typeof value === 'string') return value
  if (value === null || value === undefined) return ''
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

const normalizeTime = (value: unknown): string | null => {
  if (value === null || value === undefined || value === '') return null
  const numericValue = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numericValue)) return String(value)
  return `${numericValue.toFixed(3)}s`
}

export default function ToolCallItem({ toolCall }: ToolCallItemProps) {
  const [expanded, setExpanded] = useState(true)
  const [showOutput, setShowOutput] = useState(true)
  const { t } = useI18n()

  const getStatusIcon = () => {
    switch (toolCall.status) {
      case 'pending':
        return <Loader2 className="w-4 h-4 text-neutral-500 animate-spin" />
      case 'running':
        return <Play className="w-4 h-4 text-neutral-500" />
      case 'completed':
        return <CheckCircle2 className="w-4 h-4 text-green-600" />
      case 'error':
        return <XCircle className="w-4 h-4 text-red-500" />
      default:
        return null
    }
  }

  const getToolIcon = () => {
    switch (toolCall.name) {
      case 'execute_python':
        return <Code2 className="w-4 h-4" />
      case 'execute_shell':
        return <Terminal className="w-4 h-4" />
      case 'glob_files':
        return <Files className="w-4 h-4" />
      case 'grep_files':
        return <Search className="w-4 h-4" />
      case 'update_todo':
        return <ListTodo className="w-4 h-4" />
      default:
        return <Terminal className="w-4 h-4" />
    }
  }

  const formatToolName = (name: string) => {
    return name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
  }

  // Parse arguments
  let parsedArgs: any = {}
  try {
    parsedArgs = JSON.parse(toolCall.arguments)
  } catch (e) {
    parsedArgs = { raw: toolCall.arguments }
  }

  // Get code or command
  const code = parsedArgs.code || parsedArgs.command || (
    ['glob_files', 'grep_files'].includes(toolCall.name)
      ? JSON.stringify(parsedArgs, null, 2)
      : ''
  )
  
  // Get images from result
  const rawImages = Array.isArray(toolCall.result?.images) ? toolCall.result?.images : []
  const images = rawImages
    .map((img: unknown) => {
      if (typeof img === 'string') return img
      if (img && typeof img === 'object') {
        const imageObject = img as { url?: string; proxy_url?: string; path?: string }
        return imageObject.proxy_url || imageObject.url || imageObject.path || ''
      }
      return ''
    })
    .filter(Boolean)
    .map((img: string) => {
      if (img.startsWith('http')) return img
      if (img.startsWith('/')) return `${window.location.origin}${img}`
      return `${window.location.origin}/${img}`
    })
    .map(toProxyUrl)
  const output = normalizeText(toolCall.result?.output || toolCall.result?.stdout)
  const contentPreview = normalizeText(toolCall.result?.content_preview)
  const todos = toolCall.name === 'update_todo'
    ? (Array.isArray(toolCall.result?.todos) ? toolCall.result?.todos : Array.isArray(parsedArgs.todos) ? parsedArgs.todos : [])
    : []
  const executionTime = normalizeTime(toolCall.result?.execution_time)

  return (
    <motion.div
      initial={{ opacity: 0, y: 5 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-2xl overflow-hidden shadow-sm"
    >
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-3 py-2.5 flex items-center justify-between bg-neutral-50 dark:bg-neutral-800 hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-white dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 rounded-xl shadow-sm">
            {getToolIcon()}
          </div>
          <div className="text-left">
            <span className="text-sm font-medium text-neutral-700 dark:text-neutral-300">
              {formatToolName(toolCall.name)}
            </span>
          </div>
          {images.length > 0 && (
            <span className="flex items-center gap-1 text-xs text-neutral-500 bg-neutral-100 dark:bg-neutral-700 px-2 py-0.5 rounded">
              <ImageIcon className="w-3 h-3" />
              {images.length}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {getStatusIcon()}
          {expanded ? (
            <ChevronUp className="w-4 h-4 text-neutral-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-neutral-400" />
          )}
        </div>
      </button>

      {/* Content */}
      {expanded && (
        <div className="p-3 space-y-3 text-sm">
          {toolCall.name === 'update_todo' && todos.length > 0 && (
            <TodoChecklist todos={todos} />
          )}

          {/* Code Section */}
          {toolCall.name !== 'update_todo' && code && (
            <div>
              <div className="text-xs text-neutral-400 mb-1">{t('code')}</div>
              <div className="bg-neutral-100 dark:bg-neutral-900 rounded p-2 overflow-x-auto">
                <pre className="text-neutral-700 dark:text-neutral-300 font-mono text-xs whitespace-pre-wrap">{code}</pre>
              </div>
            </div>
          )}

          {/* Images Section */}
          {images.length > 0 && (
            <div>
              <div className="text-xs text-neutral-400 mb-1 flex items-center gap-1">
                <ImageIcon className="w-3 h-3" />
                {t('images', { count: images.length })}
              </div>
              <div className="grid grid-cols-1 gap-2">
                {images.map((imgUrl: string, idx: number) => (
                  <div key={idx} className="bg-neutral-100 dark:bg-neutral-900 rounded p-1 overflow-hidden">
                    <img 
                      src={imgUrl} 
                      alt={`Generated ${idx + 1}`}
                      className="w-full h-auto rounded block"
                      onError={(e) => {
                        const img = e.target as HTMLImageElement;
                        img.style.display = 'none';
                      }}
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Result Section */}
          {toolCall.result && toolCall.name !== 'update_todo' && (
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-neutral-400">{t('output')}</span>
                <button
                  onClick={() => setShowOutput(!showOutput)}
                  className="text-xs text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
                >
                  {showOutput ? t('hide') : t('show')}
                </button>
              </div>
              
              {showOutput && (
                <div className="space-y-2">
                  {output && (
                    <div className="bg-neutral-100 dark:bg-neutral-900 rounded p-2">
                      <pre className="text-xs text-neutral-700 dark:text-neutral-300 font-mono whitespace-pre-wrap">{output}</pre>
                    </div>
                  )}

                  {contentPreview && (
                    <div>
                      <div className="text-xs text-neutral-400 mb-1">{t('writtenContentPreview')}</div>
                      <div className="bg-neutral-100 dark:bg-neutral-900 rounded p-2 max-h-64 overflow-auto">
                        <pre className="text-xs text-neutral-700 dark:text-neutral-300 font-mono whitespace-pre-wrap">{contentPreview}</pre>
                      </div>
                    </div>
                  )}

                  {(toolCall.result.exit_code !== undefined || executionTime) && (
                    <div className="flex items-center gap-4 text-xs text-neutral-400">
                      {toolCall.result.exit_code !== undefined && <span>{t('exit')}: {toolCall.result.exit_code}</span>}
                      {executionTime && <span>{t('time')}: {executionTime}</span>}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </motion.div>
  )
}
