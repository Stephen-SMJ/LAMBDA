import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'

// AnimatePresence removed
import { api, streamChat, createConversation, uploadFile } from '../services/api'
import { useSettingsStore } from '../store/settingsStore'
import Sidebar from '../components/layout/Sidebar'
import RightPanel from '../components/layout/RightPanel'
import ChatInput from '../components/chat/ChatInput'
import MessageList from '../components/chat/MessageList'
import WelcomeScreen from '../components/chat/WelcomeScreen'
import SettingsModal from '../components/settings/SettingsModal'
import toast from 'react-hot-toast'
import type { Conversation, Message, ChatStreamData, ToolResult, User } from '../types'
import { useI18n } from '../i18n'
import { Menu } from 'lucide-react'

export interface ToolCallInfo {
  id: string
  name: string
  arguments: string
  result?: ToolResult
  status: 'pending' | 'running' | 'completed' | 'error'
  step?: number
}

interface Model {
  id: string
  name: string
  multimodal?: boolean
}

const dedupeGeneratedFiles = (files: any[] = []) => {
  const seen = new Set<string>()
  return files.filter((file) => {
    const key = file.url || file.proxy_url || file.oss_url || `${file.type || 'file'}:${file.filename || file.name}`
    if (!key || seen.has(key)) return false
    seen.add(key)
    return true
  })
}

export default function ChatPage() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const navigate = useNavigate()
  const { isSettingsOpen, openSettings, closeSettings } = useSettingsStore()
  const { t, language } = useI18n()
  const queryClient = useQueryClient()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const streamAbortRef = useRef<AbortController | null>(null)
  const stopRequestedRef = useRef(false)
  const currentStreamRef = useRef('')
  const currentConversationIdRef = useRef<string | null>(conversationId || null)
  const activeStreamConversationRef = useRef<string | null>(null)
  const activeStreamContentRef = useRef('')
  const activeStreamReasoningRef = useRef('')
  const activeStreamToolCallsRef = useRef<ToolCallInfo[]>([])
  const activeStreamStepRef = useRef(0)
  const activeStreamUserMessageRef = useRef<Message | null>(null)
  const activeStreamBaseMessagesRef = useRef<Message[]>([])

  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [activeStreamConversationId, setActiveStreamConversationId] = useState<string | null>(null)
  const [currentStream, setCurrentStream] = useState('')
  // Mobile detection: sidebar closed by default on mobile (<768px)
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth >= 768)
  const [rightPanelOpen, setRightPanelOpen] = useState(false)
  
  // Handle window resize for responsive sidebar
  useEffect(() => {
    const handleResize = () => {
      const isDesktop = window.innerWidth >= 768
      // Only auto-toggle sidebar on resize, don't force if user manually toggled
      if (!conversationId) {
        setSidebarOpen(isDesktop)
      }
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [conversationId])
  
  // Auto-open right panel on desktop when conversation has messages
  useEffect(() => {
    const isDesktop = window.innerWidth >= 768
    if (isDesktop && conversationId && messages.length > 0 && !rightPanelOpen) {
      setRightPanelOpen(true)
    }
  }, [conversationId, messages.length])
  const [toolCalls, setToolCalls] = useState<ToolCallInfo[]>([])
  const [currentStep, setCurrentStep] = useState(0)
  const [selectedModel, setSelectedModel] = useState<string>('')
  const selectedModelRef = useRef('')
  const [reasoningContent, setReasoningContent] = useState('')
  const [isPending, setIsPending] = useState<boolean>(false)
  const isPendingRef = useRef(false)
  const [pendingStatus, setPendingStatus] = useState<string>(t('initializingConversation'))
  const [modelFromPending, setModelFromPending] = useState<boolean>(false)  // Flag to prevent overwriting model from currentConversation
  const localUser: User = {
    id: 1,
    email: 'local@lambda.local',
    full_name: 'Local User',
    is_active: true,
    is_admin: false,
    created_at: new Date(0).toISOString(),
  }

  useEffect(() => {
    document.documentElement.classList.add('lambda-chat-lock')
    window.scrollTo(0, 0)

    const keepDocumentPinned = () => {
      if (window.scrollX !== 0 || window.scrollY !== 0) {
        window.scrollTo(0, 0)
      }
    }

    window.addEventListener('scroll', keepDocumentPinned, { passive: true })
    return () => {
      window.removeEventListener('scroll', keepDocumentPinned)
      document.documentElement.classList.remove('lambda-chat-lock')
    }
  }, [])

  const updatePending = (value: boolean) => {
    isPendingRef.current = value
    setIsPending(value)
  }

  useEffect(() => {
    currentConversationIdRef.current = conversationId || null
  }, [conversationId])
  
  // Check for pending message when conversationId changes
  useEffect(() => {
    if (!conversationId) {
      updatePending(false)
      setPendingStatus(t('initializingConversation'))
      return
    }
    const pending = sessionStorage.getItem('pendingMessage')
    if (pending) {
      try {
        const { conversationId: pendingConvId, model: pendingModel } = JSON.parse(pending)
        if (String(pendingConvId) === String(conversationId)) {
          updatePending(true)
          setPendingStatus(t('initializingConversation'))
          // Restore selected model from pending message and set flag
          if (pendingModel) {
            selectedModelRef.current = pendingModel
            setSelectedModel(pendingModel)
            setModelFromPending(true)  // Mark that we got model from pending
          }
        } else {
          updatePending(false)
          setPendingStatus(t('initializingConversation'))
          setModelFromPending(false)
        }
      } catch {
        updatePending(false)
        setPendingStatus(t('initializingConversation'))
      }
    } else {
      updatePending(false)
      setPendingStatus(t('initializingConversation'))
    }
  }, [conversationId])

  // Fetch available models
  const { data: modelsData } = useQuery<{ models: Model[], default: string }>({
    queryKey: ['models'],
    queryFn: async () => {
      const response = await api.get('/chat/models')
      return response.data
    },
  })

  // Fetch conversation details if we have an ID
  const { data: currentConversation } = useQuery<Conversation>({
    queryKey: ['conversation', conversationId],
    queryFn: async () => {
      if (!conversationId) return null as any
      const response = await api.get(`/conversations/${conversationId}`)
      return response.data
    },
    enabled: !!conversationId,
    staleTime: 0,
    refetchOnMount: true,
  })

  // Set selected model from conversation or default
  // Skip if we just restored model from pendingMessage (new conversation flow)
  useEffect(() => {
    if (modelFromPending) {
      // Clear the flag after this effect runs once
      setModelFromPending(false)
      return
    }
    if (currentConversation?.model) {
      selectedModelRef.current = currentConversation.model
      setSelectedModel(currentConversation.model)
    } else if (modelsData?.default && !selectedModel) {
      selectedModelRef.current = modelsData.default
      setSelectedModel(modelsData.default)
    }
  }, [currentConversation?.model, modelsData])

  // Track which conversation we've already loaded to prevent duplicate loading
  const loadedConversationRef = useRef<string | null>(null)
  const previousConversationRef = useRef<string | null>(conversationId || null)

  // Reset view-local state immediately when switching conversations. Without
  // this, a target conversation with fewer messages can be masked by old state.
  useEffect(() => {
    const previousConversationId = previousConversationRef.current
    const nextConversationId = conversationId || null
    if (previousConversationId === nextConversationId) return

    previousConversationRef.current = nextConversationId
    loadedConversationRef.current = null
    setMessages([])
    setToolCalls([])
    setCurrentStream('')
    setReasoningContent('')
    setCurrentStep(0)
    if (activeStreamConversationRef.current === nextConversationId) {
      const userMessage = activeStreamUserMessageRef.current
      setMessages(userMessage ? [...activeStreamBaseMessagesRef.current, userMessage] : activeStreamBaseMessagesRef.current)
      setToolCalls([...activeStreamToolCallsRef.current])
      setCurrentStream(activeStreamContentRef.current)
      currentStreamRef.current = activeStreamContentRef.current
      setReasoningContent(activeStreamReasoningRef.current)
      setCurrentStep(activeStreamStepRef.current)
      setIsStreaming(true)
    } else {
      setIsStreaming(false)
    }
  }, [conversationId])
  
  // Update messages when conversation data changes
  // Skip if currently streaming to avoid overwriting live updates
  useEffect(() => {
    if (isStreaming && activeStreamConversationRef.current === conversationId) return
    
    if (currentConversation?.messages) {
      // Skip if we've already loaded this conversation to prevent duplicates on refresh
      if (loadedConversationRef.current === conversationId && messages.length > 0) {
        return
      }
      
      // For a newly selected conversation, always accept server data. For the
      // same conversation, avoid overwriting optimistic streaming completion.
      const serverMessageCount = currentConversation.messages.length
      const localMessageCount = messages.length
      const isNewConversationLoad = loadedConversationRef.current !== conversationId
      
      if (serverMessageCount === 0 && localMessageCount > 0) {
        loadedConversationRef.current = conversationId || null
        return
      }

      if (isNewConversationLoad || serverMessageCount >= localMessageCount) {
        setMessages(currentConversation.messages)
        loadedConversationRef.current = conversationId || null
        
        // Restore tool calls from the last assistant message
        const lastAssistantMessage = [...currentConversation.messages]
          .reverse()
          .find((m: Message) => m.role === 'assistant' && m.tool_calls)
        
        if (lastAssistantMessage?.tool_calls) {
          try {
            const parsedToolCalls = JSON.parse(lastAssistantMessage.tool_calls)
            const restoredToolCalls: ToolCallInfo[] = parsedToolCalls.map((tc: any, idx: number) => ({
              id: tc.id || `restored_${idx}`,
              name: tc.function?.name || 'unknown',
              arguments: tc.function?.arguments || '{}',
              status: tc.status || (tc.result?.success === false || tc.result?.error || tc.error ? 'error' : 'completed'),
              step: idx,
              result: tc.result || null,
            }))
            setToolCalls(restoredToolCalls)
          } catch {
            setToolCalls([])
          }
        } else {
          setToolCalls([])
        }
      }
    } else if (!isStreaming && messages.length === 0) {
      setMessages([])
      setToolCalls([])
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentConversation, isStreaming])

  // Check for pending message to send (for new conversations)
  useEffect(() => {
    if (!conversationId || !isPending) return
    
    const pendingData = sessionStorage.getItem('pendingMessage')
    if (!pendingData) {
      updatePending(false)
      return
    }
    
    try {
      const { conversationId: pendingConvId, message, fileIds, fileNames, analysisMode } = JSON.parse(pendingData)
      
      // Only send if we're on the correct conversation
      if (String(pendingConvId) === String(conversationId)) {
        // Send the message with file names for display
        sendMessageToCurrentConversation(message, fileIds, fileNames, analysisMode).then((started) => {
          if (started !== false) {
            sessionStorage.removeItem('pendingMessage')
          } else {
            setActiveStreamConversationId(null)
          }
          updatePending(false)
        }).catch(() => {
          setActiveStreamConversationId(null)
          updatePending(false)
        })
      } else {
        updatePending(false)
      }
    } catch {
      sessionStorage.removeItem('pendingMessage')
      updatePending(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, isPending])

  // Helper function to send message to current conversation
  const sendMessageToCurrentConversation = async (content: string, fileIds?: number[], fileNames?: string[], analysisMode?: string) => {
    const activeTaskConversationId = activeStreamConversationRef.current || (streamAbortRef.current ? activeStreamConversationId : null)
    if (
      (!content.trim() && (!fileIds || fileIds.length === 0)) ||
      (activeTaskConversationId && activeTaskConversationId !== conversationId) ||
      !!streamAbortRef.current ||
      !conversationId
    ) {
      return false
    }
    const streamConversationId = conversationId
    const isActiveConversation = () => currentConversationIdRef.current === streamConversationId
    loadedConversationRef.current = conversationId
    stopRequestedRef.current = false
    const abortController = new AbortController()
    streamAbortRef.current = abortController
    activeStreamConversationRef.current = streamConversationId
    setActiveStreamConversationId(streamConversationId)
    
    // Build message content with file attachments
    let messageContent = content || (analysisMode === 'autonomous_exploration' ? t('autonomousExplorationMode') : '')
    if (fileNames && fileNames.length > 0) {
      messageContent += `\n\n📎 **Attached ${fileNames.length} file(s):** ${fileNames.join(', ')}`
    }
    
    // Add user message immediately
    const userMessage: Message = {
      id: Date.now(),
      conversation_id: currentConversation?.id || 0,
      role: 'user',
      content: messageContent,
      created_at: new Date().toISOString(),
    }
    activeStreamUserMessageRef.current = userMessage
    activeStreamBaseMessagesRef.current = messages
    activeStreamContentRef.current = ''
    activeStreamReasoningRef.current = ''
    activeStreamToolCallsRef.current = []
    activeStreamStepRef.current = 0
    if (isActiveConversation()) {
      setMessages((prev) => [...prev, userMessage])
      setIsStreaming(true)
      setCurrentStream('')
      currentStreamRef.current = ''
      setToolCalls([])
      setCurrentStep(0)
      setReasoningContent('')
    }

    let streamContent = ''
    let currentReasoning = ''
    const allToolCalls: ToolCallInfo[] = []

    await streamChat(
      content,
      conversationId,
      selectedModelRef.current || selectedModel || undefined,
      fileIds && fileIds.length > 0 ? fileIds : undefined,
      analysisMode,
      language,
      (data: ChatStreamData) => {
        if (data.type === 'delta') {
          if (isPendingRef.current) updatePending(false)
          streamContent += data.content || ''
          activeStreamContentRef.current = streamContent
          if (isActiveConversation()) {
            currentStreamRef.current = streamContent
            setCurrentStream(streamContent)
          }
        } else if (data.type === 'status') {
          // Keep new-conversation setup status on the initializing screen.
          // Existing conversations still show status inline in the message area.
          activeStreamContentRef.current = data.content || ''
          if (!isActiveConversation()) {
            return
          }
          if (isPendingRef.current) {
            setPendingStatus(data.content || 'Preparing workspace...')
          } else {
            setCurrentStream(data.content || '')
          }
        } else if (data.type === 'keepalive') {
          // Keepalive message - connection is still alive, no UI update needed
          console.log('Keepalive received:', data.timestamp)
        } else if (data.type === 'reasoning') {
          if (isPendingRef.current) updatePending(false)
          currentReasoning += data.content || ''
          activeStreamReasoningRef.current = currentReasoning
          if (isActiveConversation()) {
            setReasoningContent(currentReasoning)
          }
        } else if (data.type === 'tool_call') {
          if (isPendingRef.current) updatePending(false)
          const toolCall: ToolCallInfo = {
            id: data.tool_call?.id || '',
            name: data.tool_call?.function?.name || '',
            arguments: data.tool_call?.function?.arguments || '',
            status: 'pending',
            step: data.step || currentStep,
          }
          allToolCalls.push(toolCall)
          activeStreamToolCallsRef.current = [...allToolCalls]
          activeStreamStepRef.current = data.step || currentStep
          if (isActiveConversation()) {
            setToolCalls(prev => [...prev, toolCall])
            setCurrentStep(data.step || currentStep)
          }
        } else if (data.type === 'tool_result') {
          if (isPendingRef.current) updatePending(false)
          const resultStatus = data.result?.success ? 'completed' : 'error'
          const allIdx = data.tool_call_id
            ? allToolCalls.findIndex((tc) => tc.id === data.tool_call_id)
            : allToolCalls.findIndex((tc) => tc.status === 'pending' && tc.name === data.tool_name)
          const fallbackIdx = allIdx >= 0 ? allIdx : allToolCalls.findIndex((tc) => tc.status === 'pending')
          if (fallbackIdx >= 0) {
            allToolCalls[fallbackIdx].result = data.result
            allToolCalls[fallbackIdx].status = resultStatus
            activeStreamToolCallsRef.current = [...allToolCalls]
            if (isActiveConversation()) {
              setToolCalls(prev => {
                const updated = [...prev]
                const updateIdx = data.tool_call_id
                  ? updated.findIndex((tc) => tc.id === data.tool_call_id)
                  : updated.findIndex((tc) => tc.status === 'pending' && tc.name === data.tool_name)
                const resolvedIdx = updateIdx >= 0 ? updateIdx : updated.findIndex((tc) => tc.status === 'pending')
                if (resolvedIdx >= 0) {
                  updated[resolvedIdx] = {
                    ...updated[resolvedIdx],
                    result: data.result,
                    status: resultStatus
                  }
                }
                return updated
              })
            }
          }
          if (isActiveConversation()) {
            setCurrentStep(data.step || currentStep)
          }
          activeStreamStepRef.current = data.step || currentStep
        } else if (data.type === 'done') {
          if (isActiveConversation() && isPendingRef.current) updatePending(false)
          loadedConversationRef.current = conversationId || null
          // Build final message
          let finalContent = streamContent || 'Task completed'
          
          // Add tool execution summary with collapsible markers
          if (allToolCalls.length > 0) {
            finalContent += '\n\n<!--COLLAPSIBLE:Analyze details-->\n'
            allToolCalls.forEach((tc) => {
              finalContent += `\n**${tc.name}**\n`
              try {
                const args = JSON.parse(tc.arguments)
                if (args.code) {
                  finalContent += '```python\n' + args.code + '\n```\n'
                } else if (args.command) {
                  finalContent += '```bash\n' + args.command + '\n```\n'
                }
              } catch {
                finalContent += '```\n' + tc.arguments + '\n```\n'
              }
              if (tc.result) {
                const output = tc.result.output || tc.result.stdout
                if (output) {
                  finalContent += '**Output:**\n```\n' + output + '\n```\n'
                }
                if (tc.result.content_preview) {
                  finalContent += '**Written Content Preview:**\n```markdown\n' + tc.result.content_preview + '\n```\n'
                }
                if (!output && tc.result.stderr) {
                  finalContent += '**Error:**\n```\n' + tc.result.stderr + '\n```\n'
                }
                // NOTE: Images are NOT included here - they are shown in file viewer
              }
            })
            finalContent += '\n<!--END_COLLAPSIBLE-->'
          }
          
          // Add generated files from done event
          if (data.generated_files && data.generated_files.length > 0) {
            const fileListData = JSON.stringify(dedupeGeneratedFiles(data.generated_files).map((f: any) => ({
              name: f.filename || f.name,
              url: f.url || f.proxy_url || f.oss_url,
              type: f.type || 'file'
            })))
            finalContent += `\n\n<!--FILES:${fileListData}-->`
          }

          const completedToolCalls = allToolCalls.map((tc) => ({
            id: tc.id,
            type: 'function',
            function: {
              name: tc.name,
              arguments: tc.arguments,
            },
            result: tc.result || null,
          }))
          
          const finalMessage: Message = {
            id: Date.now() + 1,
            conversation_id: currentConversation?.id || 0,
            role: 'assistant',
            content: finalContent,
            tool_calls: completedToolCalls.length > 0 ? JSON.stringify(completedToolCalls) : undefined,
            created_at: new Date().toISOString(),
          }
          if (isActiveConversation()) {
            setMessages((prev) => [...prev, finalMessage])
            setCurrentStream('')
            currentStreamRef.current = ''
            setReasoningContent('')
            setIsStreaming(false)
            streamAbortRef.current = null
          }
          if (activeStreamConversationRef.current === streamConversationId) {
            activeStreamConversationRef.current = null
            setActiveStreamConversationId(null)
            activeStreamContentRef.current = ''
            activeStreamReasoningRef.current = ''
            activeStreamToolCallsRef.current = []
            activeStreamStepRef.current = 0
            activeStreamUserMessageRef.current = null
            activeStreamBaseMessagesRef.current = []
            setIsStreaming(false)
            streamAbortRef.current = null
          }
          stopRequestedRef.current = false
          if (isActiveConversation()) {
            setPendingStatus(t('initializingConversation'))
            setCurrentStep(0)
          }
          
          queryClient.invalidateQueries({ queryKey: ['conversations'] })
          queryClient.invalidateQueries({ queryKey: ['conversation', streamConversationId] })
        } else if (data.type === 'error') {
          if (isActiveConversation()) {
            toast.error(data.content || 'An error occurred')
            setIsStreaming(false)
            streamAbortRef.current = null
          }
          if (activeStreamConversationRef.current === streamConversationId) {
            activeStreamConversationRef.current = null
            setActiveStreamConversationId(null)
            activeStreamContentRef.current = ''
            activeStreamReasoningRef.current = ''
            activeStreamToolCallsRef.current = []
            activeStreamStepRef.current = 0
            activeStreamUserMessageRef.current = null
            activeStreamBaseMessagesRef.current = []
            setIsStreaming(false)
            streamAbortRef.current = null
          }
          stopRequestedRef.current = false
          if (isActiveConversation()) {
            updatePending(false)
            setPendingStatus(t('initializingConversation'))
            setCurrentStep(0)
            setReasoningContent('')
          }
        }
      },
      (error) => {
        if (error?.name === 'AbortError' || stopRequestedRef.current) {
          return
        }
        if (!isActiveConversation()) {
          queryClient.invalidateQueries({ queryKey: ['conversation', streamConversationId] })
          queryClient.invalidateQueries({ queryKey: ['conversations'] })
          if (activeStreamConversationRef.current === streamConversationId) {
            activeStreamConversationRef.current = null
            setActiveStreamConversationId(null)
            activeStreamContentRef.current = ''
            activeStreamReasoningRef.current = ''
            activeStreamToolCallsRef.current = []
            activeStreamStepRef.current = 0
            activeStreamUserMessageRef.current = null
            activeStreamBaseMessagesRef.current = []
            setIsStreaming(false)
            streamAbortRef.current = null
          }
          return
        }
        console.error('Stream error:', error)
        const errorMessage = error instanceof Error ? error.message : 'Failed to get response'
        toast.error(errorMessage)
        const failedMessage: Message = {
          id: Date.now() + 1,
          conversation_id: currentConversation?.id || 0,
          role: 'assistant',
          content: `The response stream ended unexpectedly: ${errorMessage}`,
          created_at: new Date().toISOString(),
        }
        setMessages((prev) => [...prev, failedMessage])
        setIsStreaming(false)
        if (activeStreamConversationRef.current === streamConversationId) {
          activeStreamConversationRef.current = null
          setActiveStreamConversationId(null)
          activeStreamContentRef.current = ''
          activeStreamReasoningRef.current = ''
          activeStreamToolCallsRef.current = []
          activeStreamStepRef.current = 0
          activeStreamUserMessageRef.current = null
          activeStreamBaseMessagesRef.current = []
        }
        streamAbortRef.current = null
        stopRequestedRef.current = false
        updatePending(false)
        setPendingStatus(t('initializingConversation'))
        setCurrentStep(0)
        setReasoningContent('')
        queryClient.invalidateQueries({ queryKey: ['conversation', conversationId] })
        queryClient.invalidateQueries({ queryKey: ['conversations'] })
      },
      abortController.signal
    )
    // streamChat reports errors through its callback and then resolves. If the
    // browser closes the stream without a final done/error event, clear any
    // stale local active-task state so New Chat is not blocked until refresh.
    if (activeStreamConversationRef.current === streamConversationId && streamAbortRef.current === abortController) {
      activeStreamConversationRef.current = null
      setActiveStreamConversationId(null)
      activeStreamContentRef.current = ''
      activeStreamReasoningRef.current = ''
      activeStreamToolCallsRef.current = []
      activeStreamStepRef.current = 0
      activeStreamUserMessageRef.current = null
      activeStreamBaseMessagesRef.current = []
      streamAbortRef.current = null
      stopRequestedRef.current = false
      updatePending(false)
      setIsStreaming(false)
      setPendingStatus(t('initializingConversation'))
    }
    return true
  }

  const handleStopGeneration = async () => {
    if (!isStreaming) return

    stopRequestedRef.current = true
    streamAbortRef.current?.abort()
    streamAbortRef.current = null

    const partialContent = currentStreamRef.current.trim()
    if (partialContent) {
      const stoppedMessage: Message = {
        id: Date.now() + 1,
        conversation_id: currentConversation?.id || 0,
        role: 'assistant',
        content: `${partialContent}\n\n_Generation stopped by user._`,
        created_at: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, stoppedMessage])
    }

    setCurrentStream('')
    currentStreamRef.current = ''
    setReasoningContent('')
    setToolCalls((prev) => prev.map((tc) => (
      tc.status === 'pending' || tc.status === 'running'
        ? {
            ...tc,
            status: 'error',
            result: {
              success: false,
              output: 'Stopped by user',
              error: 'Stopped by user'
            }
          }
        : tc
    )))
    setIsStreaming(false)
    if (activeStreamConversationRef.current === conversationId) {
      activeStreamConversationRef.current = null
      setActiveStreamConversationId(null)
      activeStreamContentRef.current = ''
      activeStreamReasoningRef.current = ''
      activeStreamToolCallsRef.current = []
      activeStreamStepRef.current = 0
      activeStreamUserMessageRef.current = null
      activeStreamBaseMessagesRef.current = []
    }
    updatePending(false)
    setPendingStatus(t('initializingConversation'))
    setCurrentStep(0)

    if (conversationId) {
      try {
        await api.post(`/chat/cancel/${conversationId}`)
      } catch (error) {
        console.error('Failed to cancel sandbox execution:', error)
      }
    }

    toast.success('Execution stopped')
  }

  const handleSendMessage = async (content: string, files?: File[], analysisMode?: string) => {
    if (!content.trim() && (!files || files.length === 0)) return false

    const activeTaskConversationId = activeStreamConversationRef.current || (streamAbortRef.current ? activeStreamConversationId : null)
    if (isPending || activeTaskConversationId || streamAbortRef.current) {
      toast.error(t('activeTaskWait'))
      if (activeTaskConversationId && activeTaskConversationId !== conversationId) {
        navigate(`/chat/${activeTaskConversationId}`)
      }
      return false
    }

    // If new conversation, create it first
    if (!conversationId) {
      try {
        const modelToUse = selectedModelRef.current || selectedModel || modelsData?.default
        updatePending(true)
        setPendingStatus(t('initializingConversation'))
        const title = content.trim() || (analysisMode === 'autonomous_exploration' ? t('autonomousDataExploration') : t('newChatTitle'))
        const conv = await createConversation(title.slice(0, 50), modelToUse || undefined)
        setActiveStreamConversationId(conv.hash_id)
        
        // Upload files if any
        let fileIds: number[] = []
        if (files && files.length > 0) {
          setPendingStatus(t('uploadingFiles', { count: files.length, plural: files.length === 1 ? '' : 's' }))
          const uploadResults = await Promise.all(
            files.map(file => uploadFile(file, conv.hash_id))
          )
          fileIds = uploadResults.map(r => r.id)
        }
        
        // Store pending message for the new page to pick up
        sessionStorage.setItem('pendingMessage', JSON.stringify({
          conversationId: conv.hash_id,
          message: content,
          fileIds: fileIds,
          fileNames: files ? files.map(f => f.name) : [],
          model: modelToUse,
          analysisMode
        }))
        
        // Navigate immediately - the new page will show loading state
        navigate(`/chat/${conv.hash_id}`, { replace: true })
        queryClient.invalidateQueries({ queryKey: ['conversations'] })
        return true
      } catch (error: any) {
        updatePending(false)
        setActiveStreamConversationId(null)
        setPendingStatus(t('initializingConversation'))
        toast.error(`Failed to create conversation: ${error.message}`)
        return false
      }
    }

    // Existing conversation - upload files if any, then send message
    try {
      let fileIds: number[] = []
      if (files && files.length > 0) {
        const uploadResults = await Promise.all(
          files.map(file => uploadFile(file, conversationId))
        )
        fileIds = uploadResults.map(r => r.id)
      }
      await sendMessageToCurrentConversation(content, fileIds, files ? files.map(f => f.name) : [], analysisMode)
      return true
    } catch (error: any) {
      toast.error(`Failed to upload files: ${error.message}`)
      return false
    }
  }

  const handleNewChat = () => {
    const activeTaskConversationId = activeStreamConversationRef.current || (streamAbortRef.current ? activeStreamConversationId : null)
    if (isPending || activeTaskConversationId || streamAbortRef.current) {
      toast.error(t('activeTaskWait'))
      return
    }
    navigate('/')
    setMessages([])
    setToolCalls([])
    setCurrentStep(0)
    setRightPanelOpen(false)
  }

  const handleSelectConversation = (hashId: string) => {
    navigate(`/chat/${hashId}`)
  }

  const handleDeleteConversation = async (hashId: string) => {
    try {
      await api.delete(`/conversations/${hashId}`)
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      if (conversationId === hashId) {
        navigate('/')
        setMessages([])
      }
      toast.success('Conversation deleted')
    } catch {
      toast.error('Failed to delete conversation')
    }
  }

  const viewingActiveStream = !!conversationId && activeStreamConversationRef.current === conversationId
  const displayedMessages = viewingActiveStream && activeStreamUserMessageRef.current
    ? [...activeStreamBaseMessagesRef.current, activeStreamUserMessageRef.current]
    : messages
  const displayedCurrentStream = viewingActiveStream ? activeStreamContentRef.current : currentStream
  const displayedToolCalls = viewingActiveStream ? activeStreamToolCallsRef.current : toolCalls
  const displayedReasoningContent = viewingActiveStream ? activeStreamReasoningRef.current : reasoningContent
  const displayedIsStreaming = viewingActiveStream || isStreaming
  const showWelcomeScreen = !isPending && displayedMessages.length === 0 && !displayedCurrentStream

  return (
    <div className="fixed inset-0 flex h-[100dvh] max-h-[100dvh] bg-white dark:bg-neutral-900 overflow-hidden overscroll-none [overflow-anchor:none]">
      {/* Sidebar */}
      <Sidebar
        currentConversationId={conversationId || null}
        activeConversationId={activeStreamConversationId}
        onSelectConversation={handleSelectConversation}
        onNewChat={handleNewChat}
        onDeleteConversation={handleDeleteConversation}
        user={localUser}
        onOpenSettings={openSettings}
        isOpen={sidebarOpen}
        onOpenChange={setSidebarOpen}
      />

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0 min-h-0 h-full max-h-full overflow-hidden [overflow-anchor:none]">
        {/* Header */}
        <header className="h-14 border-b border-neutral-200 dark:border-neutral-800 flex items-center justify-between px-4 bg-white dark:bg-neutral-900">
          <div className="flex items-center gap-3">
            {!sidebarOpen && (
              <button
                onClick={() => setSidebarOpen(true)}
                className="group -ml-1 flex h-9 w-9 items-center justify-center rounded-xl border border-neutral-200 bg-white shadow-sm transition-colors hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900 dark:hover:bg-neutral-800 md:border-0 md:bg-transparent md:shadow-none"
                title={t('expandSidebar')}
                aria-label={t('expandSidebar')}
              >
                <Menu className="h-5 w-5 text-neutral-500 transition-colors group-hover:text-neutral-800 dark:text-neutral-400 dark:group-hover:text-neutral-100" />
              </button>
            )}
            <img 
              src="/LAMBDA_logo.gif" 
              alt="LAMBDA" 
              className="w-8 h-8 object-contain rounded-lg"
            />
            <h1 className="font-semibold text-neutral-900 dark:text-neutral-100 truncate">
              {currentConversation?.title || t('newChatTitle')}
            </h1>
          </div>
          {!showWelcomeScreen && (
          <div className="flex items-center gap-2">
            {/* Model Selector */}
            <select
              value={selectedModel}
              onChange={(e) => {
                selectedModelRef.current = e.target.value
                setSelectedModel(e.target.value)
              }}
              disabled={displayedIsStreaming}
              className="text-xs bg-neutral-100 dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 px-2 py-1.5 rounded-lg border border-neutral-200 dark:border-neutral-700 focus:outline-none focus:ring-2 focus:ring-neutral-500 disabled:opacity-50"
            >
              {modelsData?.models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name}
                </option>
              ))}
            </select>
          </div>
          )}
        </header>

        {/* Chat Area */}
        <div className="flex-1 min-h-0 overflow-hidden">
          {isPending ? (
            // Loading state while initializing conversation
            <div className="h-full flex flex-col items-center justify-center px-4">
              <div className="flex flex-col items-center gap-4">
                <img 
                  src="/LAMBDA_logo.gif" 
                  alt="LAMBDA" 
                  className="w-[72px] h-[72px] object-contain rounded-2xl"
                />
                <span className="text-sm text-neutral-500">{pendingStatus}</span>
              </div>
            </div>
          ) : showWelcomeScreen ? (
            <WelcomeScreen
              onSendMessage={handleSendMessage}
              models={modelsData?.models || []}
              selectedModel={selectedModel}
              onModelChange={(model) => {
                selectedModelRef.current = model
                setSelectedModel(model)
              }}
            />
          ) : (
            <MessageList
              messages={displayedMessages}
              streamingContent={displayedCurrentStream}
              isStreaming={displayedIsStreaming}
              toolCalls={displayedToolCalls}
              messagesEndRef={messagesEndRef}
              reasoningContent={displayedReasoningContent}
            />
          )}
        </div>

        {/* Input Area */}
        {!showWelcomeScreen && (
        <div className="border-t border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 p-4">
          <ChatInput
            onSendMessage={handleSendMessage}
            disabled={displayedIsStreaming}
            isStreaming={displayedIsStreaming}
            onStop={handleStopGeneration}
            placeholder={displayedIsStreaming ? t('workingPlaceholder') : t('messagePlaceholder')}
            conversationId={conversationId}
          />
          <p className="text-center text-xs text-neutral-400 mt-2">
            {t('checkingNotice')}
          </p>
        </div>
        )}
      </div>

      {/* Right Panel */}
      <RightPanel
        isOpen={rightPanelOpen}
        onToggle={() => setRightPanelOpen(!rightPanelOpen)}
        toolCalls={displayedToolCalls}
        isStreaming={displayedIsStreaming}
        sessionId={currentConversation ? String(currentConversation.id) : undefined}
      />

      {/* Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={closeSettings}
      />
    </div>
  )
}
