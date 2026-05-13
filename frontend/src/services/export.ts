const API_BASE_URL = import.meta.env.VITE_API_URL || ''

// Get token from localStorage directly (Zustand persist stores it there)
const getToken = (): string | null => {
  try {
    const storage = localStorage.getItem('lambda-auth-storage')
    if (storage) {
      const parsed = JSON.parse(storage)
      return parsed.state?.token || null
    }
  } catch {
    // Fallback: try getting token directly
  }
  return null
}

export const exportNotebook = async (conversationId: string): Promise<void> => {
  const token = getToken()
  
  if (!token) {
    throw new Error('Not authenticated')
  }
  
  const response = await fetch(`${API_BASE_URL}/api/v1/export/notebook/${conversationId}`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  })
  
  if (!response.ok) {
    if (response.status === 401) {
      throw new Error('Authentication expired. Please login again.')
    }
    throw new Error('Export failed')
  }
  
  const blob = await response.blob()
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `notebook_${conversationId}.ipynb`
  document.body.appendChild(a)
  a.click()
  window.URL.revokeObjectURL(url)
  document.body.removeChild(a)
}

export const exportReport = async (conversationId: string, format: 'md' | 'pdf' | 'zip' | 'slides' = 'md'): Promise<void> => {
  const token = getToken()
  
  if (!token) {
    throw new Error('Not authenticated')
  }
  
  const response = await fetch(`${API_BASE_URL}/api/v1/export/report/${conversationId}?format=${format}`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  })
  
  if (!response.ok) {
    if (response.status === 401) {
      throw new Error('Authentication expired. Please login again.')
    }
    throw new Error('Export failed')
  }
  
  const blob = await response.blob()
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const ext = format === 'slides' ? 'pdf' : format
  a.download = `report_${conversationId}.${ext}`
  document.body.appendChild(a)
  a.click()
  window.URL.revokeObjectURL(url)
  document.body.removeChild(a)
}
