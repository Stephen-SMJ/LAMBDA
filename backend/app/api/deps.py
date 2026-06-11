from fastapi import Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_password_hash
from app.core.config import settings
from app.models.models import User
from typing import Optional


def get_current_user(
    db: Session = Depends(get_db),
) -> User:
    user = db.query(User).filter(User.email == settings.LOCAL_USER_EMAIL).first()
    if user is None:
        user = User(
            email=settings.LOCAL_USER_EMAIL,
            hashed_password=get_password_hash("local-mode"),
            full_name=settings.LOCAL_USER_NAME,
            display_name=settings.LOCAL_USER_NAME,
            is_active=True,
            is_admin=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_current_user_optional(
    db: Session = Depends(get_db),
) -> Optional[User]:
    return get_current_user(db=db)


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
