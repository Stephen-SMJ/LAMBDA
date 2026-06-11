const API_BASE_URL = import.meta.env.VITE_API_URL || ''

export const exportNotebook = async (conversationId: string): Promise<void> => {
  const response = await fetch(`${API_BASE_URL}/api/v1/export/notebook/${conversationId}`, {
    method: 'POST',
  })
  
  if (!response.ok) {
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
  const response = await fetch(`${API_BASE_URL}/api/v1/export/report/${conversationId}?format=${format}`, {
    method: 'POST',
  })
  
  if (!response.ok) {
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
