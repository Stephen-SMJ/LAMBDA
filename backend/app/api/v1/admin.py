from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.core.hashid import encode_id, decode_id
from app.core.security import get_password_hash
from app.models.models import Conversation, Message, UploadedFile, UsageRecord, User

router = APIRouter()


class AdminUserUpdate(BaseModel):
    full_name: Optional[str] = None
    display_name: Optional[str] = None
    plan: Optional[str] = None
    admin_notes: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


class AdminPasswordReset(BaseModel):
    new_password: str


def require_admin(user: User):
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


def validate_password_strength(password: str):
    if len(password or "") < 8 or not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters and include both letters and numbers"
        )


def estimate_tokens(*values: Optional[str]) -> int:
    total_chars = sum(len(value or "") for value in values)
    # Practical approximation for mixed English/code/Chinese text. Real usage
    # should be recorded from provider responses when available.
    return max(0, round(total_chars / 3.5))


def estimate_tokens_from_chars(total_chars: int) -> int:
    return max(0, round((total_chars or 0) / 3.5))


def user_payload(
    user: User,
    conversation_count: int = 0,
    message_count: int = 0,
    uploaded_file_count: int = 0,
    estimated_tokens: int = 0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    reasoning_tokens: int = 0,
    usage_record_count: int = 0,
    last_chat_at: Optional[datetime] = None,
):
    total_tokens = int(estimated_tokens or 0)
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "display_name": user.display_name,
        "is_active": user.is_active,
        "is_admin": user.is_admin,
        "plan": user.plan,
        "invite_code": user.invite_code,
        "admin_notes": user.admin_notes,
        "password_set": bool(user.hashed_password),
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "last_login_at": user.last_login_at,
        "last_chat_at": last_chat_at,
        "conversation_count": int(conversation_count or 0),
        "message_count": int(message_count or 0),
        "uploaded_file_count": int(uploaded_file_count or 0),
        "estimated_tokens": total_tokens,
        "total_tokens": total_tokens,
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "reasoning_tokens": int(reasoning_tokens or 0),
        "usage_record_count": int(usage_record_count or 0),
    }


@router.get("/summary")
def admin_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_admin(current_user)

    total_users = db.query(func.count(User.id)).scalar() or 0
    active_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar() or 0
    admin_users = db.query(func.count(User.id)).filter(User.is_admin == True).scalar() or 0
    total_conversations = db.query(func.count(Conversation.id)).scalar() or 0
    total_messages = db.query(func.count(Message.id)).scalar() or 0
    total_files = db.query(func.count(UploadedFile.id)).scalar() or 0
    usage_totals = db.query(
        func.coalesce(func.sum(UsageRecord.prompt_tokens), 0),
        func.coalesce(func.sum(UsageRecord.completion_tokens), 0),
        func.coalesce(func.sum(UsageRecord.reasoning_tokens), 0),
        func.coalesce(func.sum(UsageRecord.total_tokens), 0),
        func.count(UsageRecord.id),
    ).one()
    message_chars = db.query(func.coalesce(func.sum(func.length(Message.content)), 0)).scalar() or 0
    total_tokens = int(usage_totals[3] or 0) or estimate_tokens_from_chars(int(message_chars or 0))

    return {
        "total_users": total_users,
        "active_users": active_users,
        "admin_users": admin_users,
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "total_files": total_files,
        "estimated_tokens": total_tokens,
        "total_tokens": total_tokens,
        "prompt_tokens": int(usage_totals[0] or 0),
        "completion_tokens": int(usage_totals[1] or 0),
        "reasoning_tokens": int(usage_totals[2] or 0),
        "usage_record_count": int(usage_totals[4] or 0),
    }


@router.get("/users")
def admin_list_users(
    search: str = "",
    skip: int = 0,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_admin(current_user)

    message_stats = (
        db.query(
            Conversation.user_id.label("user_id"),
            func.count(func.distinct(Conversation.id)).label("conversation_count"),
            func.count(Message.id).label("message_count"),
            func.coalesce(func.sum(func.length(Message.content)), 0).label("message_chars"),
            func.max(Conversation.updated_at).label("last_chat_at"),
        )
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .group_by(Conversation.user_id)
        .subquery()
    )
    file_stats = (
        db.query(
            UploadedFile.user_id.label("user_id"),
            func.count(UploadedFile.id).label("uploaded_file_count"),
        )
        .group_by(UploadedFile.user_id)
        .subquery()
    )
    usage_stats = (
        db.query(
            UsageRecord.user_id.label("user_id"),
            func.coalesce(func.sum(UsageRecord.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(UsageRecord.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(UsageRecord.reasoning_tokens), 0).label("reasoning_tokens"),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0).label("total_tokens"),
            func.count(UsageRecord.id).label("usage_record_count"),
        )
        .group_by(UsageRecord.user_id)
        .subquery()
    )

    query = (
        db.query(
            User,
            func.coalesce(message_stats.c.conversation_count, 0),
            func.coalesce(message_stats.c.message_count, 0),
            func.coalesce(file_stats.c.uploaded_file_count, 0),
            func.coalesce(message_stats.c.message_chars, 0),
            message_stats.c.last_chat_at,
            func.coalesce(usage_stats.c.prompt_tokens, 0),
            func.coalesce(usage_stats.c.completion_tokens, 0),
            func.coalesce(usage_stats.c.reasoning_tokens, 0),
            func.coalesce(usage_stats.c.total_tokens, 0),
            func.coalesce(usage_stats.c.usage_record_count, 0),
        )
        .outerjoin(message_stats, message_stats.c.user_id == User.id)
        .outerjoin(file_stats, file_stats.c.user_id == User.id)
        .outerjoin(usage_stats, usage_stats.c.user_id == User.id)
    )

    search = search.strip()
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                User.email.ilike(pattern),
                User.full_name.ilike(pattern),
                User.display_name.ilike(pattern),
                User.invite_code.ilike(pattern),
            )
        )

    total = query.count()
    rows = query.order_by(User.created_at.desc()).offset(skip).limit(limit).all()
    return {
        "total": total,
        "users": [
            user_payload(
                user,
                conversation_count=conversation_count,
                message_count=message_count,
                uploaded_file_count=uploaded_file_count,
                estimated_tokens=int(total_tokens or 0) or estimate_tokens_from_chars(int(message_chars or 0)),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                reasoning_tokens=reasoning_tokens,
                usage_record_count=usage_record_count,
                last_chat_at=last_chat_at,
            )
            for (
                user,
                conversation_count,
                message_count,
                uploaded_file_count,
                message_chars,
                last_chat_at,
                prompt_tokens,
                completion_tokens,
                reasoning_tokens,
                total_tokens,
                usage_record_count,
            ) in rows
        ],
    }


@router.get("/users/{user_id}")
def admin_get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_admin(current_user)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    conversation_count = db.query(func.count(Conversation.id)).filter(Conversation.user_id == user.id).scalar() or 0
    message_count = (
        db.query(func.count(Message.id))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Conversation.user_id == user.id)
        .scalar()
        or 0
    )
    message_chars = (
        db.query(func.coalesce(func.sum(func.length(Message.content)), 0))
        .join(Conversation, Conversation.id == Message.conversation_id)
        .filter(Conversation.user_id == user.id)
        .scalar()
        or 0
    )
    uploaded_file_count = db.query(func.count(UploadedFile.id)).filter(UploadedFile.user_id == user.id).scalar() or 0
    last_chat_at = db.query(func.max(Conversation.updated_at)).filter(Conversation.user_id == user.id).scalar()
    usage_totals = (
        db.query(
            func.coalesce(func.sum(UsageRecord.prompt_tokens), 0),
            func.coalesce(func.sum(UsageRecord.completion_tokens), 0),
            func.coalesce(func.sum(UsageRecord.reasoning_tokens), 0),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0),
            func.count(UsageRecord.id),
        )
        .filter(UsageRecord.user_id == user.id)
        .one()
    )

    return user_payload(
        user,
        conversation_count=conversation_count,
        message_count=message_count,
        uploaded_file_count=uploaded_file_count,
        estimated_tokens=int(usage_totals[3] or 0) or estimate_tokens_from_chars(int(message_chars or 0)),
        prompt_tokens=int(usage_totals[0] or 0),
        completion_tokens=int(usage_totals[1] or 0),
        reasoning_tokens=int(usage_totals[2] or 0),
        usage_record_count=int(usage_totals[4] or 0),
        last_chat_at=last_chat_at,
    )


@router.patch("/users/{user_id}")
def admin_update_user(
    user_id: int,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_admin(current_user)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    for field in ["full_name", "display_name", "plan", "admin_notes", "is_active", "is_admin"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return {"success": True, "user": user_payload(user)}


@router.post("/users/{user_id}/reset-password")
def admin_reset_user_password(
    user_id: int,
    payload: AdminPasswordReset,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_admin(current_user)
    validate_password_strength(payload.new_password)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = get_password_hash(payload.new_password)
    db.commit()
    return {"success": True, "message": "Password reset successfully"}


@router.get("/users/{user_id}/conversations")
def admin_user_conversations(
    user_id: int,
    skip: int = 0,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_admin(current_user)
    if not db.query(User.id).filter(User.id == user_id).first():
        raise HTTPException(status_code=404, detail="User not found")

    usage_stats = (
        db.query(
            UsageRecord.conversation_id.label("conversation_id"),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0).label("total_tokens"),
            func.count(UsageRecord.id).label("usage_record_count"),
        )
        .filter(UsageRecord.user_id == user_id)
        .group_by(UsageRecord.conversation_id)
        .subquery()
    )
    rows = (
        db.query(
            Conversation,
            func.count(Message.id).label("message_count"),
            func.coalesce(func.sum(func.length(Message.content)), 0).label("message_chars"),
            func.sum(case((Message.role == "user", 1), else_=0)).label("user_message_count"),
            func.sum(case((Message.role == "assistant", 1), else_=0)).label("assistant_message_count"),
            func.coalesce(usage_stats.c.total_tokens, 0).label("total_tokens"),
            func.coalesce(usage_stats.c.usage_record_count, 0).label("usage_record_count"),
        )
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .outerjoin(usage_stats, usage_stats.c.conversation_id == Conversation.id)
        .filter(Conversation.user_id == user_id)
        .group_by(Conversation.id, usage_stats.c.total_tokens, usage_stats.c.usage_record_count)
        .order_by(Conversation.updated_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return [
        {
            "id": conversation.id,
            "hash_id": encode_id(conversation.id),
            "title": conversation.title,
            "model": conversation.model,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "message_count": int(message_count or 0),
            "user_message_count": int(user_message_count or 0),
            "assistant_message_count": int(assistant_message_count or 0),
            "estimated_tokens": int(total_tokens or 0) or estimate_tokens_from_chars(int(message_chars or 0)),
            "total_tokens": int(total_tokens or 0) or estimate_tokens_from_chars(int(message_chars or 0)),
            "usage_record_count": int(usage_record_count or 0),
        }
        for (
            conversation,
            message_count,
            message_chars,
            user_message_count,
            assistant_message_count,
            total_tokens,
            usage_record_count,
        ) in rows
    ]


@router.get("/conversations/{conversation_hash_id}")
def admin_get_conversation(
    conversation_hash_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_admin(current_user)
    conversation_id = decode_id(conversation_hash_id)
    if conversation_id is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    owner = db.query(User).filter(User.id == conversation.user_id).first()
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )
    usage_totals = (
        db.query(
            func.coalesce(func.sum(UsageRecord.prompt_tokens), 0),
            func.coalesce(func.sum(UsageRecord.completion_tokens), 0),
            func.coalesce(func.sum(UsageRecord.reasoning_tokens), 0),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0),
            func.count(UsageRecord.id),
        )
        .filter(UsageRecord.conversation_id == conversation.id)
        .one()
    )
    fallback_tokens = estimate_tokens(*(message.content for message in messages))
    total_tokens = int(usage_totals[3] or 0) or fallback_tokens

    return {
        "id": conversation.id,
        "hash_id": encode_id(conversation.id),
        "title": conversation.title,
        "model": conversation.model,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "owner": {
            "id": owner.id,
            "email": owner.email,
            "full_name": owner.full_name,
            "display_name": owner.display_name,
        } if owner else None,
        "estimated_tokens": total_tokens,
        "total_tokens": total_tokens,
        "prompt_tokens": int(usage_totals[0] or 0),
        "completion_tokens": int(usage_totals[1] or 0),
        "reasoning_tokens": int(usage_totals[2] or 0),
        "usage_record_count": int(usage_totals[4] or 0),
        "messages": [
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "tool_calls": message.tool_calls,
                "created_at": message.created_at,
            }
            for message in messages
        ],
    }
