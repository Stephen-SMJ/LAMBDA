from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import List
from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.core.hashid import encode_id, decode_id
from app.core.config import settings
from app.models.models import Conversation, Message, UsageRecord, User
from app.models.schemas import (
    ConversationCreate, 
    ConversationResponse, 
    ConversationDetailResponse,
    ConversationUpdate
)

router = APIRouter()


@router.get("", response_model=List[ConversationResponse])
def list_conversations(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    conversations = db.query(
        Conversation,
        func.count(Message.id).label("message_count")
    ).outerjoin(
        Message, Conversation.id == Message.conversation_id
    ).filter(
        Conversation.user_id == current_user.id
    ).group_by(
        Conversation.id
    ).order_by(
        Conversation.updated_at.desc()
    ).offset(skip).limit(limit).all()
    
    result = []
    for conv, msg_count in conversations:
        conv_dict = {
            "id": conv.id,
            "hash_id": encode_id(conv.id),
            "user_id": conv.user_id,
            "title": conv.title,
            "model": conv.model or settings.DEFAULT_MODEL,
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
            "message_count": msg_count
        }
        result.append(conv_dict)
    
    return result


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    conv_data: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    conversation = Conversation(
        user_id=current_user.id,
        title=conv_data.title or "New Conversation",
        model=conv_data.model or settings.DEFAULT_MODEL
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    
    return {
        "id": conversation.id,
        "hash_id": encode_id(conversation.id),
        "user_id": conversation.user_id,
        "title": conversation.title,
        "model": conversation.model or settings.DEFAULT_MODEL,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "message_count": 0
    }


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    real_id = decode_id(conversation_id)
    if real_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Use joinedload to eagerly load messages and ensure all fields are populated
    conversation = db.query(Conversation).options(
        joinedload(Conversation.messages)
    ).filter(
        Conversation.id == real_id,
        Conversation.user_id == current_user.id
    ).first()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    return {
        "id": conversation.id,
        "hash_id": encode_id(conversation.id),
        "user_id": conversation.user_id,
        "title": conversation.title,
        "model": conversation.model or settings.DEFAULT_MODEL,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "message_count": len(conversation.messages),
        "messages": [
            {
                "id": msg.id,
                "conversation_id": msg.conversation_id,
                "role": msg.role,
                "content": msg.content,
                "tool_calls": msg.tool_calls,
                "tool_call_id": msg.tool_call_id,
                "created_at": msg.created_at,
            }
            for msg in conversation.messages
        ]
    }


@router.put("/{conversation_id}", response_model=ConversationResponse)
def update_conversation(
    conversation_id: str,
    conv_data: ConversationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    real_id = decode_id(conversation_id)
    if real_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    conversation = db.query(Conversation).filter(
        Conversation.id == real_id,
        Conversation.user_id == current_user.id
    ).first()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    if conv_data.title is not None:
        conversation.title = conv_data.title
    
    db.commit()
    db.refresh(conversation)
    
    message_count = db.query(func.count(Message.id)).filter(
        Message.conversation_id == conversation.id
    ).scalar()
    
    return {
        "id": conversation.id,
        "hash_id": encode_id(conversation.id),
        "user_id": conversation.user_id,
        "title": conversation.title,
        "model": conversation.model or settings.DEFAULT_MODEL,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "message_count": message_count
    }


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    real_id = decode_id(conversation_id)
    if real_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    conversation = db.query(Conversation).filter(
        Conversation.id == real_id,
        Conversation.user_id == current_user.id
    ).first()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    message_ids = [
        row[0] for row in db.query(Message.id)
        .filter(Message.conversation_id == conversation.id)
        .all()
    ]

    db.query(UsageRecord).filter(
        UsageRecord.conversation_id == conversation.id
    ).update(
        {UsageRecord.conversation_id: None},
        synchronize_session=False
    )

    if message_ids:
        db.query(UsageRecord).filter(
            UsageRecord.message_id.in_(message_ids)
        ).update(
            {UsageRecord.message_id: None},
            synchronize_session=False
        )
    
    db.delete(conversation)
    db.commit()
    
    return None
