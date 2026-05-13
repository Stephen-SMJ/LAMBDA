from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.core.database import get_db
from app.models.models import Announcement, AnnouncementRead, User

router = APIRouter()


class AnnouncementCreate(BaseModel):
    title: str
    content: str
    is_active: bool = True


def require_admin(user: User):
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


def announcement_payload(announcement: Announcement):
    return {
        "id": announcement.id,
        "title": announcement.title,
        "content": announcement.content,
        "is_active": announcement.is_active,
        "created_by": announcement.created_by,
        "created_at": announcement.created_at,
        "updated_at": announcement.updated_at,
    }


@router.get("/unread")
def get_unread_announcements(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    read_subquery = (
        db.query(AnnouncementRead.announcement_id)
        .filter(AnnouncementRead.user_id == current_user.id)
        .subquery()
    )
    announcements = (
        db.query(Announcement)
        .filter(
            Announcement.is_active == True,
            ~Announcement.id.in_(read_subquery),
        )
        .order_by(Announcement.created_at.desc())
        .limit(5)
        .all()
    )
    return {"announcements": [announcement_payload(item) for item in announcements]}


@router.post("/{announcement_id}/read")
def mark_announcement_read(
    announcement_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    existing = (
        db.query(AnnouncementRead)
        .filter(
            AnnouncementRead.announcement_id == announcement_id,
            AnnouncementRead.user_id == current_user.id,
        )
        .first()
    )
    if not existing:
        db.add(AnnouncementRead(
            announcement_id=announcement_id,
            user_id=current_user.id,
            read_at=datetime.utcnow(),
        ))
        db.commit()
    return {"success": True}


@router.get("/admin")
def admin_list_announcements(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_admin(current_user)
    announcements = (
        db.query(Announcement)
        .order_by(Announcement.created_at.desc())
        .limit(50)
        .all()
    )
    return {"announcements": [announcement_payload(item) for item in announcements]}


@router.post("/admin")
def admin_create_announcement(
    payload: AnnouncementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_admin(current_user)
    title = payload.title.strip()
    content = payload.content.strip()
    if not title or not content:
        raise HTTPException(status_code=400, detail="Title and content are required")

    announcement = Announcement(
        title=title,
        content=content,
        is_active=payload.is_active,
        created_by=current_user.id,
    )
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    return {"success": True, "announcement": announcement_payload(announcement)}


@router.patch("/admin/{announcement_id}")
def admin_update_announcement(
    announcement_id: int,
    payload: AnnouncementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    require_admin(current_user)
    announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    announcement.title = payload.title.strip()
    announcement.content = payload.content.strip()
    announcement.is_active = payload.is_active
    announcement.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(announcement)
    return {"success": True, "announcement": announcement_payload(announcement)}
