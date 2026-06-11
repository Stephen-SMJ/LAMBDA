"""Local tool execution for the open-source build.

This intentionally runs on the host machine. It keeps Python variables alive per
conversation while constraining relative file work to a conversation workspace.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import os
import shlex
import subprocess
import time
import uuid
from pathlib import Path
from threading import RLock
from typing import Any, Dict

from app.core.config import settings
from app.utils.text import strip_ansi_escape_codes


class LocalCodeExecutionService:
    """Execute Python and shell commands in local per-session workspaces."""

    def __init__(self):
        self.timeout = settings.CODE_EXECUTION_TIMEOUT
        self.max_output_length = settings.MAX_OUTPUT_LENGTH
        self._globals: dict[str, dict[str, Any]] = {}
        self._locks: dict[str, RLock] = {}

    def workspace_for_session(self, session_id: str) -> Path:
        workspace = Path(settings.LOCAL_WORKSPACE_ROOT).resolve() / str(session_id)
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout: int | None = None,
        session_id: str = "default",
        cwd: str | Path | None = None,
    ) -> Dict[str, Any]:
        timeout = timeout or self.timeout
        workspace = Path(cwd).resolve() if cwd else self.workspace_for_session(session_id)
        workspace.mkdir(parents=True, exist_ok=True)

        if language == "python":
            return await self._execute_python(code, timeout, session_id, workspace)
        if language in {"bash", "shell"}:
            return await self._execute_shell(code, timeout, workspace)
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Unsupported language: {language}",
            "exit_code": -1,
            "execution_time": 0,
            "images": [],
            "generated_files": [],
        }

    async def _execute_python(self, code: str, timeout: int, session_id: str, workspace: Path) -> Dict[str, Any]:
        start = time.time()
        lock = self._locks.setdefault(session_id, RLock())
        return await asyncio.to_thread(self._execute_python_sync, code, timeout, session_id, workspace, start, lock)

    def _execute_python_sync(
        self,
        code: str,
        timeout: int,
        session_id: str,
        workspace: Path,
        start: float,
        lock: RLock,
    ) -> Dict[str, Any]:
        # In-process execution keeps variables alive. Timeout is advisory for
        # local mode because Python threads cannot be force-killed safely.
        with lock:
            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()
            generated_images: list[str] = []
            globals_dict = self._globals.setdefault(session_id, {"__name__": "__main__"})
            old_cwd = os.getcwd()
            os.chdir(workspace)
            try:
                preamble = self._python_preamble(workspace)
                exec(preamble, globals_dict)
                with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
                    exec(code, globals_dict)
                success = True
                error = None
            except Exception as exc:
                import traceback

                success = False
                error = f"{type(exc).__name__}: {exc}"
                traceback.print_exc(file=stderr_buffer)
            finally:
                generated_images = list(globals_dict.get("_lambda_execution_images", []))
                os.chdir(old_cwd)

            stdout = strip_ansi_escape_codes(stdout_buffer.getvalue())
            stderr = strip_ansi_escape_codes(stderr_buffer.getvalue())
            stdout = self._truncate(stdout, "output")
            stderr = self._truncate(stderr, "error output")
            images = [f"/api/v1/files/content?url={path}" for path in generated_images]
            return {
                "success": success,
                "stdout": stdout,
                "stderr": stderr,
                "error": error,
                "exit_code": 0 if success else 1,
                "execution_time": round(time.time() - start, 3),
                "images": images,
                "generated_files": [],
            }

    def _python_preamble(self, workspace: Path) -> str:
        workspace_str = str(workspace)
        return f"""
import os, uuid, json
os.makedirs({workspace_str!r}, exist_ok=True)
_lambda_workspace = {workspace_str!r}
_lambda_execution_images = []
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.figure import Figure

    _lambda_cjk_font_family = None
    for _font_path in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ):
        if os.path.exists(_font_path):
            try:
                font_manager.fontManager.addfont(_font_path)
                _lambda_cjk_font_family = font_manager.FontProperties(fname=_font_path).get_name()
                break
            except Exception:
                pass
    if _lambda_cjk_font_family:
        plt.rcParams["font.family"] = [_lambda_cjk_font_family]
        plt.rcParams["font.sans-serif"] = [_lambda_cjk_font_family]
        plt.rcParams["axes.unicode_minus"] = False

    if not hasattr(plt.savefig, "_lambda_local_wrapped"):
        _lambda_original_savefig = plt.savefig
        def _lambda_savefig(fname, *args, **kwargs):
            if fname in ("[file]", "[file].png"):
                fname = os.path.join(_lambda_workspace, "figure_" + uuid.uuid4().hex[:8] + ".png")
            elif isinstance(fname, str) and not os.path.isabs(fname):
                fname = os.path.join(_lambda_workspace, fname)
            result = _lambda_original_savefig(fname, *args, **kwargs)
            _lambda_execution_images.append(str(fname))
            print("[IMAGE_SAVED] " + str(fname))
            return result
        _lambda_savefig._lambda_local_wrapped = True
        plt.savefig = _lambda_savefig

    if not hasattr(plt.show, "_lambda_local_wrapped"):
        def _lambda_show(*args, **kwargs):
            fname = os.path.join(_lambda_workspace, "figure_" + uuid.uuid4().hex[:8] + ".png")
            plt.gcf().savefig(fname, dpi=150, bbox_inches="tight", facecolor="white")
            _lambda_execution_images.append(str(fname))
            print("[IMAGE_SAVED] " + str(fname))
            plt.close()
        _lambda_show._lambda_local_wrapped = True
        plt.show = _lambda_show
except Exception:
    pass
"""

    async def _execute_shell(self, command: str, timeout: int, workspace: Path) -> Dict[str, Any]:
        start = time.time()
        blocked = ["rm -rf /", "mkfs", ":(){", "> /dev/sda", "shutdown", "reboot"]
        lowered = command.lower()
        if any(item in lowered for item in blocked):
            return {
                "success": False,
                "stdout": "",
                "stderr": "Command blocked for safety in local mode.",
                "exit_code": -1,
                "execution_time": 0,
                "images": [],
                "generated_files": [],
            }

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=str(workspace),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=1024 * 1024,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            stdout_str = self._truncate(strip_ansi_escape_codes(stdout.decode("utf-8", errors="replace")), "output")
            stderr_str = self._truncate(strip_ansi_escape_codes(stderr.decode("utf-8", errors="replace")), "error output")
            return {
                "success": process.returncode == 0,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "error": None if process.returncode == 0 else stderr_str,
                "exit_code": process.returncode,
                "execution_time": round(time.time() - start, 3),
                "images": [],
                "generated_files": [],
            }
        except asyncio.TimeoutError:
            with contextlib.suppress(Exception):
                process.kill()
                await process.wait()
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout} seconds",
                "error": f"Execution timed out after {timeout} seconds",
                "exit_code": -1,
                "execution_time": timeout,
                "images": [],
                "generated_files": [],
            }

    def _truncate(self, text: str, label: str) -> str:
        if len(text) > self.max_output_length:
            return text[: self.max_output_length] + f"\n... ({label} truncated)"
        return text


_local_code_execution_service: LocalCodeExecutionService | None = None


def get_local_code_execution_service() -> LocalCodeExecutionService:
    global _local_code_execution_service
    if _local_code_execution_service is None:
        _local_code_execution_service = LocalCodeExecutionService()
    return _local_code_execution_service
