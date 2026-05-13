"""
Sandbox File Manager - Handles file synchronization between OSS and OpenSandbox.

This module ensures files are available in the sandbox environment for analysis,
and uploads generated files back to OSS for frontend access.
"""

import os
import asyncio
import base64
import posixpath
import re
import shlex
import shutil
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from urllib.parse import unquote
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.models import UploadedFile


SANDBOX_WORK_DIR = "/tmp/workspace"
SANDBOX_SKILLS_DIR = f"{SANDBOX_WORK_DIR}/.skills"


def extract_oss_object_name(url_or_path: str) -> str:
    """Convert a signed OSS URL or object path into a stable OSS object path."""
    if not url_or_path:
        return ""

    if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
        from app.services.oss_service import get_oss_service
        object_name = get_oss_service().get_object_name_from_url(url_or_path.split("?", 1)[0])
    else:
        object_name = url_or_path.lstrip("/")

    return unquote(object_name)


class SandboxFileManager:
    """Manages file synchronization between OSS and OpenSandbox."""
    
    def __init__(self):
        self.oss_service = None
        self._synced_files: Dict[str, Dict[str, str]] = {}  # session_id -> {filename: sandbox_path}
        self._sync_cache_generation: Dict[str, tuple[str, int]] = {}
        self._active_workspace_session: Dict[str, str] = {}

    def _get_oss_service(self):
        if self.oss_service is None:
            from app.services.oss_service import get_oss_service
            self.oss_service = get_oss_service()
        return self.oss_service

    def _is_local_mode(self) -> bool:
        return settings.CODE_EXECUTION_MODE == "local" or settings.FILE_STORAGE_MODE == "local"

    def _local_workspace(self, session_id: str) -> Path:
        workspace = Path(settings.LOCAL_WORKSPACE_ROOT).resolve() / str(session_id)
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    def _local_skills_dir(self, session_id: str) -> Path:
        return self._local_workspace(session_id) / ".skills"

    def _copy_local_skills(self, session_id: str) -> None:
        skills_root = Path(__file__).resolve().parents[1] / "skills"
        target = self._local_skills_dir(session_id)
        target.mkdir(parents=True, exist_ok=True)
        for skill_path in sorted(skills_root.glob("*_skill.md")):
            shutil.copy2(skill_path, target / skill_path.name)
        logo_path = skills_root / "res" / "logo.png"
        if logo_path.exists():
            (target / "res").mkdir(parents=True, exist_ok=True)
            shutil.copy2(logo_path, target / "res" / "logo.png")

    def _generated_object_name(self, user_id: int, session_id: str, sandbox_path: str, filename: str) -> str:
        """Build a stable OSS object name while preserving workspace subdirectories."""
        normalized_path = sandbox_path.replace("\\", "/")
        work_prefix = SANDBOX_WORK_DIR.rstrip("/") + "/"
        if normalized_path.startswith(work_prefix):
            relative_path = normalized_path[len(work_prefix):]
        else:
            relative_path = filename

        safe_parts = []
        for part in relative_path.split("/"):
            if not part or part in {".", ".."}:
                continue
            safe_parts.append(re.sub(r"[^A-Za-z0-9._ -]", "_", part))

        safe_relative_path = posixpath.join(*safe_parts) if safe_parts else filename
        return f"generated/{user_id}/{session_id}/{safe_relative_path}"

    def _sandbox_restore_path(self, db_file: UploadedFile, user_id: int, session_id: str) -> Tuple[str, bool]:
        """Map a DB file record back to its intended sandbox path."""
        object_name = db_file.filename or ""
        generated_prefix = f"generated/{user_id}/{session_id}/"
        if object_name.startswith(generated_prefix):
            relative_path = object_name[len(generated_prefix):].strip("/")
            safe_parts = []
            for part in relative_path.split("/"):
                if not part or part in {".", ".."}:
                    continue
                safe_parts.append(re.sub(r"[^A-Za-z0-9._ -]", "_", part))
            if safe_parts:
                return f"{SANDBOX_WORK_DIR}/{posixpath.join(*safe_parts)}", True

        filename = db_file.original_name or Path(object_name).name
        safe_filename = re.sub(r"[^A-Za-z0-9._ -]", "_", filename)
        return f"{SANDBOX_WORK_DIR}/{safe_filename}", False

    async def _ensure_skills(self, opensandbox, sandbox_session_id: str) -> None:
        """Make internal skill guides readable inside the sandbox."""
        skills_root = Path(__file__).resolve().parents[1] / "skills"
        logo_path = skills_root / "res" / "logo.png"
        try:
            skill_entries = []
            for skill_path in sorted(skills_root.glob("*_skill.md")):
                skill_entries.append((skill_path.name, skill_path.read_text(encoding="utf-8")))
            logo_data = logo_path.read_bytes() if logo_path.exists() else None
            from opensandbox.models import WriteEntry

            await opensandbox.execute_shell(f"mkdir -p {SANDBOX_SKILLS_DIR}/res", sandbox_session_id, timeout=20)
            session = await opensandbox._get_or_create_session(sandbox_session_id)
            entries = [
                WriteEntry(path=f"{SANDBOX_SKILLS_DIR}/{filename}", data=skill_text, mode=644)
                for filename, skill_text in skill_entries
            ]
            if logo_data is not None:
                entries.append(
                    WriteEntry(
                        path=f"{SANDBOX_SKILLS_DIR}/res/logo.png",
                        data=logo_data,
                        mode=644,
                    )
                )
            await session.sandbox.files.write_files(entries)
        except Exception as e:
            print(f"[SYNC] Failed to write skill files to sandbox: {e}")

    async def prepare_workspace_for_session(self, session_id: str, sandbox_session_id: str) -> None:
        """Ensure a user-scoped sandbox only exposes files for the active conversation."""
        if self._is_local_mode():
            self._local_workspace(session_id)
            self._copy_local_skills(session_id)
            return

        if self._active_workspace_session.get(sandbox_session_id) == session_id:
            return

        from app.services.opensandbox_service import get_opensandbox_service
        opensandbox = get_opensandbox_service()
        await opensandbox.execute_shell(
            f"mkdir -p {SANDBOX_WORK_DIR} && find {SANDBOX_WORK_DIR} -mindepth 1 -maxdepth 1 ! -name '.skills' -exec rm -rf {{}} +",
            sandbox_session_id,
            timeout=30,
        )
        self._active_workspace_session[sandbox_session_id] = session_id
        self._synced_files[session_id] = {}
        self._sync_cache_generation.pop(session_id, None)
    
    async def sync_session_files(
        self,
        session_id: str,
        db: Session,
        user_id: int,
        sandbox_session_id: str = None,
    ) -> List[Dict[str, str]]:
        """
        Sync all uploaded files for a session from OSS to Sandbox.
        
        Returns:
            List of synced files with their sandbox paths
        """
        import time
        synced = []
        sandbox_session_id = sandbox_session_id or session_id
        await self.prepare_workspace_for_session(session_id, sandbox_session_id)
        
        # Query uploaded files for this session from database
        db_files = db.query(UploadedFile).filter(
            UploadedFile.user_id == user_id,
            (UploadedFile.conversation_id == session_id) | 
            (UploadedFile.filename.like(f"%/{session_id}/%"))
        ).all()
        print(f"[SYNC] Found {len(db_files)} files to sync for session {session_id}")

        if self._is_local_mode():
            workspace = self._local_workspace(session_id)
            self._copy_local_skills(session_id)
            if session_id not in self._synced_files:
                self._synced_files[session_id] = {}

            for db_file in db_files:
                source_path = Path(db_file.file_path)
                if not source_path.exists():
                    print(f"[SYNC] Local file missing, skipping: {source_path}")
                    continue
                safe_filename = re.sub(r"[^A-Za-z0-9._ -]", "_", db_file.original_name or source_path.name)
                target_path = workspace / safe_filename
                if source_path.resolve() != target_path.resolve():
                    shutil.copy2(source_path, target_path)
                self._synced_files[session_id][safe_filename] = str(target_path)
                synced.append({
                    "filename": safe_filename,
                    "sandbox_path": str(target_path),
                    "oss_url": str(target_path),
                    "generated": False,
                })
            print(f"[SYNC] Completed local sync: {len(synced)} files")
            return synced
        
        # Initialize session tracking
        if session_id not in self._synced_files:
            self._synced_files[session_id] = {}
        
        # Create workspace directory in sandbox
        print(f"[SYNC] Step 1: Getting sandbox service...")
        t0 = time.time()
        from app.services.opensandbox_service import get_opensandbox_service
        opensandbox = get_opensandbox_service()
        print(f"[SYNC] Step 1 done: {time.time()-t0:.2f}s")
        
        print(f"[SYNC] Step 2: Creating workspace directory...")
        t0 = time.time()
        mkdir_result = await opensandbox.execute_shell(f"mkdir -p {SANDBOX_WORK_DIR}", sandbox_session_id, timeout=20)
        if not mkdir_result.get("success"):
            print(f"[SYNC] Workspace setup failed, recreating sandbox session: {mkdir_result.get('stderr', '')}")
            await opensandbox.cleanup_session(sandbox_session_id)
            self._synced_files[session_id] = {}
            mkdir_result = await opensandbox.execute_shell(f"mkdir -p {SANDBOX_WORK_DIR}", sandbox_session_id, timeout=30)
        if not mkdir_result.get("success"):
            print(f"[SYNC] ERROR: Failed to create workspace: {mkdir_result.get('stderr', '')}")
            return synced
        print(f"[SYNC] Step 2 done: {time.time()-t0:.2f}s")

        await self._ensure_skills(opensandbox, sandbox_session_id)

        cache_generation = (
            sandbox_session_id,
            opensandbox.get_session_generation(sandbox_session_id),
        )
        if self._sync_cache_generation.get(session_id) != cache_generation:
            print(f"[SYNC] Sandbox generation changed for session {session_id}; forcing file resync")
            self._synced_files[session_id] = {}
            self._sync_cache_generation[session_id] = cache_generation

        if not db_files:
            return synced
        
        for db_file in db_files:
            sandbox_path, is_generated_artifact = self._sandbox_restore_path(db_file, user_id, session_id)
            filename = sandbox_path.rsplit("/", 1)[-1]
            cache_key = db_file.filename if is_generated_artifact else filename
            print(f"[SYNC] Processing file: {filename}")
            
            # Skip if already synced
            if cache_key in self._synced_files[session_id]:
                sandbox_path = self._synced_files[session_id][cache_key]
                check_result = await opensandbox.execute_shell(
                    f"test -f {shlex.quote(sandbox_path)}",
                    sandbox_session_id,
                    timeout=10,
                )
                if check_result.get("success"):
                    print(f"[SYNC] File already synced, skipping")
                    synced.append({
                        "filename": filename,
                        "sandbox_path": sandbox_path,
                        "oss_url": db_file.file_path,
                        "generated": is_generated_artifact,
                    })
                    continue

                print(f"[SYNC] Cached file missing in sandbox, resyncing: {filename}")
                self._synced_files[session_id].pop(cache_key, None)
            
            # Download from OSS to memory
            try:
                print(f"[SYNC] Step 3: Downloading from OSS...")
                t0 = time.time()
                if db_file.file_path.startswith("http"):
                    # It's an OSS URL, extract object name
                    object_name = extract_oss_object_name(db_file.file_path)
                    file_data = await self._get_oss_service().download_file(object_name)
                else:
                    # Local file, read directly
                    with open(db_file.file_path, 'rb') as f:
                        file_data = f.read()
                print(f"[SYNC] Step 3 done: {time.time()-t0:.2f}s, size={len(file_data)} bytes")
                
                # Write to sandbox using OpenSandbox files API (fastest method)
                from opensandbox.models import WriteEntry
                parent_dir = posixpath.dirname(sandbox_path)
                if parent_dir:
                    await opensandbox.execute_shell(f"mkdir -p {shlex.quote(parent_dir)}", sandbox_session_id, timeout=20)
                
                print(f"[SYNC] Step 4: Writing to sandbox...")
                t0 = time.time()
                # Use OpenSandbox files API - much faster than Python execute
                # Need to get session first to access sandbox
                # For text files (CSV), decode as utf-8; for binary, we'd need different handling
                try:
                    file_text = file_data.decode('utf-8')
                    # Get or create session to access sandbox
                    session = await opensandbox._get_or_create_session(sandbox_session_id)
                    await session.sandbox.files.write_files([
                        WriteEntry(path=sandbox_path, data=file_text, mode=644)
                    ])
                except UnicodeDecodeError:
                    # Binary file - use base64 via Python execute
                    print(f"[SYNC] Binary file detected, using Python fallback...")
                    import base64
                    encoded = base64.b64encode(file_data).decode('utf-8')
                    write_code = f'''
import base64
data = base64.b64decode('{encoded}')
with open('{sandbox_path}', 'wb') as f:
    f.write(data)
'''
                    result = await opensandbox.execute_python(write_code, sandbox_session_id, timeout=120)
                    if not result.get('success'):
                        raise Exception(f"Failed to write binary file: {result.get('stderr', 'Unknown error')}")
                print(f"[SYNC] Step 4 done: {time.time()-t0:.2f}s")
                
                self._synced_files[session_id][cache_key] = sandbox_path
                synced.append({
                    "filename": filename,
                    "sandbox_path": sandbox_path,
                    "oss_url": db_file.file_path,
                    "generated": is_generated_artifact,
                })
                print(f"[SYNC] File {filename} synced successfully")
                
            except Exception as e:
                print(f"[SYNC] ERROR: Failed to sync file {filename}: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"[SYNC] Completed: {len(synced)} files synced")
        return synced
    
    async def download_file_to_sandbox(
        self,
        session_id: str,
        file_url: str,
        filename: str,
        sandbox_session_id: str = None,
    ) -> Optional[str]:
        """
        Download a file from OSS URL to sandbox.
        
        Returns:
            Sandbox path if successful, None otherwise
        """
        try:
            from app.services.opensandbox_service import get_opensandbox_service
            opensandbox = get_opensandbox_service()
            sandbox_session_id = sandbox_session_id or session_id
            
            # Download from OSS
            if file_url.startswith("http"):
                object_name = extract_oss_object_name(file_url)
                file_data = await self._get_oss_service().download_file(object_name)
            else:
                with open(file_url, 'rb') as f:
                    file_data = f.read()
            
            # Write to sandbox using shell command for binary files
            import base64
            encoded = base64.b64encode(file_data).decode('utf-8')
            sandbox_path = f"{SANDBOX_WORK_DIR}/{filename}"
            
            # Create directory first
            await opensandbox.execute_shell(f"mkdir -p {SANDBOX_WORK_DIR}", sandbox_session_id)
            
            # Write file using base64 decoding
            write_cmd = f"echo '{encoded}' | base64 -d > '{sandbox_path}'"
            result = await opensandbox.execute_shell(write_cmd, sandbox_session_id)
            
            if not result["success"]:
                # Fallback: try text mode for text files
                try:
                    text_content = file_data.decode('utf-8')
                    await opensandbox.write_file(sandbox_path, text_content, sandbox_session_id)
                except:
                    print(f"Failed to write file to sandbox: {result['stderr']}")
                    return None
            
            # Track synced file
            if session_id not in self._synced_files:
                self._synced_files[session_id] = {}
            self._synced_files[session_id][filename] = sandbox_path
            
            return sandbox_path
            
        except Exception as e:
            print(f"Failed to download file to sandbox: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def upload_generated_file(
        self,
        session_id: str,
        sandbox_path: str,
        filename: str,
        user_id: int,
        db: Session,
        sandbox_session_id: str = None,
    ) -> Optional[str]:
        """
        Upload a file generated in sandbox to OSS.
        
        Returns:
            OSS URL if successful, None otherwise
        """
        try:
            if self._is_local_mode():
                source_path = Path(sandbox_path)
                if not source_path.is_absolute():
                    source_path = self._local_workspace(session_id) / sandbox_path
                source_path = source_path.resolve()
                workspace = self._local_workspace(session_id).resolve()
                try:
                    source_path.relative_to(workspace)
                except ValueError:
                    print(f"Skipping file outside local workspace: {source_path}")
                    return None
                if not source_path.exists() or not source_path.is_file():
                    print(f"Generated local file not found: {source_path}")
                    return None
                if source_path == self._local_skills_dir(session_id) or self._local_skills_dir(session_id) in source_path.parents:
                    print(f"Skipping internal skill file upload: {source_path}")
                    return None

                relative_path = source_path.relative_to(workspace).as_posix()
                object_name = f"generated/{user_id}/{session_id}/{relative_path}"
                file_size = source_path.stat().st_size
                mime_type = self._guess_mime_type(source_path.name)
                local_url = f"/api/v1/files/content?url={source_path}"

                try:
                    existing = db.query(UploadedFile).filter(
                        UploadedFile.user_id == user_id,
                        UploadedFile.conversation_id == session_id,
                        UploadedFile.filename == object_name,
                    ).first()
                    if existing:
                        existing.file_path = str(source_path)
                        existing.file_size = file_size
                        existing.mime_type = mime_type
                    else:
                        db.add(UploadedFile(
                            user_id=user_id,
                            conversation_id=session_id,
                            filename=object_name,
                            original_name=source_path.name,
                            file_path=str(source_path),
                            file_size=file_size,
                            mime_type=mime_type,
                        ))
                    db.commit()
                except Exception as db_e:
                    db.rollback()
                    print(f"Database error (non-fatal): {db_e}")
                return local_url

            normalized_sandbox_path = sandbox_path.replace("\\", "/")
            if (
                normalized_sandbox_path == SANDBOX_SKILLS_DIR
                or normalized_sandbox_path.startswith(f"{SANDBOX_SKILLS_DIR}/")
            ):
                print(f"Skipping internal skill file upload: {sandbox_path}")
                return None

            from app.services.opensandbox_service import get_opensandbox_service
            opensandbox = get_opensandbox_service()
            sandbox_session_id = sandbox_session_id or session_id
            
            # Read file from sandbox using base64 for binary support
            quoted_path = shlex.quote(sandbox_path)
            # Use unwrapped base64 and disable normal stdout truncation. Generated
            # PDFs with embedded charts can exceed MAX_OUTPUT_LENGTH; truncating
            # the base64 stream silently corrupts the uploaded file.
            result = await opensandbox.execute_shell(
                f"base64 -w 0 {quoted_path}",
                sandbox_session_id,
                max_output_length=100_000_000,
            )
            if not result.get('success'):
                print(f"Failed to read file from sandbox: {result.get('stderr')}")
                return None
            
            # Decode base64 to bytes
            import base64
            # Remove any whitespace/newlines from base64 output
            b64_data = ''.join(result['stdout'].strip().split())
            # Fix padding if necessary
            padding_needed = 4 - len(b64_data) % 4
            if padding_needed != 4:
                b64_data += '=' * padding_needed
            try:
                # Try with validate=False first (more lenient)
                file_data = base64.b64decode(b64_data, validate=False)
            except Exception as e:
                print(f"Base64 decode error for {filename}: {e}")
                print(f"Base64 length: {len(b64_data)}, first 100 chars: {b64_data[:100]}")
                # Try alternative: read directly from sandbox
                try:
                    # Try to read file using Python in sandbox
                    py_result = await opensandbox.execute_python(
                        f"import base64; f=open({sandbox_path!r},'rb'); print(base64.b64encode(f.read()).decode()); f.close()",
                        sandbox_session_id
                    )
                    if py_result.get('stdout'):
                        b64_data = ''.join(py_result['stdout'].strip().split())
                        padding_needed = 4 - len(b64_data) % 4
                        if padding_needed != 4:
                            b64_data += '=' * padding_needed
                        file_data = base64.b64decode(b64_data, validate=False)
                        print(f"Fallback read succeeded for {filename}")
                    else:
                        return None
                except Exception as e2:
                    print(f"Fallback read also failed for {filename}: {e2}")
                    return None

            if filename.lower().endswith(".pdf") and not file_data.startswith(b"%PDF"):
                print(f"Decoded PDF does not start with %PDF, refusing corrupt upload: {filename}")
                return None
            
            # Upload to OSS
            object_name = self._generated_object_name(user_id, session_id, sandbox_path, filename)
            oss_service = self._get_oss_service()
            await oss_service.upload_file(
                file_data,
                object_name,
                self._guess_mime_type(filename)
            )

            # Do not trust a returned URL until OSS confirms the object exists.
            # This prevents stale DB/file-list entries that point to NoSuchKey.
            import asyncio
            upload_verified = False
            for attempt in range(3):
                try:
                    if await oss_service.file_exists(object_name):
                        upload_verified = True
                        break
                except Exception as exists_e:
                    print(f"OSS existence check failed for {object_name} (attempt {attempt + 1}): {exists_e}")
                if attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))

            if not upload_verified:
                print(f"OSS upload verification failed for {object_name}; skipping DB save")
                return None
            
            # Generate signed URL for long-term access (10 years expiry)
            # Note: URL contains AccessKey ID which is normal for signed URLs
            # The signature ensures only this specific file can be accessed
            oss_url = await oss_service.generate_download_url(object_name, expires=10*365*24*3600)
            
            # Save to database (check if already exists first)
            try:
                # Check if file already exists in database for this user/session/filename
                existing = db.query(UploadedFile).filter(
                    UploadedFile.user_id == user_id,
                    UploadedFile.conversation_id == session_id,
                    UploadedFile.filename == object_name
                ).first()
                
                if existing:
                    # Update existing record with new URL and size
                    existing.file_path = oss_url
                    existing.file_size = len(file_data)
                    db.commit()
                    print(f"Updated existing file in database: {filename}")
                else:
                    # Create new record
                    uploaded_file = UploadedFile(
                        user_id=user_id,
                        conversation_id=session_id,
                        filename=object_name,
                        original_name=filename,
                        file_path=oss_url,
                        file_size=len(file_data),
                        mime_type=self._guess_mime_type(filename)
                    )
                    db.add(uploaded_file)
                    db.commit()
                    print(f"Saved to database: {filename} -> {object_name}")
            except Exception as db_e:
                db.rollback()
                print(f"Database error (non-fatal): {db_e}")
                # Still return URL even if DB save fails
            
            return oss_url
            
        except Exception as e:
            print(f"Failed to upload generated file: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _guess_mime_type(self, filename: str) -> str:
        """Guess MIME type from filename."""
        ext = Path(filename).suffix.lower()
        mime_types = {
            '.csv': 'text/csv',
            '.json': 'application/json',
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.pdf': 'application/pdf',
            '.html': 'text/html',
            '.svg': 'image/svg+xml',
            '.webp': 'image/webp',
            '.py': 'text/x-python',
            '.ipynb': 'application/json',
        }
        return mime_types.get(ext, 'application/octet-stream')
    
    def get_file_sandbox_path(self, session_id: str, filename: str) -> Optional[str]:
        """Get the sandbox path for a synced file."""
        if session_id in self._synced_files:
            return self._synced_files[session_id].get(filename)
        return None
    
    def get_all_synced_files(self, session_id: str) -> Dict[str, str]:
        """Get all synced files for a session."""
        return self._synced_files.get(session_id, {})

    def is_sync_current(self, session_id: str, sandbox_session_id: str, generation: int) -> bool:
        """Return whether this session's cached sandbox file map matches the live sandbox generation."""
        return (
            bool(self._synced_files.get(session_id))
            and self._sync_cache_generation.get(session_id) == (sandbox_session_id, generation)
        )
    
    async def cleanup_session(self, session_id: str):
        """Clean up synced files tracking for a session."""
        if session_id in self._synced_files:
            del self._synced_files[session_id]
        self._sync_cache_generation.pop(session_id, None)


# Global instance
_sandbox_file_manager: Optional[SandboxFileManager] = None


def get_sandbox_file_manager() -> SandboxFileManager:
    """Get SandboxFileManager instance."""
    global _sandbox_file_manager
    if _sandbox_file_manager is None:
        _sandbox_file_manager = SandboxFileManager()
    return _sandbox_file_manager
