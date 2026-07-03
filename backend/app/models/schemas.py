from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime


# User schemas
class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None


class UserResponse(UserBase):
    id: int
    display_name: Optional[str] = None
    is_active: bool
    is_admin: bool
    plan: Optional[str] = None
    invite_code: Optional[str] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


# Message schemas
class MessageBase(BaseModel):
    role: str
    content: str
    tool_calls: Optional[str] = None
    tool_call_id: Optional[str] = None


class MessageCreate(MessageBase):
    conversation_id: Optional[int] = None


class MessageResponse(MessageBase):
    id: int
    conversation_id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


# Conversation schemas
class ConversationBase(BaseModel):
    title: Optional[str] = None
    model: Optional[str] = None


class ConversationCreate(ConversationBase):
    pass


class ConversationUpdate(BaseModel):
    title: Optional[str] = None


class ConversationResponse(ConversationBase):
    id: int
    hash_id: str
    user_id: int
    created_at: datetime
    updated_at: datetime
    message_count: Optional[int] = 0
    
    class Config:
        from_attributes = True


class ConversationDetailResponse(ConversationResponse):
    messages: List[MessageResponse] = []
    
    class Config:
        from_attributes = True


# Chat schemas
class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None  # hash_id
    model: Optional[str] = None
    files: Optional[List[int]] = None  # List of uploaded file IDs
    analysis_mode: Optional[str] = None
    language: Optional[str] = None


class ChatStreamResponse(BaseModel):
    type: str  # "delta", "tool_call", "done", "error"
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_output: Optional[str] = None


# File schemas
class FileUploadResponse(BaseModel):
    id: int
    filename: str
    original_name: str
    file_size: int
    mime_type: str
    created_at: datetime
    
    class Config:
        from_attributes = True


# Code execution schemas
class CodeExecutionRequest(BaseModel):
    code: str
    language: str = "python"
    timeout: Optional[int] = 60


class CodeExecutionResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    execution_time: float
