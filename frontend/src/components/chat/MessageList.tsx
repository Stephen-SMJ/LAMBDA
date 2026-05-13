import { useRef, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { ChevronDown, ChevronRight, Brain } from 'lucide-react'
import MessageItem from './MessageItem'
import ToolCallItem from './ToolCallItem'
import type { Message } from '../../types'
import type { ToolCallInfo } from '../../pages/Chat'

interface MessageListProps {
  messages: Message[]
  streamingContent: string
  isStreaming: boolean
  toolCalls?: ToolCallInfo[]
  messagesEndRef: React.RefObject<HTMLDivElement>
  reasoningContent?: string
}

export default function MessageList({
  messages,
  streamingContent,
  isStreaming,
  toolCalls = [],
  messagesEndRef,
  reasoningContent,
}: MessageListProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [isReasoningExpanded, setIsReasoningExpanded] = useState(true)

  // Auto-scroll to bottom
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [messages, streamingContent, toolCalls, reasoningContent])

  return (
    <div
      ref={containerRef}
      className="h-full max-h-full overflow-y-auto overscroll-contain [overflow-anchor:none]"
    >
      {messages.map((message) => (
        <motion.div
          key={message.id}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.2 }}
        >
          <MessageItem
            message={message}
          />
        </motion.div>
      ))}

      {/* Active Reasoning Display */}
      {(isStreaming && reasoningContent) && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="py-4 bg-neutral-50 dark:bg-neutral-800/50"
        >
          <div className="max-w-3xl mx-auto px-4">
            <button
              onClick={() => setIsReasoningExpanded(!isReasoningExpanded)}
              className="flex items-center gap-2 text-xs font-medium text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors mb-2"
            >
              <Brain className="w-4 h-4" />
              <span>Thinking</span>
              {isReasoningExpanded ? (
                <ChevronDown className="w-3 h-3" />
              ) : (
                <ChevronRight className="w-3 h-3" />
              )}
            </button>
            {isReasoningExpanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="bg-neutral-100 dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 rounded-lg p-3"
              >
                <pre className="text-xs text-neutral-600 dark:text-neutral-400 whitespace-pre-wrap font-mono leading-relaxed">
                  {reasoningContent}
                </pre>
              </motion.div>
            )}
          </div>
        </motion.div>
      )}

      {/* Active Tool Calls Display */}
      {isStreaming && toolCalls.length > 0 && (
        <div className="py-4 bg-neutral-50 dark:bg-neutral-800/50">
          <div className="max-w-3xl mx-auto px-4">
            <div className="text-xs font-medium text-neutral-400 mb-2">
              LAMBDA
            </div>
            <div className="space-y-2">
              {toolCalls.map((toolCall, index) => (
                <ToolCallItem
                  key={toolCall.id || index}
                  toolCall={toolCall}
                />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Streaming Message */}
      {isStreaming && streamingContent && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          <MessageItem
            message={{
              id: -1,
              conversation_id: 0,
              role: 'assistant',
              content: streamingContent,
              created_at: new Date().toISOString(),
            }}
            isStreaming
          />
        </motion.div>
      )}

      {/* Typing Indicator */}
      {isStreaming && !streamingContent && toolCalls.length === 0 && !reasoningContent && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="py-6 bg-neutral-50 dark:bg-neutral-800/50"
        >
          <div className="max-w-3xl mx-auto px-4">
            <div className="text-xs font-medium text-neutral-400 mb-2">
              LAMBDA
            </div>
            <div className="flex items-center gap-1 text-neutral-400">
              <span className="w-2 h-2 bg-neutral-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-2 h-2 bg-neutral-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-2 h-2 bg-neutral-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        </motion.div>
      )}

      <div ref={messagesEndRef} />
    </div>
  )
}
