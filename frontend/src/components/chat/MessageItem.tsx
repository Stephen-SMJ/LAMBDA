import { useState } from 'react'
import { Copy, Check, ChevronDown, ChevronRight, Paperclip, FolderOpen, FileText, Eye, Terminal } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypeHighlight from 'rehype-highlight'
import 'highlight.js/styles/github.css'
import 'katex/dist/katex.min.css'
import type { Message } from '../../types'
import type { ToolCallInfo } from '../../pages/Chat'
import FileViewerModal from './FileViewerModal'
import ToolCallItem from './ToolCallItem'
import { useI18n } from '../../i18n'

interface MessageItemProps {
  message: Message
  isStreaming?: boolean
}

const API_BASE_URL = import.meta.env.VITE_API_URL || ''

const toDisplayUrl = (url: string | undefined): string | undefined => {
  if (!url) return url
  if (url.startsWith('/api/')) return `${API_BASE_URL}${url}`
  try {
    const parsed = new URL(url, window.location.origin)
    if (parsed.origin === window.location.origin && parsed.pathname.startsWith('/api/')) {
      return `${API_BASE_URL}${parsed.pathname}${parsed.search}${parsed.hash}`
    }
  } catch {
    // Keep relative paths and invalid URLs unchanged.
  }
  return url.startsWith('http://') ? url.replace('http://', 'https://') : url
}

// Parse attached files from message content
const parseAttachments = (content: string): { text: string; files: string[] } => {
  const match = content.match(/\n\n📎 \*\*Attached \d+ file\(s\):\*\* (.+)$/)
  if (match) {
    const files = match[1].split(', ').filter(Boolean)
    const text = content.replace(match[0], '')
    return { text, files }
  }
  return { text: content, files: [] }
}

// Remove all HTML comments including FILES marker for display
const cleanAllHtmlComments = (content: string): string => {
  return content.replace(/<!--[\s\S]*?-->/g, '')
}

// Parse execution details from assistant content (supports both old and new format)
const parseExecutionDetails = (content: string): { mainContent: string; hasExecutionDetails: boolean; executionContent: string } => {
  // Try new format: <!--COLLAPSIBLE:Analyze details--> ... <!--END_COLLAPSIBLE-->
  // Use more flexible pattern that doesn't require exact newline matching
  const collapsibleMatch = content.match(/<!--COLLAPSIBLE:Analyze details-->[\s\S]*?<!--END_COLLAPSIBLE-->/)
  if (collapsibleMatch) {
    const mainPart = content.substring(0, collapsibleMatch.index)
    const execPart = collapsibleMatch[0]
      .replace(/<!--COLLAPSIBLE:Analyze details-->\n?/, '')
      .replace(/\n?<!--END_COLLAPSIBLE-->/, '')
      .replace(/^(<p>)?\s*(<strong>)?\s*(\*\*)?Analyze details(\*\*)?\s*(<\/strong>)?\s*(<\/p>)?\s*/i, '')
      .replace(/\*\*`([^`]+)`\*\*/g, '**$1**')
      .trim()
    
    // Clean ALL HTML comments including FILES marker from mainPart for display
    const cleanedMain = cleanAllHtmlComments(mainPart).trim()
    
    return {
      mainContent: cleanedMain,
      hasExecutionDetails: true,
      executionContent: execPart
    }
  }
  // Try old format: **Analyze details** or **Execution Details:**
  const execMatch = content.match(/\n\n---\n\n\*\*(Analyze details|Execution Details):\*\*[\s\S]*$/)
  if (execMatch) {
    return {
      mainContent: cleanAllHtmlComments(content.substring(0, execMatch.index)),
      hasExecutionDetails: true,
      executionContent: execMatch[0]
    }
  }
  // No execution details found - clean any remaining HTML comments
  return { mainContent: cleanAllHtmlComments(content), hasExecutionDetails: false, executionContent: '' }
}

// Parse files from message content
interface FileInfo {
  name: string
  url: string
  type: string
}

const parseFiles = (content: string): FileInfo[] => {
  // Use more robust pattern to match FILES marker with JSON content
  const match = content.match(/<!--FILES:([\s\S]*?)-->/)
  if (match) {
    try {
      const files = JSON.parse(match[1].trim())
      const seen = new Set<string>()
      return files.filter((file: FileInfo) => {
        const key = file.url || `${file.type}:${file.name}`
        if (!key || seen.has(key)) return false
        seen.add(key)
        return true
      })
    } catch {
      return []
    }
  }
  return []
}

// File attachment chip component
const FileAttachmentChip = ({ filename }: { filename: string }) => (
  <motion.div
    initial={{ opacity: 0, scale: 0.9 }}
    animate={{ opacity: 1, scale: 1 }}
    className="inline-flex items-center gap-2 px-3 py-1.5 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg text-sm text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors cursor-pointer"
  >
    <Paperclip className="w-4 h-4" />
    <span className="font-medium truncate max-w-[200px]">{filename}</span>
  </motion.div>
)

// Collapsible execution details component
const ExecutionDetails = ({ content, toolCalls = [] }: { content: string; toolCalls?: ToolCallInfo[] }) => {
  const [isExpanded, setIsExpanded] = useState(false)
  const { t } = useI18n()
  
  return (
    <div className="mt-4 overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-sm dark:border-neutral-700 dark:bg-neutral-800">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between gap-3 px-3 py-3 bg-neutral-50 hover:bg-neutral-100 dark:bg-neutral-800 dark:hover:bg-neutral-700/60 transition-colors"
      >
        <span className="flex min-w-0 items-center gap-3">
          <span className="p-1.5 bg-white dark:bg-neutral-700 text-neutral-600 dark:text-neutral-300 rounded-xl shadow-sm">
            <Terminal className="w-4 h-4" />
          </span>
          <span className="text-sm font-semibold text-neutral-800 dark:text-neutral-100">
            {t('analysisDetails')}
          </span>
        </span>
        <span className="flex items-center gap-1 text-xs font-medium text-neutral-400">
          {isExpanded ? t('hide') : t('show')}
          {isExpanded ? (
            <ChevronDown className="w-4 h-4 text-neutral-500" />
          ) : (
            <ChevronRight className="w-4 h-4 text-neutral-500" />
          )}
        </span>
      </button>
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: 'auto' }}
            exit={{ height: 0 }}
            className="overflow-hidden"
          >
            <div className="p-4 bg-neutral-50 dark:bg-neutral-900/50">
              {toolCalls.length > 0 ? (
                <div className="space-y-2">
                  {toolCalls.map((toolCall, index) => (
                    <ToolCallItem
                      key={toolCall.id || `detail_${index}`}
                      toolCall={toolCall}
                    />
                  ))}
                </div>
              ) : (
                <ReactMarkdown
                  remarkPlugins={[remarkGfm, remarkMath]}
                  rehypePlugins={[rehypeKatex, rehypeHighlight]}
                  components={{
                    pre: ({ children }: any) => (
                      <pre className="bg-neutral-100 dark:bg-neutral-800 rounded-lg p-3 overflow-x-auto my-2 text-xs">
                        {children}
                      </pre>
                    ),
                    code: ({ inline, children }: any) =>
                      inline ? (
                        <code className="bg-neutral-100 dark:bg-neutral-800 px-1 py-0.5 rounded text-xs">
                          {children}
                        </code>
                      ) : (
                        <code className="text-xs">{children}</code>
                      ),
                  }}
                >
                  {content}
                </ReactMarkdown>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default function MessageItem({ message, isStreaming }: MessageItemProps) {
  const [copied, setCopied] = useState(false)
  const [showFileViewer, setShowFileViewer] = useState(false)
  const [viewerFiles, setViewerFiles] = useState<FileInfo[]>([])
  const isUser = message.role === 'user'
  const isAssistant = message.role === 'assistant'
  const { t } = useI18n()
  
  // Parse attachments for user messages
  const { text: userText, files: attachedFiles } = isUser ? parseAttachments(message.content) : { text: message.content, files: [] }
  
  // Parse execution details for assistant messages
  const { mainContent, hasExecutionDetails, executionContent } = isAssistant ? parseExecutionDetails(message.content) : { mainContent: message.content, hasExecutionDetails: false, executionContent: '' }
  
  // Parse files from message
  const generatedFiles = isAssistant ? parseFiles(message.content) : []
  const reportPdf = generatedFiles.find((file) => {
    const name = file.name.toLowerCase()
    return name.endsWith('.pdf') && (name.includes('report') || name.includes('analysis'))
  })
  const structuredToolCalls: ToolCallInfo[] = (() => {
    if (!isAssistant || !message.tool_calls) return []
    try {
      const parsed = JSON.parse(message.tool_calls)
      if (!Array.isArray(parsed)) return []
      return parsed.map((tc: any, index: number) => ({
        id: tc.id || `saved_${index}`,
        name: tc.function?.name || tc.name || 'unknown',
        arguments: tc.function?.arguments || tc.arguments || '{}',
        result: tc.result || undefined,
        status: tc.status || (tc.result?.success === false || tc.result?.error || tc.error ? 'error' : 'completed'),
      }))
    } catch {
      return []
    }
  })()

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  return (
    <div className={`py-6 ${isUser ? 'bg-white dark:bg-neutral-900' : 'bg-neutral-50 dark:bg-neutral-800/50'}`}>
      <div className="max-w-3xl mx-auto px-4">
        {/* Role Label */}
        <div className="text-xs font-medium text-neutral-400 mb-2">
          {isUser ? 'You' : 'LAMBDA'}
        </div>

        {/* Content */}
        <div className="prose prose-neutral dark:prose-invert max-w-none">
          {isAssistant ? (
            <>
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkMath]}
                rehypePlugins={[rehypeKatex, rehypeHighlight]}
                components={{
                  pre: ({ children }: any) => (
                    <pre className="bg-neutral-100 dark:bg-neutral-800 rounded-lg p-4 overflow-x-auto my-2 text-sm">
                      {children}
                    </pre>
                  ),
                  code: ({ inline, children }: any) =>
                    inline ? (
                      <code className="bg-neutral-100 dark:bg-neutral-800 px-1.5 py-0.5 rounded text-sm">
                        {children}
                      </code>
                    ) : (
                      <code className="text-sm">{children}</code>
                    ),
                  img: ({ src, alt }: any) => (
                    <span className="my-4 flex justify-center">
                      <img
                        src={toDisplayUrl(src)}
                        alt={alt || ''}
                        className="h-auto max-w-[80%] rounded-lg"
                      />
                    </span>
                  ),
                }}
              >
                {mainContent}
              </ReactMarkdown>
              
              {/* Collapsible Execution Details - show even during streaming */}
              {hasExecutionDetails && executionContent && (
                <ExecutionDetails content={executionContent} toolCalls={structuredToolCalls} />
              )}

              {reportPdf && !isStreaming && (
                <button
                  type="button"
                  onClick={() => {
                    setViewerFiles([reportPdf])
                    setShowFileViewer(true)
                  }}
                  className="mt-5 flex w-full items-center justify-between gap-4 rounded-2xl border border-neutral-200 bg-white p-4 text-left shadow-sm transition-all hover:border-neutral-300 hover:shadow-md dark:border-neutral-700 dark:bg-neutral-900/70 dark:hover:border-neutral-600"
                >
                  <span className="flex min-w-0 items-center gap-3">
                    <span className="rounded-xl bg-neutral-100 p-2 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-200">
                      <FileText className="h-5 w-5" />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-semibold text-neutral-900 dark:text-neutral-100">{t('pdfReportReady')}</span>
                      <span className="block truncate text-xs text-neutral-500 dark:text-neutral-400">{reportPdf.name}</span>
                    </span>
                  </span>
                  <span className="inline-flex items-center gap-1 rounded-full bg-neutral-950 px-3 py-1.5 text-xs font-medium text-white dark:bg-white dark:text-neutral-950">
                    <Eye className="h-3.5 w-3.5" />
                    {t('preview')}
                  </span>
                </button>
              )}
            </>
          ) : (
            <>
              <p className="whitespace-pre-wrap text-neutral-900 dark:text-neutral-100">{userText}</p>
              
              {/* File Attachments */}
              {attachedFiles.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-3">
                  {attachedFiles.map((filename, index) => (
                    <FileAttachmentChip key={index} filename={filename} />
                  ))}
                </div>
              )}
            </>
          )}
          
          {/* Streaming Indicator */}
          {isStreaming && (
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ repeat: Infinity, duration: 0.8 }}
              className="inline-block w-2 h-4 bg-neutral-400 ml-1 align-middle"
            />
          )}
        </div>

        {/* Actions for Assistant */}
        {isAssistant && !isStreaming && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-center gap-2 mt-3"
          >
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 px-2 py-1 text-xs text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded transition-colors"
            >
              {copied ? (
                <>
                  <Check className="w-3 h-3" />
                  {t('copied')}
                </>
              ) : (
                <>
                  <Copy className="w-3 h-3" />
                  {t('copy')}
                </>
              )}
            </button>
            
            {/* View Files Button */}
            {generatedFiles.length > 0 && (
              <button
                onClick={() => {
                  setViewerFiles(generatedFiles)
                  setShowFileViewer(true)
                }}
                className="flex items-center gap-1 px-2 py-1 text-xs text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded transition-colors"
              >
                <FolderOpen className="w-3 h-3" />
                {t('viewFiles', { count: generatedFiles.length })}
              </button>
            )}
          </motion.div>
        )}
      </div>
      
      {/* File Viewer Modal */}
      <FileViewerModal
        isOpen={showFileViewer}
        onClose={() => setShowFileViewer(false)}
        files={viewerFiles.length > 0 ? viewerFiles : generatedFiles}
      />
    </div>
  )
}
