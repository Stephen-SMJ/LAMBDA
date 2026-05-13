import { useEffect, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, MessageSquare, Shield } from 'lucide-react'
import toast from 'react-hot-toast'
import { api } from '../services/api'
import { useAuthStore } from '../store/authStore'

interface AdminMessage {
  id: number
  role: string
  content: string
  tool_calls?: string | null
  created_at: string
}

interface AdminConversationDetail {
  hash_id: string
  title: string
  model: string
  created_at: string
  updated_at: string
  estimated_tokens: number
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
  reasoning_tokens: number
  usage_record_count: number
  owner?: {
    id: number
    email: string
    full_name: string | null
    display_name: string | null
  } | null
  messages: AdminMessage[]
}

const formatDate = (value?: string | null) => {
  if (!value) return 'Never'
  return new Date(value).toLocaleString()
}

const formatNumber = (value: number) => new Intl.NumberFormat().format(value || 0)

export default function AdminConversationPage() {
  const { conversationId } = useParams<{ conversationId: string }>()
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const [conversation, setConversation] = useState<AdminConversationDetail | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!user?.is_admin || !conversationId) return
    setLoading(true)
    api.get(`/admin/conversations/${conversationId}`)
      .then((response) => setConversation(response.data))
      .catch((error) => {
        toast.error(error.response?.data?.detail || 'Failed to load conversation')
      })
      .finally(() => setLoading(false))
  }, [conversationId, user?.is_admin])

  if (!user?.is_admin) {
    return <Navigate to="/" replace />
  }

  return (
    <div className="min-h-screen bg-[#f6f5f1] text-neutral-950">
      <header className="sticky top-0 z-10 border-b border-black/5 bg-white/85 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/admin')}
              className="rounded-xl border border-neutral-200 bg-white p-2 text-neutral-600 shadow-sm hover:bg-neutral-50"
              title="Back to admin"
            >
              <ArrowLeft className="h-5 w-5" />
            </button>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-neutral-400">Conversation Viewer</p>
              <h1 className="text-xl font-semibold">{conversation?.title || 'Chat History'}</h1>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-full bg-neutral-950 px-4 py-2 text-sm font-medium text-white">
            <Shield className="h-4 w-4" />
            Admin
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-5 py-6">
        {loading ? (
          <div className="rounded-3xl border border-black/5 bg-white p-8 text-sm text-neutral-500 shadow-sm">
            Loading conversation...
          </div>
        ) : conversation ? (
          <div className="space-y-5">
            <section className="rounded-3xl border border-black/5 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-sm text-neutral-500">
                    {conversation.owner?.email || 'Unknown user'} · {conversation.model}
                  </p>
                  <h2 className="mt-1 text-2xl font-semibold">{conversation.title || 'Untitled conversation'}</h2>
                  <p className="mt-1 text-sm text-neutral-500">
                    Created {formatDate(conversation.created_at)} · Updated {formatDate(conversation.updated_at)}
                  </p>
                </div>
                <button
                  onClick={() => navigate(`/chat/${conversation.hash_id}`)}
                  className="rounded-2xl bg-neutral-950 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800"
                >
                  Open Chat
                </button>
              </div>

              <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-5">
                <Metric label="Messages" value={conversation.messages.length} />
                <Metric label="Tokens" value={conversation.total_tokens || conversation.estimated_tokens} />
                <Metric label="Prompt" value={conversation.prompt_tokens} />
                <Metric label="Completion" value={conversation.completion_tokens} />
                <Metric label="Usage records" value={conversation.usage_record_count} />
              </div>
            </section>

            <section className="space-y-4">
              {conversation.messages.map((message) => (
                <article key={message.id} className="rounded-3xl border border-black/5 bg-white p-5 shadow-sm">
                  <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-neutral-950 px-3 py-1 text-xs font-semibold capitalize text-white">
                        {message.role}
                      </span>
                      <span className="text-xs text-neutral-400">#{message.id}</span>
                    </div>
                    <span className="text-xs text-neutral-400">{formatDate(message.created_at)}</span>
                  </div>
                  <pre className="whitespace-pre-wrap break-words rounded-2xl bg-neutral-50 p-4 text-sm leading-6 text-neutral-800">
                    {message.content || '(empty)'}
                  </pre>
                  {message.tool_calls && (
                    <details className="mt-3 rounded-2xl border border-neutral-100 bg-neutral-50">
                      <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-neutral-700">
                        Tool calls
                      </summary>
                      <pre className="max-h-[480px] overflow-auto border-t border-neutral-100 p-4 text-xs leading-5 text-neutral-700">
                        {message.tool_calls}
                      </pre>
                    </details>
                  )}
                </article>
              ))}
            </section>
          </div>
        ) : (
          <div className="rounded-3xl border border-black/5 bg-white p-8 text-sm text-neutral-500 shadow-sm">
            Conversation not found.
          </div>
        )}
      </main>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl bg-neutral-50 p-3">
      <div className="flex items-center gap-2 text-neutral-500">
        <MessageSquare className="h-4 w-4" />
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <p className="mt-2 text-xl font-semibold">{formatNumber(value)}</p>
    </div>
  )
}
