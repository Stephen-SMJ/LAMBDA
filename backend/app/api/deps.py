from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_token
from app.core.security import get_password_hash
from app.core.config import settings
from app.models.models import User
from typing import Generator, Optional

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    if settings.LOCAL_MODE:
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

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not token:
        raise credentials_exception
    
    payload = decode_token(token)
    if payload is None:
        raise credentials_exception
    
    user_id: Optional[int] = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive"
        )
    
    return user


def get_current_user_optional(
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme)
) -> Optional[User]:
    if settings.LOCAL_MODE:
        return get_current_user(db=db, token=token or "")

    """Get current user if authenticated, otherwise return None."""
    if not token:
        return None
    
    payload = decode_token(token)
    if payload is None:
        return None
    
    user_id: Optional[int] = payload.get("sub")
    if user_id is None:
        return None
    
    user = db.query(User).filter(User.id == user_id).first()
    return user


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
