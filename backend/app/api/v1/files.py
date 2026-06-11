"""File management API endpoints with OSS support."""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File as FastAPIFile, Form, Query
from fastapi.responses import FileResponse, RedirectResponse, Response
from starlette.background import BackgroundTask
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import zipfile
import shutil
import mimetypes
from pathlib import Path
from datetime import datetime
import io
from urllib.parse import quote, unquote
from urllib.parse import urlparse, parse_qs
import re

from app.api.deps import get_current_active_user, get_db
from app.core.hashid import decode_id
from app.models.models import User, UploadedFile
from app.core.config import settings

router = APIRouter()


def get_oss_service():
    from app.services.oss_service import get_oss_service as _get_oss_service
    return _get_oss_service()

# Base directories (fallback for local mode)
IMAGES_DIR = Path("./data/images")
UPLOADS_DIR = Path("./data/uploads")
LATEX_DIR = Path("./data/latex")
WORKSPACES_DIR = Path(settings.LOCAL_WORKSPACE_ROOT)

# Ensure directories exist for local fallback
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
LATEX_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_OSS_DOMAINS = [
    "lambda-app-prod.oss-cn-hongkong.aliyuncs.com",
]
ALLOWED_OSS_PREFIXES = [
    "generated/",
    "uploads/",
    "latex/",
]

INTERNAL_FILE_MARKERS = (
    "/.skills/",
    "/.lambda_skills/",
    "generated/.skills/",
)

MAX_UPLOAD_SIZE_BYTES = 30 * 1024 * 1024
BLOCKED_UPLOAD_EXTENSIONS = {
    ".app", ".apk", ".bat", ".bin", ".bash", ".cmd", ".com", ".cpl", ".dll",
    ".dmg", ".elf", ".exe", ".gadget", ".hta", ".jar", ".js", ".jse", ".lnk",
    ".msi", ".msp", ".pif", ".ps1", ".py", ".rb", ".reg", ".run", ".scr",
    ".sh", ".so", ".sys", ".vb", ".vbe", ".vbs", ".ws", ".wsf", ".zsh",
}


def validate_upload_file(filename: str, file_size: int) -> None:
    suffix = Path(filename or "").suffix.lower()
    if file_size > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File is too large. Maximum upload size is 30MB.",
        )
    if suffix in BLOCKED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{suffix}' is not allowed for security reasons.",
        )


def is_internal_file_record(file_record: UploadedFile) -> bool:
    """Hide internal sandbox support files from user-facing file APIs."""
    values = [
        file_record.filename or "",
        file_record.original_name or "",
        file_record.file_path or "",
    ]
    return any(marker in value for value in values for marker in INTERNAL_FILE_MARKERS)


def is_allowed_oss_url(url: str) -> bool:
    return any(domain in url for domain in ALLOWED_OSS_DOMAINS)


def extract_oss_object_name(url_or_path: str) -> str:
    """Convert a signed OSS URL or object path into a stable OSS object path."""
    if not url_or_path:
        return ""

    if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
        object_name = get_oss_service().get_object_name_from_url(url_or_path.split("?", 1)[0])
    else:
        object_name = url_or_path.lstrip("/")

    return unquote(object_name)


def oss_path_belongs_to_user(object_name: str, user_id: int) -> bool:
    """Ensure the requested OSS object path matches the authenticated user namespace."""
    parts = [part for part in object_name.split("/") if part]
    if len(parts) < 2:
        return False

    try:
        owner_id = int(parts[1])
    except ValueError:
        return False

    return owner_id == user_id


def is_allowed_oss_object_path(object_name: str) -> bool:
    return any(object_name.startswith(prefix) for prefix in ALLOWED_OSS_PREFIXES)


def build_proxy_object_url(object_name: str, absolute: bool = False) -> str:
    """Build a short proxy URL for an OSS object path."""
    encoded_path = quote(object_name, safe="/")
    relative_url = f"/api/v1/files/proxy-object?path={encoded_path}"
    if absolute:
        return f"{settings.FRONTEND_URL.rstrip('/')}{relative_url}"
    return relative_url


def build_local_file_url(path: str, absolute: bool = False) -> str:
    relative_url = f"/api/v1/files/content?url={quote(path, safe='')}"
    if absolute:
        return f"{settings.FRONTEND_URL.rstrip('/')}{relative_url}"
    return relative_url


async def repair_missing_generated_file_from_sandbox(
    db_file: UploadedFile,
    session_id: str,
    user_id: int,
    db: Session,
) -> bool:
    """Re-upload a generated file if DB has a record but OSS no longer has the object."""
    if settings.FILE_STORAGE_MODE != "oss":
        return True

    object_name = extract_oss_object_name(db_file.file_path or db_file.filename)
    if not object_name or not object_name.startswith("generated/"):
        return True

    oss_service = get_oss_service()
    try:
        if await oss_service.file_exists(object_name):
            return True
    except Exception as e:
        print(f"Failed checking OSS object {object_name}: {e}")
        return True

    parts = object_name.split("/")
    if len(parts) < 4:
        return False

    relative_path = "/".join(parts[3:])
    if not relative_path:
        return False

    try:
        from app.services.sandbox_file_manager import SANDBOX_WORK_DIR, get_sandbox_file_manager

        sandbox_path = f"{SANDBOX_WORK_DIR}/{relative_path}"
        filename = Path(relative_path).name
        repaired_url = await get_sandbox_file_manager().upload_generated_file(
            session_id,
            sandbox_path,
            filename,
            user_id,
            db,
            sandbox_session_id=f"user-{user_id}",
        )
        if repaired_url:
            print(f"Repaired missing OSS object from sandbox: {object_name}")
            return True
    except Exception as e:
        print(f"Failed repairing missing generated file {object_name}: {e}")

    return False


async def read_content_from_reference(reference: str) -> tuple[bytes, str]:
    """Read bytes from an OSS URL, proxy-object path, or local file path."""
    import httpx

    if reference.startswith("/api/v1/files/proxy-object"):
        parsed = urlparse(reference)
        path_values = parse_qs(parsed.query).get("path", [])
        object_name = extract_oss_object_name(path_values[0] if path_values else "")
        if not object_name or not is_allowed_oss_object_path(object_name):
            raise HTTPException(status_code=403, detail="Access denied")

        content = await get_oss_service().download_file(object_name)
        media_type, _ = mimetypes.guess_type(object_name)
        return content, media_type or "application/octet-stream"

    object_name = extract_oss_object_name(reference)
    if object_name and is_allowed_oss_object_path(object_name) and not reference.startswith("http"):
        content = await get_oss_service().download_file(object_name)
        media_type, _ = mimetypes.guess_type(object_name)
        return content, media_type or "application/octet-stream"

    if reference.startswith("http"):
        if not is_allowed_oss_url(reference):
            raise HTTPException(status_code=403, detail="Access denied: URL not in allowed list")
        resolved_url = reference.replace("http://", "https://", 1) if reference.startswith("http://") else reference
        async with httpx.AsyncClient() as client:
            response = await client.get(resolved_url, timeout=60.0)
            response.raise_for_status()
            return response.content, response.headers.get("content-type", "application/octet-stream")

    file_path = Path(reference)
    allowed_roots = [IMAGES_DIR, UPLOADS_DIR, LATEX_DIR, WORKSPACES_DIR.resolve()]
    resolved_path = file_path.resolve()
    is_allowed = any(
        str(resolved_path).startswith(str(Path(root).resolve()))
        for root in allowed_roots
    )
    if not is_allowed or not resolved_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    media_type, _ = mimetypes.guess_type(str(resolved_path))
    return resolved_path.read_bytes(), media_type or "application/octet-stream"


def get_oss_object_name(file_type: str, filename: str, user_id: int, session_id: Optional[str] = None) -> str:
    """Generate OSS object name for file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if session_id:
        return f"{file_type}/{user_id}/{session_id}/{timestamp}_{filename}"
    return f"{file_type}/{user_id}/{timestamp}_{filename}"


@router.post("/upload")
async def upload_file(
    file: UploadFile = FastAPIFile(...),
    conversation_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Upload a file to OSS or local storage."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Upload request - conversation_id: {conversation_id}, file: {file.filename}")
    
    try:
        # Decode hash_id to int for internal session tracking
        session_id = conversation_id
        if conversation_id:
            decoded = decode_id(conversation_id)
            if decoded is not None:
                session_id = str(decoded)
        
        # Read file content
        content = await file.read()
        file_size = len(content)
        validate_upload_file(file.filename or "", file_size)
        
        if settings.FILE_STORAGE_MODE == "oss":
            # Upload to OSS
            oss_service = get_oss_service()
            object_name = get_oss_object_name(
                "uploads", 
                file.filename, 
                current_user.id, 
                session_id
            )
            
            file_url = await oss_service.upload_file(
                content, 
                object_name, 
                file.content_type or 'application/octet-stream'
            )
            file_path = file_url
        else:
            # Local storage fallback
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if session_id:
                safe_filename = f"{session_id}_{timestamp}_{file.filename}"
            else:
                safe_filename = f"{timestamp}_{file.filename}"
            local_path = UPLOADS_DIR / safe_filename
            
            with open(local_path, "wb") as buffer:
                buffer.write(content)
            file_path = str(local_path)
        
        # Save to database
        uploaded_file = UploadedFile(
            user_id=current_user.id,
            conversation_id=session_id,
            filename=os.path.basename(file_path) if settings.FILE_STORAGE_MODE == "local" else object_name,
            original_name=file.filename,
            file_path=file_path,
            file_size=file_size,
            mime_type=file.content_type or 'application/octet-stream'
        )
        db.add(uploaded_file)
        db.commit()
        db.refresh(uploaded_file)
        
        # Note: Sandbox initialization is now done in stream API with keepalive
        # to prevent timeout for large file uploads
        
        return {
            "id": uploaded_file.id,
            "name": uploaded_file.original_name,
            "path": file_path,
            "size": uploaded_file.file_size,
            "content_type": uploaded_file.mime_type,
            "storage_mode": settings.FILE_STORAGE_MODE
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        await file.close()


@router.get("/session/{session_id}")
async def list_session_files(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List all files in a session."""
    files = []
    
    if settings.FILE_STORAGE_MODE == "local":
        # Check images directory
        if IMAGES_DIR.exists():
            for img in IMAGES_DIR.glob(f"{session_id}_*"):
                if img.is_file():
                    stat = img.stat()
                    files.append({
                        "name": img.name,
                        "path": f"/images/{img.name}",
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "type": "image",
                        "category": "generated"
                    })
        
        # Check LaTeX directory
        latex_session = LATEX_DIR / session_id
        if latex_session.exists():
            for file in latex_session.iterdir():
                if file.is_file():
                    stat = file.stat()
                    category = "pdf" if file.suffix == ".pdf" else "latex"
                    files.append({
                        "name": file.name,
                        "path": str(file),
                        "url": f"/api/v1/files/download?path={str(file)}",
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "type": file.suffix.lower(),
                        "category": category
                    })
    else:
        # OSS mode - list files from database that are associated with this session
        pass  # Images and LaTeX files will be tracked via database or separate API
    
    # Check uploaded files - filter by session_id in filename or conversation_id
    db_files = db.query(UploadedFile).filter(
        UploadedFile.user_id == current_user.id,
        (UploadedFile.conversation_id == session_id) | 
        (UploadedFile.filename.like(f"%/{session_id}/%"))
    ).all()
    db_files = [f for f in db_files if not is_internal_file_record(f)]
    
    # Deduplicate by filename (keep the most recent)
    seen_files = {}
    for f in db_files:
        if f.filename not in seen_files or (f.created_at and seen_files[f.filename].created_at and f.created_at > seen_files[f.filename].created_at):
            seen_files[f.filename] = f
    
    db_files = list(seen_files.values())
    
    for f in db_files:
        if settings.FILE_STORAGE_MODE == "oss" and f.filename.startswith("generated/"):
            repaired_or_exists = await repair_missing_generated_file_from_sandbox(
                f,
                session_id,
                current_user.id,
                db,
            )
            if not repaired_or_exists:
                print(f"Skipping missing generated file without sandbox backup: {f.filename}")
                continue

        # Determine category based on file path and mime type
        category = "uploaded"
        if f.filename.startswith("generated/"):
            if f.mime_type and f.mime_type.startswith("image/"):
                category = "image"
            elif f.mime_type == "application/pdf":
                category = "pdf"
            else:
                category = "generated"
        elif f.filename.startswith("latex/"):
            category = "pdf" if f.original_name.endswith(".pdf") else "latex"
        
        # Generate download URL for OSS files
        if settings.FILE_STORAGE_MODE == "oss" and f.file_path.startswith("http"):
            object_name = extract_oss_object_name(f.file_path)
            url = build_proxy_object_url(object_name)
        else:
            url = build_local_file_url(f.file_path)
        
        files.append({
            "name": f.original_name,
            "path": f.file_path,
            "url": url,
            "size": f.file_size,
            "modified": f.created_at.timestamp() if f.created_at else 0,
            "type": Path(f.original_name).suffix.lower(),
            "category": category,
            "id": f.id
        })
    
    return {"files": sorted(files, key=lambda x: x["modified"], reverse=True)}


@router.get("/download")
async def download_file(
    path: str,
    current_user: User = Depends(get_current_active_user)
):
    """Download a file by path."""
    # Check if it's an OSS URL
    if path.startswith("http") and settings.FILE_STORAGE_MODE == "oss":
        # Redirect to OSS URL
        return RedirectResponse(url=path)
    
    file_path = Path(path)
    
    # Security check - only allow access to data directories
    allowed_roots = [IMAGES_DIR, UPLOADS_DIR, LATEX_DIR, WORKSPACES_DIR.resolve()]
    resolved_path = file_path.resolve()
    is_allowed = any(str(resolved_path).startswith(str(Path(root).resolve())) for root in allowed_roots)
    
    if not is_allowed:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not resolved_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=str(resolved_path),
        filename=resolved_path.name,
        media_type="application/octet-stream"
    )


@router.get("/content")
async def get_file_content(
    url: str,
):
    """Get local file content for browser previews."""
    # Local edition is a single-user app. read_content_from_reference still
    # restricts local paths to the app data directories.
    if not settings.LOCAL_MODE:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        content, content_type = await read_content_from_reference(url)
        filename = Path(extract_oss_object_name(url) or url).name or "file"
        return Response(
            content=content,
            media_type=content_type,
            headers={
                'Content-Disposition': f'inline; filename="{filename}"'
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get("/proxy")
async def proxy_file(url: str):
    """Proxy OSS files for browser display/download without direct client-to-OSS requests."""
    import httpx

    if not is_allowed_oss_url(url):
        raise HTTPException(status_code=403, detail="Access denied: URL not in allowed list")

    try:
        if url.startswith("http://"):
            url = url.replace("http://", "https://", 1)

        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url, timeout=60.0)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "application/octet-stream")
            filename = url.split("/")[-1].split("?")[0]
            return Response(
                content=response.content,
                media_type=content_type,
                headers={
                    "Content-Disposition": f'inline; filename="{filename}"',
                    "Cache-Control": "public, max-age=300",
                },
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch file: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get("/proxy-object")
async def proxy_object_file(
    path: str,
    db: Session = Depends(get_db),
):
    """Proxy OSS objects by stable object path instead of signed URL."""
    object_name = extract_oss_object_name(path)
    if not object_name:
        raise HTTPException(status_code=400, detail="Missing object path")

    if not is_allowed_oss_object_path(object_name):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        oss_service = get_oss_service()
        content = await oss_service.download_file(object_name)
        media_type, _ = mimetypes.guess_type(object_name)
        filename = Path(object_name).name

        return Response(
            content=content,
            media_type=media_type or "application/octet-stream",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "Cache-Control": "public, max-age=300",
            },
        )
    except Exception as e:
        if "NoSuchKey" in str(e) and object_name.startswith("generated/"):
            parts = object_name.split("/")
            if len(parts) >= 4:
                try:
                    user_id = int(parts[1])
                    session_id = parts[2]
                    relative_path = "/".join(parts[3:])
                    sandbox_path = f"/tmp/workspace/{relative_path}"
                    filename = Path(relative_path).name

                    from app.services.sandbox_file_manager import get_sandbox_file_manager

                    repaired_url = await get_sandbox_file_manager().upload_generated_file(
                        session_id,
                        sandbox_path,
                        filename,
                        user_id,
                        db,
                        sandbox_session_id=f"user-{user_id}",
                    )
                    if repaired_url:
                        content = await get_oss_service().download_file(object_name)
                        media_type, _ = mimetypes.guess_type(object_name)
                        return Response(
                            content=content,
                            media_type=media_type or "application/octet-stream",
                            headers={
                                "Content-Disposition": f'inline; filename="{filename}"',
                                "Cache-Control": "public, max-age=300",
                            },
                        )
                except Exception as repair_e:
                    print(f"Failed to repair missing proxy object {object_name}: {repair_e}")

        status_code = 404 if "NoSuchKey" in str(e) else 502
        raise HTTPException(status_code=status_code, detail=f"Failed to fetch file: {str(e)}")


@router.post("/package/{session_id}")
async def create_package(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Create a ZIP package of all session files."""
    import tempfile
    import httpx
    
    # Get all files for this session from database
    db_files = db.query(UploadedFile).filter(
        UploadedFile.user_id == current_user.id,
        (UploadedFile.conversation_id == session_id) | 
        (UploadedFile.filename.like(f"%/{session_id}/%"))
    ).all()
    db_files = [f for f in db_files if not is_internal_file_record(f)]
    
    # Create temp zip
    temp_dir = Path(tempfile.mkdtemp())
    zip_path = temp_dir / f"{session_id}_package.zip"
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in db_files:
            try:
                if settings.FILE_STORAGE_MODE == "local":
                    path = Path(f.file_path).resolve()
                    if path.exists() and path.is_file():
                        zf.write(path, arcname=f.original_name)
                elif f.file_path and f.file_path.startswith('http'):
                    async with httpx.AsyncClient() as client:
                        response = await client.get(f.file_path, timeout=30.0)
                        response.raise_for_status()
                        zf.writestr(f.original_name, response.content)
            except Exception as e:
                print(f"Failed to add {f.original_name}: {e}")
    
    return FileResponse(
        path=str(zip_path),
        filename=f"{session_id}_package.zip",
        media_type="application/zip",
        background=BackgroundTask(lambda: shutil.rmtree(temp_dir))
    )


@router.delete("/session/{session_id}/{filename}")
async def delete_file(
    session_id: str,
    filename: str,
    current_user: User = Depends(get_current_active_user)
):
    """Delete a file from session."""
    if settings.FILE_STORAGE_MODE == "oss":
        # Delete from OSS
        oss_service = get_oss_service()
        # Try to find the object name from various locations
        object_names = [
            f"latex/{current_user.id}/{session_id}/{filename}",
            f"images/{current_user.id}/{session_id}/{filename}",
            f"uploads/{current_user.id}/{session_id}/{filename}",
        ]
        for obj_name in object_names:
            try:
                if await oss_service.file_exists(obj_name):
                    await oss_service.delete_file(obj_name)
                    return {"success": True, "message": f"Deleted {filename}"}
            except:
                pass
    
    # Check latex directory (local mode)
    file_path = LATEX_DIR / session_id / filename
    if file_path.exists():
        os.remove(file_path)
        return {"success": True, "message": f"Deleted {filename}"}
    
    raise HTTPException(status_code=404, detail="File not found")


# Internal function to upload generated files (images, PDFs) to OSS
async def upload_generated_file(
    file_path: str, 
    file_type: str,
    user_id: int,
    session_id: Optional[str] = None
) -> str:
    """Upload a generated file to OSS and return the URL."""
    if settings.FILE_STORAGE_MODE != "oss":
        return file_path
    
    path = Path(file_path)
    if not path.exists():
        return file_path
    
    oss_service = get_oss_service()
    object_name = get_oss_object_name(file_type, path.name, user_id, session_id)
    
    # Determine content type
    content_type = 'application/octet-stream'
    if path.suffix == '.png':
        content_type = 'image/png'
    elif path.suffix == '.pdf':
        content_type = 'application/pdf'
    elif path.suffix == '.tex':
        content_type = 'application/x-tex'
    
    url = await oss_service.upload_file_from_path(file_path, object_name)
    return url


async def package_markdown_bytes(markdown_text: str, filename: str) -> tuple[Path, str]:
    """Write markdown and referenced assets into a zip for offline viewing."""
    import tempfile

    zip_basename = Path(filename or "report.md").stem or "report"
    markdown_name = Path(filename or (zip_basename + ".md")).name

    image_refs = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', markdown_text)
    assets_map: dict[str, str] = {}

    temp_dir = Path(tempfile.mkdtemp())
    assets_dir = temp_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    for index, ref in enumerate(image_refs, start=1):
        try:
            image_bytes, _ = await read_content_from_reference(ref)
            parsed_name = Path(extract_oss_object_name(ref) or ref).name
            asset_name = parsed_name or f"asset_{index}.bin"
            target_path = assets_dir / asset_name
            if target_path.exists():
                asset_name = f"{target_path.stem}_{index}{target_path.suffix}"
                target_path = assets_dir / asset_name
            target_path.write_bytes(image_bytes)
            assets_map[ref] = f"assets/{asset_name}"
        except Exception:
            continue

    packaged_markdown = markdown_text
    for original_ref, relative_ref in assets_map.items():
        packaged_markdown = packaged_markdown.replace(f"({original_ref})", f"({relative_ref})")

    (temp_dir / markdown_name).write_text(packaged_markdown, encoding="utf-8")

    zip_path = temp_dir / f"{zip_basename}.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(temp_dir / markdown_name, markdown_name)
        for asset_file in assets_dir.iterdir():
            if asset_file.is_file():
                zf.write(asset_file, f"assets/{asset_file.name}")

    return temp_dir, zip_path.name


@router.get("/package-markdown")
async def package_markdown(
    url: str = Query(...),
    filename: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_active_user)
):
    """Package a markdown file with its referenced images into a zip for offline viewing."""
    markdown_bytes, _ = await read_content_from_reference(url)
    markdown_text = markdown_bytes.decode("utf-8", errors="replace")
    resolved_name = Path(filename or (Path(extract_oss_object_name(url) or "report.md").name)).name
    temp_dir, zip_name = await package_markdown_bytes(markdown_text, resolved_name)

    return FileResponse(
        path=str(temp_dir / zip_name),
        filename=zip_name,
        media_type="application/zip",
        background=BackgroundTask(lambda: shutil.rmtree(temp_dir))
    )
