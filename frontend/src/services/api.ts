import axios from 'axios'
import type { Language } from '../i18n'

// If VITE_API_URL is empty or not set, use relative path (goes through nginx)
const API_BASE_URL = import.meta.env.VITE_API_URL || ''

export const api = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Create conversation API
export const createConversation = async (title?: string, model?: string): Promise<any> => {
  const response = await fetch(`${API_BASE_URL}/api/v1/conversations`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ 
      title: title || 'New Conversation',
      model: model 
    }),
  })
  
  if (!response.ok) {
    const text = await response.text()
    let error: any = {}
    try {
      error = text ? JSON.parse(text) : {}
    } catch {
      error = { detail: text }
    }
    throw new Error(error.detail || 'Failed to create conversation')
  }
  
  return response.json()
}

// File upload API
export const uploadFile = async (file: File, conversationId?: string): Promise<any> => {
  const formData = new FormData()
  formData.append('file', file)
  
  // Add conversation_id to form data if provided
  if (conversationId) {
    formData.append('conversation_id', conversationId.toString())
  }

  const response = await fetch(`${API_BASE_URL}/api/v1/files/upload`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Upload failed')
  }

  return response.json()
}

// Chat streaming API with file support
export const streamChat = async (
  message: string,
  conversationId?: string,
  model?: string,
  fileIds?: number[],
  analysisMode?: string,
  language?: Language,
  onMessage?: (data: any) => void,
  onError?: (error: any) => void,
  signal?: AbortSignal
) => {
  try {
    const streamUrl = API_BASE_URL 
      ? `${API_BASE_URL}/api/v1/chat/stream`
      : '/api/v1/chat/stream'
    const response = await fetch(streamUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        model,
        files: fileIds,
        analysis_mode: analysisMode,
        language,
      }),
      signal,
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body?.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let sawDone = false

    if (!reader) {
      throw new Error('No response body')
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }

      buffer += decoder.decode(value, { stream: true })
      const events = buffer.split('\n\n')
      buffer = events.pop() || ''

      for (const event of events) {
        const dataLines = event
          .split('\n')
          .filter(line => line.startsWith('data: '))
          .map(line => line.slice(6))

        if (dataLines.length > 0) {
          try {
            const data = JSON.parse(dataLines.join('\n'))
            if (data.type === 'done') {
              sawDone = true
            }
            onMessage?.(data)
          } catch (e) {
            // Ignore parse errors for incomplete chunks
          }
        }
      }
    }

    if (buffer.trim().startsWith('data: ')) {
      try {
        const data = JSON.parse(buffer.trim().slice(6))
        if (data.type === 'done') {
          sawDone = true
        }
        onMessage?.(data)
      } catch (e) {
        // Ignore parse errors for incomplete final chunks
      }
    }

    if (!sawDone) {
      throw new Error('Stream ended before completion')
    }
  } catch (error) {
    onError?.(error)
  }
}
