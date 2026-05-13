import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { ArrowLeft, FileText, MessageSquare, Search, Shield, Users } from 'lucide-react'
import toast from 'react-hot-toast'
import { api } from '../services/api'
import { useAuthStore } from '../store/authStore'

interface AdminUser {
  id: number
  email: string
  full_name: string | null
  display_name: string | null
  is_active: boolean
  is_admin: boolean
  plan: string | null
  invite_code: string | null
  admin_notes: string | null
  password_set: boolean
  created_at: string
  updated_at: string
  last_login_at: string | null
  last_chat_at: string | null
  conversation_count: number
  message_count: number
  uploaded_file_count: number
  estimated_tokens: number
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
  reasoning_tokens: number
  usage_record_count: number
}

interface AdminSummary {
  total_users: number
  active_users: number
  admin_users: number
  total_conversations: number
  total_messages: number
  total_files: number
  estimated_tokens: number
  total_tokens: number
  prompt_tokens: number
  completion_tokens: number
  reasoning_tokens: number
  usage_record_count: number
}

interface AdminConversation {
  id: number
  hash_id: string
  title: string
  model: string
  created_at: string
  updated_at: string
  message_count: number
  user_message_count: number
  assistant_message_count: number
  estimated_tokens: number
  total_tokens: number
  usage_record_count: number
}

interface Announcement {
  id: number
  title: string
  content: string
  is_active: boolean
  created_at: string
}

const formatDate = (value?: string | null) => {
  if (!value) return 'Never'
  return new Date(value).toLocaleString()
}

const formatNumber = (value: number) => new Intl.NumberFormat().format(value || 0)

export default function AdminPage() {
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const [summary, setSummary] = useState<AdminSummary | null>(null)
  const [users, setUsers] = useState<AdminUser[]>([])
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null)
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null)
  const [conversations, setConversations] = useState<AdminConversation[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [newPassword, setNewPassword] = useState('')
  const [resettingPassword, setResettingPassword] = useState(false)
  const [announcements, setAnnouncements] = useState<Announcement[]>([])
  const [announcementTitle, setAnnouncementTitle] = useState('')
  const [announcementContent, setAnnouncementContent] = useState('')
  const [publishingAnnouncement, setPublishingAnnouncement] = useState(false)

  const selectedDraft = useMemo(() => ({
    full_name: selectedUser?.full_name || '',
    display_name: selectedUser?.display_name || '',
    plan: selectedUser?.plan || '',
    admin_notes: selectedUser?.admin_notes || '',
    is_active: selectedUser?.is_active ?? true,
    is_admin: selectedUser?.is_admin ?? false,
  }), [selectedUser])

  const [draft, setDraft] = useState(selectedDraft)
  const isStrongPassword = (value: string) =>
    value.length >= 8 && /[A-Za-z]/.test(value) && /\d/.test(value)

  useEffect(() => {
    setDraft(selectedDraft)
  }, [selectedDraft])

  const loadUsers = async (query = search) => {
    setLoading(true)
    try {
      const [summaryRes, usersRes] = await Promise.all([
        api.get('/admin/summary'),
        api.get('/admin/users', { params: { search: query, limit: 100 } }),
      ])
      setSummary(summaryRes.data)
      setUsers(usersRes.data.users)
      if (!selectedUserId && usersRes.data.users.length > 0) {
        setSelectedUserId(usersRes.data.users[0].id)
      }
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to load admin data')
    } finally {
      setLoading(false)
    }
  }

  const loadAnnouncements = async () => {
    try {
      const response = await api.get('/announcements/admin')
      setAnnouncements(response.data.announcements || [])
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to load announcements')
    }
  }

  const loadUserDetail = async (userId: number) => {
    try {
      const [userRes, conversationsRes] = await Promise.all([
        api.get(`/admin/users/${userId}`),
        api.get(`/admin/users/${userId}/conversations`, { params: { limit: 100 } }),
      ])
      setSelectedUser(userRes.data)
      setConversations(conversationsRes.data)
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to load user detail')
    }
  }

  const saveUser = async () => {
    if (!selectedUser) return
    setSaving(true)
    try {
      await api.patch(`/admin/users/${selectedUser.id}`, draft)
      toast.success('User updated')
      await loadUserDetail(selectedUser.id)
      await loadUsers(search)
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to save user')
    } finally {
      setSaving(false)
    }
  }

  const resetUserPassword = async () => {
    if (!selectedUser) return
    if (!isStrongPassword(newPassword)) {
      toast.error('Password must be at least 8 characters and include both letters and numbers')
      return
    }
    setResettingPassword(true)
    try {
      await api.post(`/admin/users/${selectedUser.id}/reset-password`, {
        new_password: newPassword,
      })
      setNewPassword('')
      toast.success('Password reset')
      await loadUserDetail(selectedUser.id)
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to reset password')
    } finally {
      setResettingPassword(false)
    }
  }

  const publishAnnouncement = async () => {
    if (!announcementTitle.trim() || !announcementContent.trim()) {
      toast.error('Announcement title and content are required')
      return
    }
    setPublishingAnnouncement(true)
    try {
      await api.post('/announcements/admin', {
        title: announcementTitle,
        content: announcementContent,
        is_active: true,
      })
      setAnnouncementTitle('')
      setAnnouncementContent('')
      toast.success('Announcement published')
      await loadAnnouncements()
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to publish announcement')
    } finally {
      setPublishingAnnouncement(false)
    }
  }

  const toggleAnnouncement = async (announcement: Announcement) => {
    try {
      await api.patch(`/announcements/admin/${announcement.id}`, {
        title: announcement.title,
        content: announcement.content,
        is_active: !announcement.is_active,
      })
      await loadAnnouncements()
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to update announcement')
    }
  }

  useEffect(() => {
    if (!user?.is_admin) return
    void loadUsers('')
    void loadAnnouncements()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.is_admin])

  useEffect(() => {
    if (user?.is_admin && selectedUserId) void loadUserDetail(selectedUserId)
  }, [selectedUserId, user?.is_admin])

  if (!user?.is_admin) {
    return <Navigate to="/" replace />
  }

  return (
    <div className="min-h-screen bg-[#f6f5f1] text-neutral-950">
      <header className="sticky top-0 z-10 border-b border-black/5 bg-white/85 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/')}
              className="rounded-xl border border-neutral-200 bg-white p-2 text-neutral-600 shadow-sm hover:bg-neutral-50"
              title="Back to LAMBDA"
            >
              <ArrowLeft className="h-5 w-5" />
            </button>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-neutral-400">LAMBDA Admin</p>
              <h1 className="text-xl font-semibold">User Management</h1>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-full bg-neutral-950 px-4 py-2 text-sm font-medium text-white">
            <Shield className="h-4 w-4" />
            Admin
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-5 py-6">
        <section className="grid grid-cols-2 gap-3 md:grid-cols-6">
          {[
            ['Users', summary?.total_users || 0],
            ['Active', summary?.active_users || 0],
            ['Admins', summary?.admin_users || 0],
            ['Chats', summary?.total_conversations || 0],
            ['Messages', summary?.total_messages || 0],
            ['Tokens', summary?.total_tokens || summary?.estimated_tokens || 0],
          ].map(([label, value]) => (
            <div key={label} className="rounded-2xl border border-black/5 bg-white p-4 shadow-sm">
              <p className="text-xs font-medium uppercase tracking-wide text-neutral-400">{label}</p>
              <p className="mt-2 text-2xl font-semibold">{formatNumber(Number(value))}</p>
            </div>
          ))}
        </section>

        <section className="mt-5 grid gap-5 lg:grid-cols-[360px_1fr]">
          <div className="rounded-3xl border border-black/5 bg-white shadow-sm">
            <div className="border-b border-neutral-100 p-4">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') void loadUsers(search)
                  }}
                  placeholder="Search email, name, invite code..."
                  className="w-full rounded-2xl border border-neutral-200 bg-neutral-50 py-2.5 pl-9 pr-3 text-sm outline-none focus:border-neutral-400"
                />
              </div>
            </div>
            <div className="max-h-[72vh] overflow-auto p-2">
              {loading ? (
                <p className="p-4 text-sm text-neutral-500">Loading users...</p>
              ) : users.map((item) => (
                <button
                  key={item.id}
                  onClick={() => setSelectedUserId(item.id)}
                  className={`mb-1 w-full rounded-2xl p-3 text-left transition-colors ${
                    selectedUserId === item.id ? 'bg-neutral-950 text-white' : 'hover:bg-neutral-50'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-sm font-semibold">{item.display_name || item.full_name || item.email}</p>
                    <span className={`rounded-full px-2 py-0.5 text-[11px] ${item.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                      {item.is_active ? 'active' : 'inactive'}
                    </span>
                  </div>
                  <p className={`mt-1 truncate text-xs ${selectedUserId === item.id ? 'text-white/65' : 'text-neutral-500'}`}>{item.email}</p>
                  <div className={`mt-2 flex gap-3 text-xs ${selectedUserId === item.id ? 'text-white/70' : 'text-neutral-500'}`}>
                    <span>{item.conversation_count} chats</span>
                    <span>{formatNumber(item.total_tokens || item.estimated_tokens)} tokens</span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-5">
              <div className="rounded-3xl border border-black/5 bg-white p-5 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-neutral-400">Announcements</p>
                    <h2 className="mt-1 text-xl font-semibold">Publish notice</h2>
                  </div>
                  <button
                    onClick={publishAnnouncement}
                    disabled={publishingAnnouncement}
                    className="rounded-2xl bg-neutral-950 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                  >
                    {publishingAnnouncement ? 'Publishing...' : 'Publish'}
                  </button>
                </div>
                <div className="mt-4 grid gap-3">
                  <input
                    value={announcementTitle}
                    onChange={(e) => setAnnouncementTitle(e.target.value)}
                    placeholder="Announcement title"
                    className="w-full rounded-xl border border-neutral-200 px-3 py-2 text-sm outline-none focus:border-neutral-400"
                  />
                  <textarea
                    value={announcementContent}
                    onChange={(e) => setAnnouncementContent(e.target.value)}
                    rows={4}
                    placeholder="Write the notice users should see after login..."
                    className="w-full rounded-xl border border-neutral-200 px-3 py-2 text-sm outline-none focus:border-neutral-400"
                  />
                </div>
                {announcements.length > 0 && (
                  <div className="mt-4 space-y-2">
                    {announcements.slice(0, 5).map((announcement) => (
                      <div key={announcement.id} className="rounded-2xl border border-neutral-100 bg-neutral-50 p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-neutral-900">{announcement.title}</p>
                            <p className="mt-1 line-clamp-2 text-xs text-neutral-500">{announcement.content}</p>
                          </div>
                          <button
                            onClick={() => toggleAnnouncement(announcement)}
                            className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium ${
                              announcement.is_active ? 'bg-emerald-100 text-emerald-700' : 'bg-neutral-200 text-neutral-600'
                            }`}
                          >
                            {announcement.is_active ? 'Active' : 'Inactive'}
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="rounded-3xl border border-black/5 bg-white p-5 shadow-sm">
                {selectedUser ? (
                  <>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-neutral-400">User profile</p>
                        <h2 className="mt-1 text-2xl font-semibold">{selectedUser.email}</h2>
                        <p className="text-sm text-neutral-500">Joined {formatDate(selectedUser.created_at)}</p>
                      </div>
                      <button
                        onClick={saveUser}
                        disabled={saving}
                        className="rounded-2xl bg-neutral-950 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                      >
                        {saving ? 'Saving...' : 'Save changes'}
                      </button>
                    </div>

                    <div className="mt-5 grid gap-3 md:grid-cols-2">
                      <label className="text-sm">
                        <span className="text-neutral-500">Full name</span>
                        <input value={draft.full_name} onChange={(e) => setDraft({ ...draft, full_name: e.target.value })} className="mt-1 w-full rounded-xl border border-neutral-200 px-3 py-2 outline-none focus:border-neutral-400" />
                      </label>
                      <label className="text-sm">
                        <span className="text-neutral-500">Display name</span>
                        <input value={draft.display_name} onChange={(e) => setDraft({ ...draft, display_name: e.target.value })} className="mt-1 w-full rounded-xl border border-neutral-200 px-3 py-2 outline-none focus:border-neutral-400" />
                      </label>
                      <label className="text-sm">
                        <span className="text-neutral-500">Plan</span>
                        <input value={draft.plan} onChange={(e) => setDraft({ ...draft, plan: e.target.value })} placeholder="empty for now" className="mt-1 w-full rounded-xl border border-neutral-200 px-3 py-2 outline-none focus:border-neutral-400" />
                      </label>
                      <div className="flex items-end gap-4">
                        <label className="flex items-center gap-2 text-sm">
                          <input type="checkbox" checked={draft.is_active} onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })} />
                          Active
                        </label>
                        <label className="flex items-center gap-2 text-sm">
                          <input type="checkbox" checked={draft.is_admin} onChange={(e) => setDraft({ ...draft, is_admin: e.target.checked })} />
                          Admin
                        </label>
                      </div>
                    </div>

                    <label className="mt-3 block text-sm">
                      <span className="text-neutral-500">Admin notes</span>
                      <textarea value={draft.admin_notes} onChange={(e) => setDraft({ ...draft, admin_notes: e.target.value })} rows={3} className="mt-1 w-full rounded-xl border border-neutral-200 px-3 py-2 outline-none focus:border-neutral-400" />
                    </label>

                    <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
                      <Metric label="Chats" value={selectedUser.conversation_count} icon={<MessageSquare className="h-4 w-4" />} />
                      <Metric label="Messages" value={selectedUser.message_count} icon={<FileText className="h-4 w-4" />} />
                      <Metric label="Files" value={selectedUser.uploaded_file_count} icon={<FileText className="h-4 w-4" />} />
                      <Metric label="Tokens" value={selectedUser.total_tokens || selectedUser.estimated_tokens} icon={<Users className="h-4 w-4" />} />
                    </div>

                    <div className="mt-5 grid gap-2 text-sm text-neutral-600 md:grid-cols-2">
                      <p>Last login: <span className="text-neutral-950">{formatDate(selectedUser.last_login_at)}</span></p>
                      <p>Last chat: <span className="text-neutral-950">{formatDate(selectedUser.last_chat_at)}</span></p>
                      <p>Invite code: <span className="text-neutral-950">{selectedUser.invite_code || '-'}</span></p>
                      <p>Password: <span className="text-neutral-950">{selectedUser.password_set ? 'set' : 'missing'}</span></p>
                    </div>

                    <div className="mt-5 rounded-2xl border border-neutral-100 bg-neutral-50 p-4">
                      <p className="text-sm font-semibold text-neutral-900">Reset password</p>
                      <p className="mt-1 text-xs text-neutral-500">At least 8 characters, with letters and numbers.</p>
                      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                        <input
                          type="password"
                          value={newPassword}
                          onChange={(e) => setNewPassword(e.target.value)}
                          placeholder="New password"
                          className="min-w-0 flex-1 rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm outline-none focus:border-neutral-400"
                        />
                        <button
                          onClick={resetUserPassword}
                          disabled={resettingPassword || !newPassword}
                          className="rounded-xl bg-neutral-950 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                        >
                          {resettingPassword ? 'Resetting...' : 'Reset'}
                        </button>
                      </div>
                    </div>
                  </>
                ) : (
                  <p className="text-sm text-neutral-500">Select a user to inspect details.</p>
                )}
              </div>

              <div className="rounded-3xl border border-black/5 bg-white p-5 shadow-sm">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-lg font-semibold">Chat history</h3>
                  <span className="text-sm text-neutral-500">{conversations.length} conversations</span>
                </div>
                <div className="space-y-2">
                  {conversations.map((conversation) => (
                    <button
                      key={conversation.hash_id}
                      onClick={() => navigate(`/admin/conversations/${conversation.hash_id}`)}
                      className="w-full rounded-2xl border border-neutral-100 p-3 text-left transition-colors hover:bg-neutral-50"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="truncate font-medium">{conversation.title || 'Untitled'}</p>
                        <span className="shrink-0 rounded-full bg-neutral-100 px-2 py-0.5 text-xs text-neutral-500">{conversation.message_count} msg</span>
                      </div>
                      <p className="mt-1 truncate text-xs text-neutral-500">{conversation.model} · {formatDate(conversation.updated_at)} · {formatNumber(conversation.total_tokens || conversation.estimated_tokens)} tokens</p>
                    </button>
                  ))}
                </div>
              </div>
          </div>
        </section>
      </main>
    </div>
  )
}

function Metric({ label, value, icon }: { label: string; value: number; icon: ReactNode }) {
  return (
    <div className="rounded-2xl bg-neutral-50 p-3">
      <div className="flex items-center gap-2 text-neutral-500">
        {icon}
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <p className="mt-2 text-xl font-semibold">{formatNumber(value)}</p>
    </div>
  )
}
