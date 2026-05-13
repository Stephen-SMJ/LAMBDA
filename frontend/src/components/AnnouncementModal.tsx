import { useEffect, useState } from 'react'
import { Megaphone, X } from 'lucide-react'
import { api } from '../services/api'
import { useAuthStore } from '../store/authStore'

interface Announcement {
  id: number
  title: string
  content: string
  created_at: string
}

export default function AnnouncementModal() {
  const { isAuthenticated } = useAuthStore()
  const [announcements, setAnnouncements] = useState<Announcement[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)

  useEffect(() => {
    if (!isAuthenticated) return
    api.get('/announcements/unread')
      .then((response) => setAnnouncements(response.data.announcements || []))
      .catch(() => undefined)
  }, [isAuthenticated])

  const current = announcements[currentIndex]
  if (!current) return null

  const closeCurrent = async () => {
    try {
      await api.post(`/announcements/${current.id}/read`)
    } catch {
      // Best effort only. The modal should not trap the user.
    }

    if (currentIndex + 1 < announcements.length) {
      setCurrentIndex((index) => index + 1)
    } else {
      setAnnouncements([])
      setCurrentIndex(0)
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/35 px-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-[28px] border border-black/5 bg-white p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="rounded-2xl bg-neutral-950 p-3 text-white">
              <Megaphone className="h-5 w-5" />
            </span>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-neutral-400">Notice</p>
              <h2 className="text-xl font-semibold text-neutral-950">{current.title}</h2>
            </div>
          </div>
          <button
            onClick={closeCurrent}
            className="rounded-full p-2 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700"
            aria-label="Close announcement"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mt-5 whitespace-pre-wrap text-sm leading-6 text-neutral-700">
          {current.content}
        </div>

        <div className="mt-6 flex items-center justify-between gap-3">
          <span className="text-xs text-neutral-400">
            {announcements.length > 1 ? `${currentIndex + 1} / ${announcements.length} · Team LAMBDA` : 'Team LAMBDA'}
          </span>
          <button
            onClick={closeCurrent}
            className="rounded-2xl bg-neutral-950 px-5 py-2.5 text-sm font-medium text-white hover:bg-neutral-800"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  )
}
