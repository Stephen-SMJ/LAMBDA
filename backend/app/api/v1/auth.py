from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from datetime import datetime, timedelta as dt_timedelta
import hashlib
import secrets
import hmac
import httpx
from app.core.database import get_db
from app.core.security import verify_password, create_access_token, get_password_hash
from app.models.models import User, EmailVerificationCode, InviteCode
from app.models.schemas import (
    ResetPasswordRequest,
    SendPasswordResetCodeRequest,
    SendVerificationCodeRequest,
    Token,
    UserCreate,
    UserResponse,
)
from app.core.config import settings

router = APIRouter()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_verification_code(email: str, code: str) -> str:
    payload = f"{normalize_email(email)}:{code}:{settings.SECRET_KEY}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_password_strength(password: str):
    if len(password or "") < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters and include both letters and numbers"
        )
    if not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters and include both letters and numbers"
        )


def get_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if request.client:
        return request.client.host
    return None


def verify_turnstile_or_raise(token: str | None, request: Request):
    if not settings.TURNSTILE_ENABLED:
        return

    if not settings.TURNSTILE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Turnstile is not configured"
        )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Human verification is required"
        )

    try:
        response = httpx.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={
                "secret": settings.TURNSTILE_SECRET_KEY,
                "response": token,
                "remoteip": get_client_ip(request),
            },
            timeout=10.0,
        )
        payload = response.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Human verification service is unavailable"
        )

    if not payload.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Human verification failed"
        )


def send_verification_email(email: str, code: str):
    if not settings.RESEND_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Email verification service is not configured"
        )

    response = httpx.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": settings.EMAIL_FROM,
            "to": [email],
            "subject": "Your LAMBDA verification code",
            "html": (
                "<div style='font-family:Arial,sans-serif;line-height:1.6'>"
                "<h2>LAMBDA Email Verification</h2>"
                f"<p>Your verification code is <strong style='font-size:24px'>{code}</strong>.</p>"
                f"<p>This code expires in {settings.EMAIL_VERIFICATION_EXPIRE_MINUTES} minutes.</p>"
                "<p>If you did not request this, you can ignore this email.</p>"
                "</div>"
            ),
        },
        timeout=20.0,
    )

    if response.status_code >= 400:
        detail = "Failed to send verification email"
        try:
            payload = response.json()
            detail = payload.get("message") or payload.get("error") or detail
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail,
        )


@router.post("/send-verification-code")
def send_verification_code(
    payload: SendVerificationCodeRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    verify_turnstile_or_raise(payload.turnstile_token, request)
    email = normalize_email(payload.email)

    invite = db.query(InviteCode).filter(
        InviteCode.code == payload.invite_code,
        InviteCode.is_active == True
    ).first()
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid invitation code"
        )
    if invite.used_count >= invite.max_uses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邀请码使用人数已满"
        )

    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    now = datetime.utcnow()
    resend_cutoff = now - dt_timedelta(seconds=settings.EMAIL_VERIFICATION_RESEND_SECONDS)
    recent_code = (
        db.query(EmailVerificationCode)
        .filter(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose == "register",
            EmailVerificationCode.created_at >= resend_cutoff,
        )
        .order_by(EmailVerificationCode.created_at.desc())
        .first()
    )
    if recent_code:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {settings.EMAIL_VERIFICATION_RESEND_SECONDS} seconds before requesting another code"
        )

    hourly_cutoff = now - dt_timedelta(hours=1)
    hourly_count = (
        db.query(EmailVerificationCode)
        .filter(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose == "register",
            EmailVerificationCode.created_at >= hourly_cutoff,
        )
        .count()
    )
    if hourly_count >= settings.EMAIL_VERIFICATION_HOURLY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many verification attempts. Please try again later."
        )

    code = f"{secrets.randbelow(1000000):06d}"
    db_code = EmailVerificationCode(
        email=email,
        purpose="register",
        code_hash=hash_verification_code(email, code),
        expires_at=now + dt_timedelta(minutes=settings.EMAIL_VERIFICATION_EXPIRE_MINUTES),
    )
    db.add(db_code)
    db.commit()

    try:
        send_verification_email(email, code)
    except Exception:
        db.delete(db_code)
        db.commit()
        raise

    return {
        "message": "Verification code sent",
        "expires_in_minutes": settings.EMAIL_VERIFICATION_EXPIRE_MINUTES,
    }


def check_verification_rate_limit(db: Session, email: str, purpose: str):
    now = datetime.utcnow()
    resend_cutoff = now - dt_timedelta(seconds=settings.EMAIL_VERIFICATION_RESEND_SECONDS)
    recent_code = (
        db.query(EmailVerificationCode)
        .filter(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose == purpose,
            EmailVerificationCode.created_at >= resend_cutoff,
        )
        .order_by(EmailVerificationCode.created_at.desc())
        .first()
    )
    if recent_code:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {settings.EMAIL_VERIFICATION_RESEND_SECONDS} seconds before requesting another code"
        )

    hourly_cutoff = now - dt_timedelta(hours=1)
    hourly_count = (
        db.query(EmailVerificationCode)
        .filter(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose == purpose,
            EmailVerificationCode.created_at >= hourly_cutoff,
        )
        .count()
    )
    if hourly_count >= settings.EMAIL_VERIFICATION_HOURLY_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many verification attempts. Please try again later."
        )


def create_and_send_code(db: Session, email: str, purpose: str):
    now = datetime.utcnow()
    code = f"{secrets.randbelow(1000000):06d}"
    db_code = EmailVerificationCode(
        email=email,
        purpose=purpose,
        code_hash=hash_verification_code(email, code),
        expires_at=now + dt_timedelta(minutes=settings.EMAIL_VERIFICATION_EXPIRE_MINUTES),
    )
    db.add(db_code)
    db.commit()

    try:
        send_verification_email(email, code)
    except Exception:
        db.delete(db_code)
        db.commit()
        raise

    return {
        "message": "Verification code sent",
        "expires_in_minutes": settings.EMAIL_VERIFICATION_EXPIRE_MINUTES,
    }


def get_valid_verification_or_raise(db: Session, email: str, purpose: str, code: str) -> EmailVerificationCode:
    verification = (
        db.query(EmailVerificationCode)
        .filter(
            EmailVerificationCode.email == email,
            EmailVerificationCode.purpose == purpose,
            EmailVerificationCode.used_at.is_(None),
        )
        .order_by(EmailVerificationCode.created_at.desc())
        .first()
    )
    if not verification or verification.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code expired or not found"
        )

    expected_hash = hash_verification_code(email, code)
    if not hmac.compare_digest(expected_hash, verification.code_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code"
        )
    return verification


@router.post("/register", response_model=Token)
def register(
    user_data: UserCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    verify_turnstile_or_raise(user_data.turnstile_token, request)
    email = normalize_email(user_data.email)
    validate_password_strength(user_data.password)

    # Validate invitation code
    invite = db.query(InviteCode).filter(
        InviteCode.code == user_data.invite_code,
        InviteCode.is_active == True
    ).first()
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid invitation code"
        )
    if invite.used_count >= invite.max_uses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该邀请码使用人数已满"
        )
    
    # Check if user already exists
    db_user = db.query(User).filter(User.email == email).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    verification = get_valid_verification_or_raise(
        db,
        email,
        "register",
        user_data.verification_code,
    )
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    db_user = User(
        email=email,
        hashed_password=hashed_password,
        full_name=user_data.full_name,
        is_active=True,
        invite_code=user_data.invite_code
    )
    db.add(db_user)
    invite.used_count += 1
    verification.used_at = datetime.utcnow()
    db.commit()
    db.refresh(db_user)
    
    # Create access token
    access_token = create_access_token(
        data={"sub": str(db_user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": db_user
    }


@router.post("/send-password-reset-code")
def send_password_reset_code(
    payload: SendPasswordResetCodeRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    verify_turnstile_or_raise(payload.turnstile_token, request)
    email = normalize_email(payload.email)
    check_verification_rate_limit(db, email, "password_reset")

    user = db.query(User).filter(User.email == email).first()
    if user:
        return create_and_send_code(db, email, "password_reset")

    # Avoid leaking whether an email exists.
    return {
        "message": "If the email exists, a reset code has been sent",
        "expires_in_minutes": settings.EMAIL_VERIFICATION_EXPIRE_MINUTES,
    }


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    verify_turnstile_or_raise(payload.turnstile_token, request)
    email = normalize_email(payload.email)
    validate_password_strength(payload.new_password)

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code"
        )

    verification = get_valid_verification_or_raise(
        db,
        email,
        "password_reset",
        payload.verification_code,
    )
    user.hashed_password = get_password_hash(payload.new_password)
    verification.used_at = datetime.utcnow()
    db.commit()
    return {"message": "Password has been reset"}


@router.post("/login", response_model=Token)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    turnstile_token: str | None = Form(None),
    db: Session = Depends(get_db)
):
    verify_turnstile_or_raise(turnstile_token, request)
    # Find user by email
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    
    # Create access token
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }
