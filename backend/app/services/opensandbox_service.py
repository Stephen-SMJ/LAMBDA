"""OpenSandbox code execution service for secure code execution."""

import asyncio
import os
import time
import uuid
from typing import Dict, Any, Optional, List
from datetime import timedelta
from pathlib import Path
from functools import partial

from app.core.config import settings
from app.services.oss_service import get_oss_service

# Import OpenSandbox SDK
try:
    from opensandbox import Sandbox
    from opensandbox.config.connection import ConnectionConfig
    from code_interpreter import CodeInterpreter, SupportedLanguage
    from opensandbox.models import WriteEntry
    OPENSANDBOX_AVAILABLE = True
except ImportError:
    OPENSANDBOX_AVAILABLE = False


# Default connection config for local server
DEFAULT_CONNECTION_CONFIG = ConnectionConfig(
    domain="127.0.0.1:8080",
    protocol="http",
    request_timeout=timedelta(seconds=300),
)

# Data science packages to pre-install
PRE_INSTALLED_PACKAGES = [
    "pandas==2.2.3",
    "numpy==2.1.3",
    "scipy==1.15.3",
    "matplotlib==3.9.2",
    "seaborn==0.13.2",
    "scikit-learn==1.5.2",
    "statsmodels==0.14.4",
    "openpyxl==3.1.5",
    "xlrd==2.0.1",
    "plotly==5.24.1",
    "python-pptx==1.0.2",
]


class NotebookSession:
    """Persistent notebook session using OpenSandbox."""
    
    def __init__(self, session_id: str, sandbox: Sandbox, interpreter: CodeInterpreter):
        self.session_id = session_id
        self.sandbox = sandbox
        self.interpreter = interpreter
        self.execution_count = 0
        self.variables = {}
        self.packages_installed = False  # Track if packages are installed
        self.generation = 0
        self.last_used_at = time.monotonic()
    
    async def ensure_packages(self):
        """Install data science packages if not already installed."""
        import time

        if settings.SANDBOX_PREINSTALLED_PACKAGES:
            self.packages_installed = True
            print("[PACKAGES] Using preinstalled packages from sandbox image")
            return True
        
        if self.packages_installed:
            print(f"[PACKAGES] Already installed, skipping")
            return True
        
        print(f"[PACKAGES] Step 1: Checking if pandas is available...")
        t0 = time.time()
        try:
            check_result = await self.interpreter.codes.run(
                "import pandas; print('pandas_available')",
                language=SupportedLanguage.PYTHON,
            )
            
            # If pandas is available, mark as installed
            if any('pandas_available' in (log.text if hasattr(log, 'text') else str(log)) 
                   for log in (check_result.logs.stdout if check_result.logs else [])):
                print(f"[PACKAGES] Step 1 done: {time.time()-t0:.2f}s - pandas already available")
                self.packages_installed = True
                return True
            print(f"[PACKAGES] Step 1 done: {time.time()-t0:.2f}s - pandas not found")
        except Exception as e:
            print(f"[PACKAGES] Step 1 failed: {e}")
        
        # Install packages using the Python interpreter directly
        print(f"[PACKAGES] Step 2: Installing packages {PRE_INSTALLED_PACKAGES}...")
        t0 = time.time()
        try:
            # Use python -m pip to install packages with --break-system-packages
            install_code = f'''
import subprocess
import sys

print(f"[PACKAGES] Running pip install...")
result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "--break-system-packages", "--no-cache-dir"] + {PRE_INSTALLED_PACKAGES},
    capture_output=True,
    text=True,
    timeout=300
)

print("STDOUT:", result.stdout[-1000:] if len(result.stdout) > 1000 else result.stdout)
print("STDERR:", result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
print("Return code:", result.returncode)
'''
            result = await self.interpreter.codes.run(
                install_code,
                language=SupportedLanguage.PYTHON,
            )
            print(f"[PACKAGES] Step 2 done: {time.time()-t0:.2f}s")
            
            print(f"[PACKAGES] Step 3: Verifying installation...")
            t0 = time.time()
            # Check if installation was successful by trying to import pandas again
            check_result = await self.interpreter.codes.run(
                "import pandas; print('pandas_installed')",
                language=SupportedLanguage.PYTHON,
            )
            
            if any('pandas_installed' in (log.text if hasattr(log, 'text') else str(log))
                   for log in (check_result.logs.stdout if check_result.logs else [])):
                print(f"[PACKAGES] Step 3 done: {time.time()-t0:.2f}s - installation successful")
                self.packages_installed = True
                return True
            else:
                print(f"[PACKAGES] ERROR: Installation verification failed")
                return False
                
        except Exception as e:
            print(f"[PACKAGES] ERROR: Failed to install packages: {e}")
            import traceback
            traceback.print_exc()
            return False


class OpenSandboxService:
    """Service for executing code in OpenSandbox environment."""
    
    def __init__(self):
        self.timeout = settings.CODE_EXECUTION_TIMEOUT
        self.max_output_length = settings.MAX_OUTPUT_LENGTH
        # Allow custom sandbox image via environment variable
        self.sandbox_image = getattr(settings, 'SANDBOX_IMAGE', 'opensandbox/code-interpreter:v1.0.2')
        self._sessions: Dict[str, NotebookSession] = {}
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._session_generations: Dict[str, int] = {}
        self._executor = None
        self._connection_config = DEFAULT_CONNECTION_CONFIG
    
    def _ensure_executor(self):
        """Ensure thread pool executor exists."""
        if self._executor is None:
            from concurrent.futures import ThreadPoolExecutor
            self._executor = ThreadPoolExecutor(max_workers=10)
        return self._executor

    def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        """Serialize interpreter access per session to avoid kernel busy errors."""
        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
        return self._session_locks[session_id]

    def get_session_generation(self, session_id: str) -> int:
        """Return the current kernel/container generation for a session."""
        return self._session_generations.get(session_id, 0)

    async def _is_session_alive(self, session: NotebookSession) -> bool:
        """Confirm a sandbox session is alive without overreacting to one flaky ping."""
        for attempt in range(2):
            try:
                await asyncio.wait_for(
                    session.sandbox.commands.run("echo ping"),
                    timeout=5.0,
                )
                return True
            except Exception as e:
                print(f"Health check failed for session {session.session_id} (attempt {attempt + 1}/2): {e}")
                if attempt == 0:
                    await asyncio.sleep(0.25)
        return False
    
    async def _get_or_create_session(self, session_id: str) -> NotebookSession:
        """Get or create a notebook session."""
        if not OPENSANDBOX_AVAILABLE:
            raise RuntimeError("OpenSandbox SDK not available")
        
        if session_id in self._sessions:
            session = self._sessions[session_id]
            # Do not proactively ping and kill sessions here. The ping itself can
            # falsely classify a busy or transiently slow sandbox as dead. Reuse
            # the cached session and let the actual command path handle real
            # connection failures.
            return session
        
        # Create new sandbox with connection config. OpenSandbox's timeout acts
        # like a container TTL, not an idle timeout. App-level idle cleanup is
        # handled by cleanup_idle_sessions().
        container_timeout = getattr(settings, 'SANDBOX_CONTAINER_TIMEOUT_MINUTES', 1440)
        print(f"Creating new sandbox session: {session_id} (container TTL: {container_timeout} minutes)")
        sandbox = await Sandbox.create(
            self.sandbox_image,
            entrypoint=["/opt/opensandbox/code-interpreter.sh"],
            env={"PYTHON_VERSION": "3.11"},
            timeout=timedelta(minutes=container_timeout),
            connection_config=self._connection_config,
        )
        
        # Create interpreter
        interpreter = await CodeInterpreter.create(sandbox)
        
        # Create session
        session = NotebookSession(session_id, sandbox, interpreter)
        session.generation = self._session_generations.get(session_id, 0) + 1
        self._session_generations[session_id] = session.generation
        self._sessions[session_id] = session
        
        return session
    
    async def execute_python(
        self, 
        code: str, 
        session_id: str = "default",
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute Python code in OpenSandbox.
        """
        if not OPENSANDBOX_AVAILABLE:
            return {
                "success": False,
                "stdout": "",
                "stderr": "OpenSandbox is not available. Please install opensandbox-sdk and opensandbox-code-interpreter.",
                "exit_code": -1,
                "execution_time": 0,
                "images": []
            }
        
        timeout = timeout or self.timeout
        start_time = asyncio.get_event_loop().time()
        generation_before = self.get_session_generation(session_id)
        had_existing_session = session_id in self._sessions
        
        try:
            async with self._get_session_lock(session_id):
                # Get or create session
                session = await self._get_or_create_session(session_id)
                
                # Ensure packages are installed
                await session.ensure_packages()
                
                # Escape backslashes for Jupyter protocol
                # Jupyter interprets \n as newline, so we need to escape it to \\n
                escaped_code = code.replace('\\', '\\\\')
                
                # Execute code with an application-level timeout. The OpenSandbox
                # request can occasionally hang below the SDK layer, so do not rely
                # on the SDK/client timeout alone.
                result = await asyncio.wait_for(
                    session.interpreter.codes.run(
                        escaped_code,
                        language=SupportedLanguage.PYTHON,
                    ),
                    timeout=timeout,
                )
                session.last_used_at = time.monotonic()
            
            execution_time = asyncio.get_event_loop().time() - start_time
            generation_after = self.get_session_generation(session_id)
            kernel_restarted = had_existing_session and generation_after != generation_before
            
            # Process output
            stdout_lines = []
            stderr_lines = []
            
            if result.logs:
                if result.logs.stdout:
                    for log in result.logs.stdout:
                        text = log.text if hasattr(log, 'text') else str(log)
                        stdout_lines.append(text)
                
                if result.logs.stderr:
                    for log in result.logs.stderr:
                        text = log.text if hasattr(log, 'text') else str(log)
                        stderr_lines.append(text)
            
            stdout = "\n".join(stdout_lines)
            stderr = "\n".join(stderr_lines)
            
            # Truncate output if too long
            if len(stdout) > self.max_output_length:
                stdout = stdout[:self.max_output_length] + "\n... (output truncated)"
            if len(stderr) > self.max_output_length:
                stderr = stderr[:self.max_output_length] + "\n... (error output truncated)"
            
            # Get result value
            result_value = ""
            if result.result:
                for r in result.result:
                    text = r.text if hasattr(r, 'text') else str(r)
                    if text:
                        result_value += text + "\n"
                if result_value:
                    stdout = stdout + "\n" + result_value.strip() if stdout else result_value.strip()
            
            # Get exit code - it's on the result object directly
            exit_code = 0
            if hasattr(result, 'exit_code') and result.exit_code is not None:
                exit_code = result.exit_code
            elif result.error:
                exit_code = 1
            
            # Capture error information if present
            if result.error:
                error_info = f"Error: {result.error.name} - {result.error.value}"
                if result.error.traceback:
                    error_info += f"\nTraceback:\n{''.join(result.error.traceback)}"
                stderr = error_info + "\n" + stderr if stderr else error_info
            
            return {
                "success": exit_code == 0 and result.error is None,
                "stdout": stdout.strip(),
                "stderr": stderr,
                "exit_code": exit_code,
                "execution_time": round(execution_time, 3),
                "images": [],
                "kernel_restarted": kernel_restarted,
                "session_generation": generation_after,
            }
            
        except asyncio.TimeoutError:
            await self.cleanup_session(session_id)
            generation_after = self.get_session_generation(session_id)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout} seconds",
                "exit_code": -1,
                "execution_time": timeout,
                "images": [],
                "kernel_restarted": generation_after != generation_before or had_existing_session,
                "session_generation": generation_after,
            }
        except Exception as e:
            error_msg = str(e).lower()
            # Check for connection-related errors
            is_connection_error = any(err in error_msg for err in [
                'connection', 'network', 'refused', 'reset', 'closed',
                'unable to connect', 'all connection attempts failed'
            ])
            
            if is_connection_error:
                print(f"Connection lost for session {session_id}, cleaning up dead session...")
                # Clean up the dead session
                await self.cleanup_session(session_id)
            generation_after = self.get_session_generation(session_id)
            
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution error: {str(e)}\n\nNote: Sandbox session may have expired due to inactivity. Please retry your request.",
                "exit_code": -1,
                "execution_time": asyncio.get_event_loop().time() - start_time,
                "images": [],
                "kernel_restarted": bool(is_connection_error and (generation_after != generation_before or had_existing_session)),
                "session_generation": generation_after,
            }
    
    async def execute_shell(
        self, 
        command: str, 
        session_id: str = "default",
        timeout: Optional[int] = None,
        max_output_length: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute shell command in OpenSandbox.
        """
        if not OPENSANDBOX_AVAILABLE:
            return {
                "success": False,
                "stdout": "",
                "stderr": "OpenSandbox is not available",
                "exit_code": -1,
                "execution_time": 0,
                "images": []
            }
        
        # Block dangerous commands
        dangerous_commands = [
            'rm -rf /', 'mkfs.', 'dd if=/dev/zero', ':(){ :|:& };:',
            '> /dev/sda', 'curl', 'wget', 'nc ', 'netcat',
            'bash -i', 'sh -i', 'python -c', 'python3 -c'
        ]
        
        for dangerous in dangerous_commands:
            if dangerous in command.lower():
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Command blocked for security reasons: {dangerous}",
                    "exit_code": -1,
                    "execution_time": 0,
                    "images": []
                }
        
        timeout = timeout or self.timeout
        start_time = asyncio.get_event_loop().time()
        generation_before = self.get_session_generation(session_id)
        had_existing_session = session_id in self._sessions
        
        try:
            async with self._get_session_lock(session_id):
                # Get or create session
                session = await self._get_or_create_session(session_id)
                sandbox = session.sandbox
                
                # Execute command with an application-level timeout. The SDK
                # can otherwise block for a long time on a dead sandbox stream.
                execution = await asyncio.wait_for(
                    sandbox.commands.run(command),
                    timeout=timeout,
                )
                session.last_used_at = time.monotonic()
            
            execution_time = asyncio.get_event_loop().time() - start_time
            generation_after = self.get_session_generation(session_id)
            kernel_restarted = had_existing_session and generation_after != generation_before
            
            # Process output - Fix: exit_code is on Execution, not ExecutionLogs
            stdout_lines = []
            stderr_lines = []
            
            if execution.logs:
                if execution.logs.stdout:
                    for log in execution.logs.stdout:
                        text = log.text if hasattr(log, 'text') else str(log)
                        stdout_lines.append(text)
                
                if execution.logs.stderr:
                    for log in execution.logs.stderr:
                        text = log.text if hasattr(log, 'text') else str(log)
                        stderr_lines.append(text)
            
            stdout = "\n".join(stdout_lines)
            stderr = "\n".join(stderr_lines)
            
            # Truncate output if too long
            output_limit = max_output_length or self.max_output_length
            if output_limit and len(stdout) > output_limit:
                stdout = stdout[:output_limit] + "\n... (output truncated)"
            if output_limit and len(stderr) > output_limit:
                stderr = stderr[:output_limit] + "\n... (error output truncated)"
            
            # Get exit code - it's on the execution object directly
            exit_code = 0
            if hasattr(execution, 'exit_code') and execution.exit_code is not None:
                exit_code = execution.exit_code
            elif execution.error:
                exit_code = 1
            
            return {
                "success": exit_code == 0 and execution.error is None,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "execution_time": round(execution_time, 3),
                "images": [],
                "kernel_restarted": kernel_restarted,
                "session_generation": generation_after,
            }
            
        except asyncio.TimeoutError:
            await self.cleanup_session(session_id)
            generation_after = self.get_session_generation(session_id)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout} seconds",
                "exit_code": -1,
                "execution_time": timeout,
                "images": [],
                "kernel_restarted": generation_after != generation_before or had_existing_session,
                "session_generation": generation_after,
            }
        except Exception as e:
            import traceback
            error_msg = str(e).lower()
            is_connection_error = any(err in error_msg for err in [
                'connection', 'network', 'refused', 'reset', 'closed',
                'unable to connect', 'all connection attempts failed',
                'incomplete chunked read', 'remoteprotocolerror',
            ])

            if is_connection_error:
                print(f"Shell connection lost for session {session_id}, cleaning up dead session...")
                await self.cleanup_session(session_id)
            generation_after = self.get_session_generation(session_id)

            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution error: {str(e)}\n{traceback.format_exc()}",
                "exit_code": -1,
                "execution_time": asyncio.get_event_loop().time() - start_time,
                "images": [],
                "kernel_restarted": bool(is_connection_error and (generation_after != generation_before or had_existing_session)),
                "session_generation": generation_after,
            }
    
    async def write_file(
        self, 
        path: str, 
        content: str, 
        session_id: str = "default"
    ) -> bool:
        """Write a file to the sandbox."""
        if not OPENSANDBOX_AVAILABLE:
            return False
        
        try:
            session = await self._get_or_create_session(session_id)
            await session.sandbox.files.write_files([
                WriteEntry(path=path, data=content, mode=644)
            ])
            return True
        except Exception:
            return False
    
    async def read_file(self, path: str, session_id: str = "default") -> Optional[str]:
        """Read a file from the sandbox."""
        if not OPENSANDBOX_AVAILABLE:
            return None
        
        try:
            session = await self._get_or_create_session(session_id)
            content = await session.sandbox.files.read_file(path)
            return content
        except Exception:
            return None
    
    async def cleanup_session(self, session_id: str):
        """Clean up sandbox for a session."""
        if session_id in self._sessions:
            session = self._sessions[session_id]
            try:
                await session.sandbox.kill()
            except:
                pass
            del self._sessions[session_id]
            self._session_generations[session_id] = self._session_generations.get(session_id, 0) + 1
        self._session_locks.pop(session_id, None)
    
    async def cleanup_all_sessions(self):
        """Clean up all sessions."""
        for session_id in list(self._sessions.keys()):
            await self.cleanup_session(session_id)

    async def cleanup_orphan_containers_on_startup(self):
        """Stop sandbox containers left behind by a previous backend process.

        OpenSandbox sessions are tracked in this Python process. If the backend
        restarts, old Docker containers can keep running but are no longer
        reachable through _sessions, so normal idle cleanup cannot reap them.
        Startup is the safe point to clear those orphans because in-flight
        requests from the previous process are already gone.
        """
        if not getattr(settings, "SANDBOX_CLEANUP_ORPHANS_ON_STARTUP", True):
            return

        try:
            list_proc = await asyncio.create_subprocess_exec(
                "docker",
                "ps",
                "--format",
                "{{.ID}}\t{{.Names}}\t{{.Image}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await list_proc.communicate()
            if list_proc.returncode != 0:
                message = stderr.decode("utf-8", errors="replace").strip()
                print(f"Sandbox orphan cleanup skipped: docker ps failed: {message}")
                return

            container_ids = []
            for line in stdout.decode("utf-8", errors="replace").splitlines():
                parts = line.split("\t", 2)
                if len(parts) != 3:
                    continue
                container_id, name, image = parts
                if image == self.sandbox_image and name.startswith("sandbox-"):
                    container_ids.append(container_id)

            if not container_ids:
                return

            stop_proc = await asyncio.create_subprocess_exec(
                "docker",
                "stop",
                *container_ids,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stop_stderr = await stop_proc.communicate()
            if stop_proc.returncode == 0:
                print(f"Stopped {len(container_ids)} orphan sandbox container(s) on startup")
            else:
                message = stop_stderr.decode("utf-8", errors="replace").strip()
                print(f"Sandbox orphan cleanup failed: docker stop failed: {message}")
        except FileNotFoundError:
            print("Sandbox orphan cleanup skipped: docker command not found")
        except Exception as exc:
            print(f"Sandbox orphan cleanup failed: {exc}")

    async def cleanup_idle_sessions(self):
        """Clean up sessions idle longer than SANDBOX_IDLE_TIMEOUT_MINUTES."""
        idle_timeout = getattr(settings, 'SANDBOX_IDLE_TIMEOUT_MINUTES', 30) * 60
        now = time.monotonic()
        for session_id, session in list(self._sessions.items()):
            idle_for = now - session.last_used_at
            if idle_for >= idle_timeout:
                print(f"Cleaning up idle sandbox session {session_id} after {idle_for:.0f}s")
                await self.cleanup_session(session_id)


# Global OpenSandbox service instance
_opensandbox_service: Optional[OpenSandboxService] = None


def get_opensandbox_service() -> OpenSandboxService:
    """Get OpenSandbox service instance."""
    global _opensandbox_service
    if _opensandbox_service is None:
        _opensandbox_service = OpenSandboxService()
    return _opensandbox_service
