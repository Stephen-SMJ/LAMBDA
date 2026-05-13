export interface User {
  id: number
  email: string
  full_name: string | null
  display_name?: string | null
  is_active: boolean
  is_admin?: boolean
  plan?: string | null
  invite_code?: string | null
  last_login_at?: string | null
  created_at: string
}

export interface Message {
  id: number
  conversation_id: number
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  tool_calls?: string
  tool_call_id?: string
  created_at: string
}

export interface Conversation {
  id: number
  hash_id: string
  user_id: number
  title: string
  model: string
  created_at: string
  updated_at: string
  message_count?: number
  messages?: Message[]
}

export interface ToolCall {
  id: string
  type: string
  function: {
    name: string
    arguments: string
  }
}

export interface ToolResult {
  success: boolean
  stdout?: string
  stderr?: string
  output?: string
  content_preview?: string
  path?: string
  exit_code?: number
  execution_time?: number
  error?: string
  images?: string[]
  todos?: Array<{ id?: number; content: string; status: string }>
}

export interface ChatStreamData {
  type: 'delta' | 'reasoning' | 'tool_call' | 'tool_result' | 'done' | 'error' | 'conversation_created' | 'status' | 'keepalive'
  content?: string
  conversation_id?: string
  tool_call?: ToolCall
  tool_call_id?: string
  tool_name?: string
  result?: ToolResult
  step?: number
  generated_files?: { name: string; url: string; type: string }[]
  timestamp?: number
}

export interface UploadedFile {
  id: number
  filename: string
  original_name: string
  file_size: number
  mime_type: string
  created_at: string
}

export interface CodeExecutionResult {
  success: boolean
  stdout: string
  stderr: string
  exit_code: number
  execution_time: number
}
