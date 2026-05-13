import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Plus, MessageSquare, Trash2, Settings, ChevronLeft, ChevronRight, Bot, Loader2 } from 'lucide-react'
import { formatDistanceToNow, parseISO, addHours } from 'date-fns'
import { api } from '../../services/api'
import type { Conversation, User } from '../../types'
import { useI18n } from '../../i18n'

interface SidebarProps {
  currentConversationId: string | null
  activeConversationId?: string | null
  onSelectConversation: (hashId: string) => void
  onNewChat: () => void
  onDeleteConversation: (hashId: string) => void
  user: User | null
  onLogout?: () => void
  onOpenSettings: () => void
  isOpen?: boolean
  onOpenChange?: (isOpen: boolean) => void
}

export default function Sidebar({
  currentConversationId,
  activeConversationId = null,
  onSelectConversation,
  onNewChat,
  onDeleteConversation,
  user,
  onOpenSettings,
  isOpen = true,
  onOpenChange,
}: SidebarProps) {
  const [hoveredConversation, setHoveredConversation] = useState<number | null>(null)
  const [isCollapsed, setIsCollapsed] = useState(!isOpen)
  const { t } = useI18n()

  // Sync internal state with prop
  useEffect(() => {
    setIsCollapsed(!isOpen)
  }, [isOpen])

  const { data: conversations = [] } = useQuery<Conversation[]>({
    queryKey: ['conversations'],
    queryFn: async () => {
      const response = await api.get('/conversations')
      return response.data
    },
    staleTime: 30000, // Cache for 30 seconds
    refetchOnWindowFocus: false,
  })

  // Group conversations by date
  const groupedConversations = conversations.reduce((groups, conv) => {
    const date = addHours(parseISO(conv.updated_at), 8) // Convert UTC to local time (UTC+8)
    const now = new Date()
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24))
    
    let group = 'older'
    if (diffDays === 0) group = 'today'
    else if (diffDays === 1) group = 'yesterday'
    else if (diffDays <= 7) group = 'previous7Days'
    else if (diffDays <= 30) group = 'previous30Days'
    
    if (!groups[group]) groups[group] = []
    groups[group].push(conv)
    return groups
  }, {} as Record<string, Conversation[]>)

  const groupOrder = ['today', 'yesterday', 'previous7Days', 'previous30Days', 'older']

  const handleCollapse = () => {
    setIsCollapsed(true)
    onOpenChange?.(false)
  }

  const handleExpand = () => {
    setIsCollapsed(false)
    onOpenChange?.(true)
  }

  // Collapsed state - compact sidebar
  if (isCollapsed) {
    return (
      <div className="hidden h-full w-16 bg-white dark:bg-neutral-900 border-r border-neutral-100 dark:border-neutral-800 md:flex flex-col flex-shrink-0 shadow-[1px_0_0_rgba(0,0,0,0.02)]">
        <div className="p-3">
          <button
            onClick={handleExpand}
            className="w-full h-10 flex items-center justify-center hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-xl transition-colors"
            title={t('expandSidebar')}
          >
            <ChevronRight className="w-5 h-5 text-neutral-500" />
          </button>
        </div>
        <div className="flex-1 overflow-hidden" />
        <div className="p-3 border-t border-neutral-100 dark:border-neutral-800">
          <button
            onClick={onOpenSettings}
            className="w-full h-10 flex items-center justify-center hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-xl transition-colors text-neutral-600 dark:text-neutral-400"
            title={t('settings')}
          >
            <Settings className="w-5 h-5" />
          </button>
        </div>
      </div>
    )
  }

  // Expanded state - full sidebar
  return (
    <div className="fixed inset-0 z-[70] h-full w-full bg-white dark:bg-neutral-900 border-r border-neutral-100 dark:border-neutral-800 flex flex-col flex-shrink-0 shadow-[1px_0_0_rgba(0,0,0,0.02)] md:relative md:inset-auto md:z-auto md:w-72">
      {/* Header */}
      <div className="p-4 flex items-center justify-between">
        <button
          onClick={() => {
            onNewChat()
            if (window.innerWidth < 768) handleCollapse()
          }}
          className="flex-1 flex items-center gap-2 px-3.5 py-2.5 bg-white dark:bg-neutral-800 hover:bg-neutral-50 dark:hover:bg-neutral-700 border border-neutral-200 dark:border-neutral-700 rounded-2xl transition-colors text-sm font-medium text-neutral-800 dark:text-neutral-200 shadow-sm"
        >
          <Plus className="w-4 h-4" />
          {t('newChat')}
        </button>
        <button
          onClick={handleCollapse}
          className="ml-2 p-2 hover:bg-neutral-100 dark:hover:bg-neutral-800 rounded-xl transition-colors"
          title={t('collapseSidebar')}
        >
          <ChevronLeft className="w-4 h-4 text-neutral-500" />
        </button>
      </div>

      {/* Conversations List */}
      <div className="flex-1 overflow-y-auto px-2 py-2">
        {conversations.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <Bot className="w-12 h-12 text-neutral-300 mx-auto mb-3" />
            <p className="text-sm text-neutral-500">{t('noConversations')}</p>
            <p className="text-xs text-neutral-400 mt-1">{t('startNewChat')}</p>
          </div>
        ) : (
          groupOrder.map((group) => {
            const groupConversations = groupedConversations[group]
            if (!groupConversations?.length) return null

            return (
              <div key={group} className="mb-4">
                <h3 className="px-3 py-2 text-[11px] font-semibold text-neutral-400 uppercase tracking-[0.16em]">
                  {t(group as 'today' | 'yesterday' | 'previous7Days' | 'previous30Days' | 'older')}
                </h3>
                {groupConversations.map((conv) => {
                  const isRunning = activeConversationId === conv.hash_id
                  return (
                    <div
                      key={conv.id}
                      onClick={() => {
                        onSelectConversation(conv.hash_id)
                        if (window.innerWidth < 768) handleCollapse()
                      }}
                      onMouseEnter={() => setHoveredConversation(conv.id)}
                      onMouseLeave={() => setHoveredConversation(null)}
                      className={`group px-3 py-2.5 rounded-2xl cursor-pointer flex items-center gap-3 transition-all ${
                        currentConversationId === conv.hash_id
                          ? 'bg-neutral-100 dark:bg-neutral-800 shadow-sm'
                          : 'hover:bg-neutral-50 dark:hover:bg-neutral-800/50'
                      }`}
                    >
                      {isRunning ? (
                        <Loader2 className="w-4 h-4 text-blue-500 flex-shrink-0 animate-spin" />
                      ) : (
                        <MessageSquare className="w-4 h-4 text-neutral-300 flex-shrink-0" />
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-neutral-700 dark:text-neutral-300 truncate">
                          {conv.title}
                        </p>
                        <p className="text-xs text-neutral-400">
                          {isRunning ? t('runningTask') : formatDistanceToNow(addHours(parseISO(conv.updated_at), 8), { addSuffix: true })}
                        </p>
                      </div>
                      <AnimatePresence>
                        {hoveredConversation === conv.id && (
                          <motion.button
                            initial={{ opacity: 0, scale: 0.8 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.8 }}
                            onClick={(e) => {
                              e.stopPropagation()
                              onDeleteConversation(conv.hash_id)
                            }}
                            className="p-1 hover:bg-neutral-200 dark:hover:bg-neutral-700 rounded text-neutral-400 hover:text-red-500 transition-colors"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </motion.button>
                        )}
                      </AnimatePresence>
                    </div>
                  )
                })}
              </div>
            )
          })
        )}
      </div>

      {/* User Section */}
      <div className="p-4 border-t border-neutral-100 dark:border-neutral-800">
        <div className="flex items-center gap-3 px-2 py-2 rounded-2xl hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors">
          <div className="w-9 h-9 rounded-full bg-neutral-100 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 flex items-center justify-center text-sm font-semibold text-neutral-700 dark:text-neutral-200">
            {user?.full_name?.[0]?.toUpperCase() || user?.email[0].toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300 truncate">
              {user?.full_name || user?.email}
            </p>
            <p className="text-xs text-neutral-500 truncate">{user?.email}</p>
          </div>
          <button
            onClick={() => {
              onOpenSettings()
              if (window.innerWidth < 768) handleCollapse()
            }}
            className="p-2 hover:bg-neutral-100 dark:hover:bg-neutral-700 rounded-xl transition-colors text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200"
            title={t('settings')}
          >
            <Settings className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
