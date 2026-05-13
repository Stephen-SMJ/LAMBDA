import json
import re
import time
import os
import fnmatch
from typing import Dict, Any, List
from app.services.code_execution_service import CodeExecutionService
from app.services.sandbox_file_manager import get_sandbox_file_manager, SANDBOX_SKILLS_DIR, SANDBOX_WORK_DIR
from app.core.config import settings
from app.services.local_code_execution import get_local_code_execution_service


class AgentService:
    """Service for executing AI agent tools with file synchronization."""
    
    def __init__(self):
        self.code_service = CodeExecutionService()
        self.local_code_service = get_local_code_execution_service()
        self.session_files = {}  # Track files per session
        self.session_todos = {}
        self.file_manager = get_sandbox_file_manager()
        self.tools = {
            "execute_python": self._execute_python,
            "execute_shell": self._execute_shell,
            "read_file": self._read_file,
            "write_file": self._write_file,
            "edit_file": self._edit_file,
            "glob_files": self._glob_files,
            "grep_files": self._grep_files,
            "update_todo": self._update_todo,
        }
        self.current_session_id = None
    
    async def sync_files_for_session(
        self, 
        session_id: str, 
        db, 
        user_id: int,
        sandbox_session_id: str = None,
    ) -> List[Dict[str, str]]:
        """Sync all uploaded files for a session to sandbox."""
        return await self.file_manager.sync_session_files(session_id, db, user_id, sandbox_session_id)

    def is_session_sync_current(self, session_id: str, sandbox_session_id: str) -> bool:
        """Check whether uploaded files are already synced for the current sandbox generation."""
        if settings.CODE_EXECUTION_MODE == "local":
            return bool(self.file_manager.get_all_synced_files(session_id))

        from app.services.opensandbox_service import get_opensandbox_service

        opensandbox = get_opensandbox_service()
        return self.file_manager.is_sync_current(
            session_id,
            sandbox_session_id,
            opensandbox.get_session_generation(sandbox_session_id),
        )

    def get_cached_synced_files(self, session_id: str) -> List[Dict[str, str]]:
        """Return cached synced files in the same shape as sync_files_for_session."""
        return [
            {
                "filename": path.rsplit("/", 1)[-1],
                "sandbox_path": path,
                "oss_url": "",
                "generated": key.startswith("generated/"),
            }
            for key, path in self.file_manager.get_all_synced_files(session_id).items()
        ]

    async def _resync_files_after_kernel_restart(
        self,
        session_id: str,
        db,
        user_id: int,
        sandbox_session_id: str = None,
    ) -> None:
        """Recreate /tmp/workspace files after OpenSandbox replaces the container."""
        if not db or not user_id:
            return

        await self.file_manager.cleanup_session(session_id)
        await self.file_manager.sync_session_files(session_id, db, user_id, sandbox_session_id)
    
    def get_available_files_prompt(self, session_id: str) -> str:
        """Get prompt text describing available files in sandbox."""
        synced_files = self.file_manager.get_all_synced_files(session_id)
        if not synced_files:
            return "No files uploaded yet."
        
        location = "LOCAL WORKSPACE" if settings.CODE_EXECUTION_MODE == "local" else "SANDBOX"
        files_text = f"📁 AVAILABLE FILES IN {location}:\n"
        for filename, path in synced_files.items():
            files_text += f"  - {filename}: {path}\n"
        
        files_text += "\nUse these paths directly in your code. For example:\n"
        example_path = next(iter(synced_files.values()), f"{SANDBOX_WORK_DIR}/your_file.csv")
        files_text += f"  df = pd.read_csv('{example_path}')\n"
        return files_text

    def _local_workspace(self, session_id: str):
        return self.local_code_service.workspace_for_session(session_id)

    def _resolve_local_path(self, path: str, session_id: str):
        workspace = self._local_workspace(session_id).resolve()
        raw_path = path or ""
        raw_path = raw_path.replace(SANDBOX_WORK_DIR, str(workspace))
        candidate = os.path.expanduser(raw_path)
        resolved = (workspace / candidate).resolve() if not os.path.isabs(candidate) else os.path.abspath(candidate)
        resolved_path = __import__("pathlib").Path(resolved).resolve()
        try:
            resolved_path.relative_to(workspace)
        except ValueError:
            raise ValueError(f"Path outside workspace is not allowed: {path}")
        return resolved_path
    
    async def execute_tool(self, tool_name: str, tool_input: Dict[str, Any], db=None, user_id: int = None) -> Dict[str, Any]:
        """Execute a tool by name."""
        if tool_name not in self.tools:
            return {
                "success": False,
                "output": f"Unknown tool: {tool_name}",
                "error": "Tool not found"
            }
        
        try:
            # Add db and user_id to input_data for file upload
            enriched_input = dict(tool_input)
            if db is not None:
                enriched_input["db"] = db
            if user_id is not None:
                enriched_input["user_id"] = user_id
            
            result = await self.tools[tool_name](enriched_input)
            return result
        except Exception as e:
            return {
                "success": False,
                "output": f"Error executing {tool_name}: {str(e)}",
                "error": str(e)
            }
    
    def _wrap_code_for_image_capture(self, code: str, session_id: str) -> str:
        """Wrap user code to capture matplotlib images."""
        work_dir = SANDBOX_WORK_DIR
        
        # Header code - setup image capture with recursion guard
        header = '''
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.figure import Figure
import os
import uuid

# Ensure workspace directory exists
os.makedirs(''' + repr(work_dir) + ''', exist_ok=True)

# Configure Chinese-capable matplotlib fonts when available. This prevents
# CJK labels from rendering as tofu boxes with the default DejaVu Sans font.
_lambda_cjk_font_family = None
for _font_path in (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
):
    if os.path.exists(_font_path):
        try:
            font_manager.fontManager.addfont(_font_path)
            if _lambda_cjk_font_family is None:
                _lambda_cjk_font_family = font_manager.FontProperties(fname=_font_path).get_name()
        except Exception:
            pass

def _lambda_configure_matplotlib_fonts():
    """Apply CJK-capable fonts globally and to existing figure text."""
    # Only use font family names that are actually available. Listing common
    # but missing CJK aliases causes noisy "findfont: Font family ... not found"
    # warnings in stderr even when rendering succeeds via fallback.
    _families = [_lambda_cjk_font_family] if _lambda_cjk_font_family else ["DejaVu Sans"]
    plt.rcParams["font.family"] = _families
    plt.rcParams["font.sans-serif"] = _families
    plt.rcParams["axes.unicode_minus"] = False
    if not _lambda_cjk_font_family:
        return
    for _num in plt.get_fignums():
        _fig = plt.figure(_num)
        for _text in _fig.findobj(match=matplotlib.text.Text):
            try:
                _text.set_fontfamily(_lambda_cjk_font_family)
            except Exception:
                pass

_lambda_configure_matplotlib_fonts()

if not hasattr(plt.tight_layout, '_lambda_wrapped'):
    _original_tight_layout = plt.tight_layout
    def _custom_tight_layout(*args, **kwargs):
        _lambda_configure_matplotlib_fonts()
        return _original_tight_layout(*args, **kwargs)
    _custom_tight_layout._lambda_wrapped = True
    plt.tight_layout = _custom_tight_layout

if not hasattr(Figure.tight_layout, '_lambda_wrapped'):
    _original_figure_tight_layout = Figure.tight_layout
    def _custom_figure_tight_layout(self, *args, **kwargs):
        _lambda_configure_matplotlib_fonts()
        return _original_figure_tight_layout(self, *args, **kwargs)
    _custom_figure_tight_layout._lambda_wrapped = True
    Figure.tight_layout = _custom_figure_tight_layout

# Initialize/reset image paths list for this execution
_image_paths = []  # Always reset to avoid accumulating old images
_lambda_explicit_savefig_called = False

# Only override plt.show if not already overridden
if not hasattr(plt.show, '_lambda_wrapped'):
    _original_show = plt.show
    def _custom_show(*args, **kwargs):
        """Custom show that saves figure to file"""
        global _lambda_explicit_savefig_called
        _lambda_configure_matplotlib_fonts()
        if _lambda_explicit_savefig_called:
            plt.close()
            return None
        img_path = ''' + repr(work_dir + "/figure_") + ''' + uuid.uuid4().hex[:8] + ".png"
        # Use the actual savefig from Figure to avoid recursion
        fig = plt.gcf()
        fig.savefig(img_path, dpi=150, bbox_inches='tight', facecolor='white')
        _image_paths.append(img_path)
        print("[IMAGE_SAVED] " + img_path)
        plt.close()
    _custom_show._lambda_wrapped = True
    plt.show = _custom_show

# Only override savefig if not already overridden  
if not hasattr(plt.savefig, '_lambda_wrapped'):
    _original_savefig = plt.savefig
    def _custom_savefig(fname, *args, **kwargs):
        """Custom savefig that captures paths"""
        global _lambda_explicit_savefig_called
        _lambda_configure_matplotlib_fonts()
        _lambda_explicit_savefig_called = True
        # Handle placeholder [file] or [file].png - generate actual filename with extension
        if fname == '[file]' or fname == '[file].png':
            fname = ''' + repr(work_dir + "/figure_") + ''' + uuid.uuid4().hex[:8] + ".png"
        elif fname and not fname.startswith('/'):
            fname = ''' + repr(work_dir + "/") + ''' + fname
        # Call Figure.savefig directly so pyplot.savefig does not trigger the
        # Figure wrapper as a second capture.
        if '_original_figure_savefig' in globals():
            result = _original_figure_savefig(plt.gcf(), fname, *args, **kwargs)
        else:
            result = _original_savefig(fname, *args, **kwargs)
        _image_paths.append(fname)
        print("[IMAGE_SAVED] " + str(fname))
        return result
    _custom_savefig._lambda_wrapped = True
    plt.savefig = _custom_savefig

if not hasattr(Figure.savefig, '_lambda_wrapped'):
    _original_figure_savefig = Figure.savefig
    def _custom_figure_savefig(self, fname, *args, **kwargs):
        global _lambda_explicit_savefig_called
        _lambda_configure_matplotlib_fonts()
        _lambda_explicit_savefig_called = True
        if fname == '[file]' or fname == '[file].png':
            fname = ''' + repr(work_dir + "/figure_") + ''' + uuid.uuid4().hex[:8] + ".png"
        elif isinstance(fname, str) and fname and not fname.startswith('/'):
            fname = ''' + repr(work_dir + "/") + ''' + fname
        result = _original_figure_savefig(self, fname, *args, **kwargs)
        _image_paths.append(fname)
        print("[IMAGE_SAVED] " + str(fname))
        return result
    _custom_figure_savefig._lambda_wrapped = True
    Figure.savefig = _custom_figure_savefig

# User code starts here
'''
        
        # Footer code - capture image paths
        footer = '''

# Capture all image paths at end of execution
import json
if '_image_paths' in globals() and _image_paths:
    print("\\n[CAPTURED_IMAGES] " + json.dumps(_image_paths))
'''
        
        return header + code + footer
    
    def _replace_local_paths_with_urls(self, text: str, result: Dict[str, Any]) -> str:
        """Replace local sandbox paths with OSS URLs in text."""
        if not text:
            return text

        # Internal capture markers are useful for backend upload detection, but
        # should not appear in user-visible logs.
        text = "\n".join(
            line for line in text.splitlines()
            if "[IMAGE_SAVED]" not in line and "[CAPTURED_IMAGES]" not in line
        )

        if not result.get("generated_files"):
            return text
        
        for file_info in result["generated_files"]:
            local_path = file_info.get("sandbox_path", "")
            oss_url = file_info.get("oss_url", "")
            if local_path and oss_url:
                # Replace only exact sandbox paths. Do not replace the bare
                # filename globally: that corrupts signed OSS URLs that already
                # contain the filename, producing generated/.../https://...
                text = text.replace(local_path, oss_url)
        
        return text
    
    async def _execute_python(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute Python code."""
        code = input_data.get("code", "")
        session_id = input_data.get("session_id", self.current_session_id or "default")
        sandbox_session_id = input_data.get("sandbox_session_id", session_id)
        
        if not code:
            return {
                "success": False,
                "output": "No code provided",
                "error": "Missing code parameter"
            }

        if settings.CODE_EXECUTION_MODE == "local":
            before_files = await self._snapshot_workspace_files(session_id)
            workspace = self._local_workspace(session_id)
            code = code.replace(SANDBOX_WORK_DIR, str(workspace))
            result = await self.local_code_service.execute(
                code,
                language="python",
                session_id=session_id,
                cwd=workspace,
            )
            await self._scan_and_upload_files(
                session_id,
                input_data.get("user_id"),
                input_data.get("db"),
                result,
                before_files=before_files,
                sandbox_session_id=sandbox_session_id,
            )
            output = result.get("stdout", "")
            if result.get("stderr"):
                output += ("\n" if output else "") + f"[STDERR] {result['stderr']}"
            stdout = result.get("stdout", "")
            return {
                "success": result.get("success", False),
                "output": self._replace_local_paths_with_urls(output, result),
                "stdout": self._replace_local_paths_with_urls(stdout, result),
                "stderr": result.get("stderr", ""),
                "error": result.get("error"),
                "images": result.get("images", []),
                "generated_files": result.get("generated_files", []),
            }
        
        # Ensure workspace directory exists in sandbox
        from app.services.opensandbox_service import get_opensandbox_service
        opensandbox = get_opensandbox_service()
        generation_before = opensandbox.get_session_generation(sandbox_session_id)
        mkdir_result = await opensandbox.execute_shell(f"mkdir -p {SANDBOX_WORK_DIR}", sandbox_session_id)
        if mkdir_result.get("kernel_restarted"):
            await self._resync_files_after_kernel_restart(
                session_id,
                input_data.get("db"),
                input_data.get("user_id"),
                sandbox_session_id,
            )
        generation_after_workspace = opensandbox.get_session_generation(sandbox_session_id)
        workspace_restarted = generation_after_workspace != generation_before
        before_files = await self._snapshot_workspace_files(sandbox_session_id)
        if opensandbox.get_session_generation(sandbox_session_id) != generation_after_workspace:
            workspace_restarted = True
            await self._resync_files_after_kernel_restart(
                session_id,
                input_data.get("db"),
                input_data.get("user_id"),
                sandbox_session_id,
            )
            before_files = await self._snapshot_workspace_files(sandbox_session_id)
        
        # Wrap code to capture images
        wrapped_code = self._wrap_code_for_image_capture(code, session_id)
        
        result = await self.code_service.execute(wrapped_code, language="python", session_id=sandbox_session_id)
        kernel_restarted = bool(result.get("kernel_restarted") or workspace_restarted)
        if kernel_restarted:
            await self._resync_files_after_kernel_restart(
                session_id,
                input_data.get("db"),
                input_data.get("user_id"),
                sandbox_session_id,
            )
        
        # Scan for and upload generated files
        await self._scan_and_upload_files(
            session_id,
            input_data.get("user_id"),
            input_data.get("db"),
            result,
            before_files=before_files,
            sandbox_session_id=sandbox_session_id,
        )
        
        # Map stdout/stderr to output for consistency
        output = result.get("stdout", "")
        if result.get("stderr"):
            if output:
                output += "\n"
            output += f"[STDERR] {result['stderr']}"
        if kernel_restarted:
            restart_notice = (
                "[KERNEL_RESTARTED] The sandbox Python kernel/container was recreated. "
                "In-memory variables from earlier steps are gone. Uploaded input files have been re-synced to "
                f"{SANDBOX_WORK_DIR}; reload the dataset before continuing."
            )
            output = f"{restart_notice}\n{output}" if output else restart_notice
        
        # Replace local paths with OSS URLs in output
        output = self._replace_local_paths_with_urls(output, result)
        stdout = self._replace_local_paths_with_urls(result.get("stdout", ""), result)
        
        return {
            "success": result.get("success", False),
            "output": output,
            "stdout": stdout,
            "stderr": result.get("stderr", ""),
            "error": result.get("error"),
            "images": result.get("images", []),
            "generated_files": result.get("generated_files", []),
            "kernel_restarted": kernel_restarted,
        }
    
    async def _execute_shell(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute shell commands."""
        command = input_data.get("command", "")
        session_id = input_data.get("session_id", self.current_session_id or "default")
        sandbox_session_id = input_data.get("sandbox_session_id", session_id)
        
        if not command:
            return {
                "success": False,
                "output": "No command provided",
                "error": "Missing command parameter"
            }

        if settings.CODE_EXECUTION_MODE == "local":
            before_files = await self._snapshot_workspace_files(session_id)
            workspace = self._local_workspace(session_id)
            command = command.replace(SANDBOX_WORK_DIR, str(workspace))
            result = await self.local_code_service.execute(
                command,
                language="shell",
                session_id=session_id,
                cwd=workspace,
            )
            await self._scan_and_upload_files(
                session_id,
                input_data.get("user_id"),
                input_data.get("db"),
                result,
                before_files=before_files,
                sandbox_session_id=sandbox_session_id,
            )
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            return {
                "success": result.get("success", False),
                "output": stdout,
                "stdout": stdout,
                "stderr": stderr,
                "error": result.get("error"),
                "generated_files": result.get("generated_files", []),
            }
        
        # Security: whitelist allowed commands
        allowed_prefixes = ['ls', 'cat', 'head', 'tail', 'wc', 'grep', 'find', 'pwd', 'echo', 'mkdir', 'touch', 'rm', 'cp', 'mv', 'pip', 'python', 'python3', '/opt/python/versions/cpython-3.11.14-linux-x86_64-gnu/bin/python3', 'cd', 'which', 'file', 'du', 'df', 'pdflatex', 'xelatex']
        cmd_parts = command.strip().split()
        if not cmd_parts or cmd_parts[0] not in allowed_prefixes:
            return {
                "success": False,
                "output": f"Command '{command}' is not allowed for security reasons",
                "error": f"Command not in whitelist: {allowed_prefixes}"
            }
        
        from app.services.opensandbox_service import get_opensandbox_service
        opensandbox = get_opensandbox_service()
        before_files = await self._snapshot_workspace_files(sandbox_session_id)
        result = await opensandbox.execute_shell(command, sandbox_session_id)
        
        # Scan for and upload generated files
        await self._scan_and_upload_files(
            session_id,
            input_data.get("user_id"),
            input_data.get("db"),
            result,
            before_files=before_files,
            sandbox_session_id=sandbox_session_id,
        )

        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        output_text = f"{stdout}\n{stderr}"
        command_name = cmd_parts[0] if cmd_parts else ""
        generated_files = result.get("generated_files", [])
        generated_pdf = any((f.get("filename") or "").lower().endswith(".pdf") for f in generated_files)
        latex_wrote_pdf = "Output written on " in output_text and ".pdf" in output_text
        recovered_latex_pdf = (
            command_name in {"pdflatex", "xelatex"}
            and not result.get("success", False)
            and generated_pdf
            and latex_wrote_pdf
        )
        if recovered_latex_pdf:
            result["success"] = True
            stdout = (
                stdout.rstrip()
                + "\n\n[LATEX_WARNING] The LaTeX command returned a non-zero exit code, "
                "but a PDF was generated and uploaded. Review the log warnings if formatting looks wrong."
            ).strip()
        
        return {
            "success": result.get("success", False),
            "output": stdout,
            "stdout": stdout,
            "stderr": stderr,
            "error": result.get("error"),
            "generated_files": result.get("generated_files", [])
        }
    
    async def _snapshot_workspace_files(self, session_id: str) -> Dict[str, Dict[str, Any]]:
        """Return a lightweight snapshot of files currently in the sandbox workspace.

        Use shell instead of the Python interpreter so file bookkeeping does not
        touch the user's long-lived Python kernel or its variables.
        """
        if settings.CODE_EXECUTION_MODE == "local":
            workspace = self._local_workspace(session_id)
            snapshot = {}
            for path in workspace.rglob("*"):
                if not path.is_file() or ".skills" in path.parts:
                    continue
                stat = path.stat()
                snapshot[str(path)] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
            return snapshot

        from app.services.opensandbox_service import get_opensandbox_service
        opensandbox = get_opensandbox_service()

        try:
            result = await opensandbox.execute_shell(
                f"find {SANDBOX_WORK_DIR} -path '{SANDBOX_SKILLS_DIR}' -prune -o -type f -printf '%p\\t%s\\t%T@\\n'",
                session_id,
                timeout=30,
            )
            if not result.get("success"):
                return {}

            stdout = result.get("stdout", "")
            snapshot = {}
            for line in stdout.splitlines():
                parts = line.rstrip("\n").split("\t")
                if len(parts) != 3:
                    continue
                path, size, mtime = parts
                try:
                    snapshot[path] = {
                        "size": int(size),
                        "mtime_ns": int(float(mtime) * 1_000_000_000),
                    }
                except ValueError:
                    continue
            return snapshot
        except Exception as e:
            print(f"Failed to snapshot workspace files: {e}")

        return {}

    async def _scan_and_upload_files(
        self,
        session_id: str,
        user_id: int,
        db,
        result: Dict[str, Any],
        before_files: Dict[str, Dict[str, Any]] = None,
        sandbox_session_id: str = None,
    ):
        """Scan sandbox workspace for generated files and upload to OSS.
        
        Uploads files detected from explicit image markers and from a before/after
        workspace diff. The diff is the authoritative fallback because stdout
        markers can be missed when code uses fig.savefig(), paths contain spaces,
        or output is truncated by the execution backend."""
        if not user_id or not db:
            return
        
        try:
            # Parse stdout to find files generated in THIS execution
            stdout = result.get('stdout', '')
            before_files = before_files or {}
            
            # Find all [IMAGE_SAVED] lines. Parse by line instead of \S+ so
            # paths containing spaces are not truncated.
            current_execution_files = set()
            for line in stdout.splitlines():
                if "[IMAGE_SAVED]" in line:
                    path = line.split("[IMAGE_SAVED]", 1)[1].strip()
                    if path:
                        current_execution_files.add(path)
            
            # Also check [CAPTURED_IMAGES] for the list
            for line in stdout.splitlines():
                if "[CAPTURED_IMAGES]" not in line:
                    continue
                try:
                    import json
                    captured_files = json.loads(line.split("[CAPTURED_IMAGES]", 1)[1].strip())
                    current_execution_files.update(captured_files)
                except:
                    pass
            
            # Authoritative fallback: compare workspace snapshots before and
            # after execution. This catches fig.savefig(), markdown/csv/model
            # exports, and any marker lost in stdout.
            snapshot_session_id = session_id if settings.CODE_EXECUTION_MODE == "local" else (sandbox_session_id or session_id)
            after_files = await self._snapshot_workspace_files(snapshot_session_id)
            for path, metadata in after_files.items():
                if before_files.get(path) != metadata:
                    current_execution_files.add(path)
            
            if not current_execution_files:
                print("No files generated in current execution")
                return
            
            print(f"Files generated in current execution: {current_execution_files}")
            
            # Only process files generated in this execution
            uploaded_files = []
            uploaded_oss_urls = set()
            
            # Get list of original uploaded files to skip them
            from app.models.models import UploadedFile
            from app.services.sandbox_file_manager import get_sandbox_file_manager
            file_manager = get_sandbox_file_manager()
            synced_files = file_manager.get_all_synced_files(session_id)
            uploaded_file_names = set(synced_files.keys())
            
            for sandbox_path in sorted(current_execution_files):
                if not sandbox_path or sandbox_path.startswith('.'):
                    continue
                if sandbox_path.startswith(("http://", "https://", "/api/")):
                    print(f"Skipping non-sandbox generated file reference: {sandbox_path}")
                    continue
                normalized_path = sandbox_path.replace("\\", "/")
                if settings.CODE_EXECUTION_MODE != "local" and not normalized_path.startswith(f"{SANDBOX_WORK_DIR}/"):
                    print(f"Skipping file outside sandbox workspace: {sandbox_path}")
                    continue
                if (
                    sandbox_path == SANDBOX_SKILLS_DIR
                    or sandbox_path.startswith(f"{SANDBOX_SKILLS_DIR}/")
                    or "/.skills/" in normalized_path
                ):
                    print(f"Skipping internal skill file: {sandbox_path}")
                    continue
                
                filename = sandbox_path.split('/')[-1]
                if not filename:
                    continue
                
                # Skip original uploaded files (user input files)
                if filename in uploaded_file_names:
                    print(f"Skipping original uploaded file: {filename}")
                    continue
                
                # Skip common non-generated files
                if filename in ['.gitignore', 'README.md', 'requirements.txt', '.init']:
                    continue
                
                # Determine file type
                ext = '.' + filename.split('.')[-1].lower() if '.' in filename else ''
                file_type = 'file'
                if ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp']:
                    file_type = 'image'
                elif ext in ['.pdf']:
                    file_type = 'pdf'
                elif ext in ['.csv', '.xlsx', '.xls', '.json', '.txt', '.html', '.xml', '.md']:
                    file_type = 'data'
                elif ext in ['.tex', '.sty', '.cls']:
                    file_type = 'latex'
                elif ext in ['.pkl', '.joblib', '.h5', '.pt', '.pth', '.onnx', '.model']:
                    file_type = 'model'
                elif ext in ['.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.go', '.rs']:
                    file_type = 'code'
                
                print(f"Processing file: {filename} (type: {file_type}) from {sandbox_path}")
                
                # Upload all non-uploaded files
                # Retry logic for upload
                oss_url = None
                for attempt in range(3):
                    try:
                        oss_url = await self.file_manager.upload_generated_file(
                            session_id,
                            sandbox_path,
                            filename,
                            user_id,
                            db,
                            sandbox_session_id=sandbox_session_id,
                        )
                        if oss_url:
                            break
                    except Exception as e:
                        print(f"Upload attempt {attempt + 1} failed for {filename}: {e}")
                        if attempt < 2:
                            import asyncio
                            await asyncio.sleep(0.5)
                
                if oss_url:
                    # Track uploaded URLs to avoid duplicates
                    if oss_url not in uploaded_oss_urls:
                        uploaded_files.append({
                            "filename": filename,
                            "sandbox_path": sandbox_path,
                            "oss_url": oss_url,
                            "type": file_type
                        })
                        uploaded_oss_urls.add(oss_url)
                        print(f"Uploaded {filename} ({file_type}) to {oss_url}")
                    else:
                        print(f"Skipping duplicate upload: {filename}")
                else:
                    print(f"Failed to upload {filename} after 3 attempts")
            
            # Add uploaded files to result
            if uploaded_files:
                if "generated_files" not in result:
                    result["generated_files"] = []
                result["generated_files"].extend(uploaded_files)
                
                # Add image URLs to images list
                if "images" not in result:
                    result["images"] = []
                for f in uploaded_files:
                    if f["type"] == "image" and f["oss_url"] not in result["images"]:
                        result["images"].append(f["oss_url"])
                        print(f"Added image URL: {f['oss_url']}")
                        
        except Exception as e:
            print(f"Failed to scan and upload files: {e}")
            import traceback
            traceback.print_exc()
    
    async def _read_file(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Read file contents from OpenSandbox."""
        file_path = input_data.get("path", "")
        session_id = input_data.get("session_id", self.current_session_id or "default")
        sandbox_session_id = input_data.get("sandbox_session_id", session_id)
        
        if not file_path:
            return {
                "success": False,
                "output": "No file path provided",
                "error": "Missing path parameter"
            }

        if settings.CODE_EXECUTION_MODE == "local":
            try:
                local_path = self._resolve_local_path(file_path, session_id)
                if not local_path.exists() or not local_path.is_file():
                    return {"success": False, "output": f"File not found or cannot be read: {file_path}", "error": "File not found"}
                content = local_path.read_text(encoding="utf-8", errors="replace")
                return {"success": True, "output": content, "content": content, "path": str(local_path)}
            except Exception as e:
                return {"success": False, "output": f"Error reading file: {str(e)}", "error": str(e)}
        
        try:
            # Try to read from OpenSandbox first
            from app.services.opensandbox_service import get_opensandbox_service
            sandbox_service = get_opensandbox_service()
            content = await sandbox_service.read_file(file_path, sandbox_session_id)
            
            if content is None:
                return {
                    "success": False,
                    "output": f"File not found or cannot be read: {file_path}",
                    "error": "File not found"
                }
            
            return {
                "success": True,
                "output": content,
                "content": content,
                "path": file_path
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": f"Error reading file: {str(e)}",
                "error": str(e)
            }
    
    async def _write_file(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Write text file to OpenSandbox."""
        start_time = time.time()
        file_path = input_data.get("path", "")
        content = input_data.get("content", "")
        session_id = input_data.get("session_id", self.current_session_id or "default")
        sandbox_session_id = input_data.get("sandbox_session_id", session_id)
        
        if not file_path:
            return {
                "success": False,
                "output": "No file path provided",
                "error": "Missing path parameter"
            }

        if settings.CODE_EXECUTION_MODE == "local":
            try:
                local_path = self._resolve_local_path(file_path, session_id)
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_text(content, encoding="utf-8")
                content_preview = content[:500] + "..." if len(content) > 500 else content
                summary = f"Wrote file: {local_path.name} ({len(content):,} characters)"
                return {
                    "success": True,
                    "output": summary,
                    "stdout": summary,
                    "path": str(local_path),
                    "content_preview": content_preview,
                    "exit_code": 0,
                    "execution_time": round(time.time() - start_time, 3),
                }
            except Exception as e:
                return {"success": False, "output": f"Error writing file: {str(e)}", "error": str(e)}
        
        try:
            from app.services.opensandbox_service import get_opensandbox_service
            sandbox_service = get_opensandbox_service()
            
            # Ensure parent directory exists
            parent_dir = "/".join(file_path.split("/")[:-1])
            if parent_dir:
                await sandbox_service.execute_shell(f"mkdir -p {parent_dir}", sandbox_session_id)
            
            success = await sandbox_service.write_file(file_path, content, sandbox_session_id)
            
            if not success:
                return {
                    "success": False,
                    "output": f"Failed to write file: {file_path}",
                    "error": "Write operation failed"
                }
            
            # Truncate content for display if too long
            content_preview = content[:500] + "..." if len(content) > 500 else content
            filename = file_path.rstrip("/").split("/")[-1] or file_path
            summary = f"Wrote file: {filename} ({len(content):,} characters)"
            return {
                "success": True,
                "output": summary,
                "stdout": summary,
                "path": file_path,
                "content_preview": content_preview,
                "exit_code": 0,
                "execution_time": round(time.time() - start_time, 3)
            }
            
        except Exception as e:
            return {
                "success": False,
                "output": f"Error writing file: {str(e)}",
                "error": str(e)
            }
    
    async def _edit_file(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Edit file by replacing text."""
        file_path = input_data.get("path", "")
        old_string = input_data.get("old_string", "")
        new_string = input_data.get("new_string", "")
        session_id = input_data.get("session_id", self.current_session_id or "default")
        sandbox_session_id = input_data.get("sandbox_session_id", session_id)
        
        if not file_path or old_string is None:
            return {
                "success": False,
                "output": "Missing required parameters",
                "error": "path and old_string are required"
            }
        
        try:
            # First read the file
            read_result = await self._read_file({
                "path": file_path,
                "session_id": session_id,
                "sandbox_session_id": sandbox_session_id,
            })
            if not read_result.get("success"):
                return read_result
            
            current_content = read_result.get("content", "")
            
            # Replace the old string with new string
            if old_string not in current_content:
                return {
                    "success": False,
                    "output": f"Could not find the text to replace in {file_path}",
                    "error": "old_string not found in file"
                }
            
            new_content = current_content.replace(old_string, new_string, 1)
            
            # Write the modified content
            write_result = await self._write_file({
                "path": file_path,
                "content": new_content,
                "session_id": session_id,
                "sandbox_session_id": sandbox_session_id,
            })
            
            if write_result.get("success"):
                return {
                    "success": True,
                    "output": f"File edited successfully: {file_path}",
                    "path": file_path
                }
            else:
                return write_result
                
        except Exception as e:
            import traceback
            return {
                "success": False,
                "output": f"Failed to edit file: {str(e)}",
                "error": traceback.format_exc()
            }

    async def _glob_files(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Find files in the sandbox using a glob-style pattern."""
        pattern = input_data.get("pattern", "")
        path = input_data.get("path") or SANDBOX_WORK_DIR
        max_results = int(input_data.get("max_results") or 100)
        session_id = input_data.get("session_id", self.current_session_id or "default")
        sandbox_session_id = input_data.get("sandbox_session_id", session_id)

        if not pattern:
            return {
                "success": False,
                "output": "No glob pattern provided",
                "error": "Missing pattern parameter"
            }
        if path == SANDBOX_SKILLS_DIR or path.startswith(f"{SANDBOX_SKILLS_DIR}/"):
            return {
                "success": True,
                "output": "No files matched",
                "stdout": "No files matched",
                "matches": [],
                "count": 0,
            }

        if settings.CODE_EXECUTION_MODE == "local":
            try:
                root = self._resolve_local_path(path, session_id)
                matches = []
                if root.is_file():
                    candidates = [root]
                else:
                    candidates = [p for p in root.rglob("*") if p.is_file() and ".skills" not in p.parts]
                for candidate in candidates:
                    rel = candidate.relative_to(root if root.is_dir() else root.parent).as_posix()
                    if fnmatch.fnmatch(candidate.name, pattern) or fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(str(candidate), pattern):
                        matches.append(str(candidate))
                        if len(matches) >= max_results:
                            break
                output = "\n".join(matches) if matches else "No files matched"
                return {"success": True, "output": output, "stdout": output, "matches": matches, "count": len(matches)}
            except Exception as e:
                return {"success": False, "output": f"Glob failed: {str(e)}", "error": str(e), "matches": [], "count": 0}

        max_results = max(1, min(max_results, 500))
        scan_code = f"""
import fnmatch
import json
import os

root = {path!r}
pattern = {pattern!r}
max_results = {max_results}
skills_dir = {SANDBOX_SKILLS_DIR!r}

if not os.path.isabs(root):
    root = os.path.join({SANDBOX_WORK_DIR!r}, root)

matches = []
if os.path.isdir(root):
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {{'.git', '__pycache__', '.ipynb_checkpoints', '.skills'}}]
        for name in files:
            full_path = os.path.join(current_root, name)
            if full_path == skills_dir or full_path.startswith(skills_dir + os.sep):
                continue
            rel_path = os.path.relpath(full_path, root)
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(full_path, pattern):
                matches.append(full_path)
                if len(matches) >= max_results:
                    break
        if len(matches) >= max_results:
            break

print(json.dumps({{"matches": matches, "count": len(matches)}}, ensure_ascii=False))
"""

        from app.services.opensandbox_service import get_opensandbox_service
        sandbox_service = get_opensandbox_service()
        result = await sandbox_service.execute_python(scan_code, sandbox_session_id, timeout=30)
        stdout = result.get("stdout", "")

        try:
            payload = json.loads(stdout.strip().splitlines()[-1])
            matches = payload.get("matches", [])
        except Exception:
            matches = []

        output = "\n".join(matches) if matches else "No files matched"
        return {
            "success": result.get("success", False),
            "output": output,
            "stdout": output,
            "matches": matches,
            "count": len(matches),
            "stderr": result.get("stderr", ""),
            "error": result.get("error")
        }

    async def _grep_files(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Search text files in the sandbox."""
        pattern = input_data.get("pattern", "")
        path = input_data.get("path") or SANDBOX_WORK_DIR
        include_glob = input_data.get("include_glob") or "*"
        max_results = int(input_data.get("max_results") or 100)
        case_sensitive = bool(input_data.get("case_sensitive", True))
        session_id = input_data.get("session_id", self.current_session_id or "default")
        sandbox_session_id = input_data.get("sandbox_session_id", session_id)

        if not pattern:
            return {
                "success": False,
                "output": "No search pattern provided",
                "error": "Missing pattern parameter"
            }
        if path == SANDBOX_SKILLS_DIR or path.startswith(f"{SANDBOX_SKILLS_DIR}/"):
            return {
                "success": True,
                "output": "No matches found",
                "stdout": "No matches found",
                "matches": [],
                "count": 0,
            }

        if settings.CODE_EXECUTION_MODE == "local":
            try:
                root = self._resolve_local_path(path, session_id)
                flags = 0 if case_sensitive else re.IGNORECASE
                try:
                    compiled = re.compile(pattern, flags)
                except re.error:
                    compiled = re.compile(re.escape(pattern), flags)
                candidates = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file() and ".skills" not in p.parts]
                matches = []
                for candidate in candidates:
                    if not fnmatch.fnmatch(candidate.name, include_glob):
                        continue
                    if candidate.stat().st_size > 2_000_000:
                        continue
                    for line_no, line in enumerate(candidate.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
                        if compiled.search(line):
                            matches.append({"path": str(candidate), "line": line_no, "text": line})
                            if len(matches) >= max_results:
                                break
                    if len(matches) >= max_results:
                        break
                output = "\n".join(f"{m['path']}:{m['line']}: {m['text']}" for m in matches) if matches else "No matches found"
                return {"success": True, "output": output, "stdout": output, "matches": matches, "count": len(matches)}
            except Exception as e:
                return {"success": False, "output": f"Grep failed: {str(e)}", "error": str(e), "matches": [], "count": 0}

        max_results = max(1, min(max_results, 500))
        scan_code = f"""
import fnmatch
import json
import os
import re

root = {path!r}
pattern = {pattern!r}
include_glob = {include_glob!r}
max_results = {max_results}
case_sensitive = {case_sensitive!r}
skills_dir = {SANDBOX_SKILLS_DIR!r}

if not os.path.isabs(root):
    root = os.path.join({SANDBOX_WORK_DIR!r}, root)

flags = 0 if case_sensitive else re.IGNORECASE
try:
    compiled = re.compile(pattern, flags)
except re.error:
    compiled = re.compile(re.escape(pattern), flags)

matches = []
if os.path.isfile(root):
    candidate_files = [root]
else:
    candidate_files = []
    if os.path.isdir(root):
        for current_root, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in {{'.git', '__pycache__', '.ipynb_checkpoints', '.skills'}}]
            for name in files:
                full_path = os.path.join(current_root, name)
                if full_path == skills_dir or full_path.startswith(skills_dir + os.sep):
                    continue
                rel_path = os.path.relpath(full_path, root)
                if fnmatch.fnmatch(name, include_glob) or fnmatch.fnmatch(rel_path, include_glob):
                    candidate_files.append(full_path)

for full_path in candidate_files:
    try:
        if os.path.getsize(full_path) > 2_000_000:
            continue
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as handle:
            for line_no, line in enumerate(handle, start=1):
                if compiled.search(line):
                    matches.append({{
                        "path": full_path,
                        "line": line_no,
                        "text": line.rstrip("\\n")
                    }})
                    if len(matches) >= max_results:
                        raise StopIteration
    except StopIteration:
        break
    except Exception:
        continue

print(json.dumps({{"matches": matches, "count": len(matches)}}, ensure_ascii=False))
"""

        from app.services.opensandbox_service import get_opensandbox_service
        sandbox_service = get_opensandbox_service()
        result = await sandbox_service.execute_python(scan_code, sandbox_session_id, timeout=30)
        stdout = result.get("stdout", "")

        try:
            payload = json.loads(stdout.strip().splitlines()[-1])
            matches = payload.get("matches", [])
        except Exception:
            matches = []

        lines = [
            f"{match.get('path')}:{match.get('line')}: {match.get('text')}"
            for match in matches
        ]
        output = "\n".join(lines) if lines else "No matches found"
        return {
            "success": result.get("success", False),
            "output": output,
            "stdout": output,
            "matches": matches,
            "count": len(matches),
            "stderr": result.get("stderr", ""),
            "error": result.get("error")
        }

    async def _update_todo(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update a per-session todo list for multi-step work."""
        todos = input_data.get("todos")
        session_id = input_data.get("session_id", self.current_session_id or "default")

        if not isinstance(todos, list):
            return {
                "success": False,
                "output": "todos must be a list",
                "error": "Invalid todos parameter"
            }

        allowed_statuses = {"pending", "in_progress", "completed"}
        normalized = []
        for index, item in enumerate(todos, start=1):
            if isinstance(item, str):
                content = item.strip()
                status = "pending"
            elif isinstance(item, dict):
                content = str(item.get("content") or item.get("task") or "").strip()
                status = str(item.get("status") or "pending")
            else:
                continue

            if not content:
                continue
            if status not in allowed_statuses:
                status = "pending"
            normalized.append({
                "id": index,
                "content": content,
                "status": status
            })

        self.session_todos[session_id] = normalized
        if not normalized:
            output = "Todo list cleared"
        else:
            output = "\n".join(
                f"{item['id']}. [{item['status']}] {item['content']}"
                for item in normalized
            )

        return {
            "success": True,
            "output": output,
            "stdout": output,
            "todos": normalized
        }
    
    def get_session_files(self, session_id: str) -> List[str]:
        """Get list of files in a session."""
        return self.session_files.get(session_id, [])
    
    def set_session(self, session_id: str):
        """Set current session ID."""
        self.current_session_id = session_id
        if session_id not in self.session_files:
            self.session_files[session_id] = []
    
    def get_tool_definitions(self) -> list:
        """Get tool definitions for LLM."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "execute_python",
                    "description": f"""🎯 PRIMARY TOOL for Python data analysis.

WORKING DIRECTORY: the current conversation's local workspace.
Uploaded files are automatically synced there. Use the exact paths shown in the available-files prompt.

Generated files (charts, exports) are automatically captured and displayed in Files.

USE THIS FOR:
- Loading and analyzing CSV, Excel, JSON files
- Data cleaning, transformation, aggregation
- Creating visualizations with matplotlib, seaborn
- Statistical analysis with pandas, numpy, scipy
- Machine learning with scikit-learn
- Any Python code execution

VARIABLES PERSIST between calls in the same session!
Example: Load data in step 1, analyze in step 2, visualize in step 3.

ALWAYS use plt.savefig() to save charts, NOT plt.show():
  plt.savefig('chart.png')""",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "Python code to execute. Use plt.savefig() for charts. Variables persist between calls."
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Session ID for variable persistence (use conversation_id)"
                            }
                        },
                        "required": ["code", "session_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_shell",
                    "description": f"""Execute shell commands for analysis and report generation.

IMPORTANT: Use 'python3' instead of 'python', and 'python3 -m pip' instead of 'pip'.
First use preinstalled packages. If installation is essential, use one simple command like `/opt/python/versions/cpython-3.11.14-linux-x86_64-gnu/bin/python3 -m pip install package-name --break-system-packages --no-cache-dir`.
Do NOT use apt-get, sudo, pip3, tlmgr, shell chaining with ;/||/&&, pipes, or redirection such as 2>&1.
Examples:
- /opt/python/versions/cpython-3.11.14-linux-x86_64-gnu/bin/python3 -m pip install python-pptx --break-system-packages --no-cache-dir
- python3 script.py
- ls
- pdflatex -interaction=nonstopmode -halt-on-error report.tex
- xelatex -interaction=nonstopmode -halt-on-error report.tex

LaTeX is available if installed on the host. For English PDF reports, write a .tex file first, then compile it with pdflatex via this tool. For Chinese or mixed Chinese/English reports, use xelatex with xeCJK/ctex and Noto CJK fonts. Do not use tlmgr at runtime. For long reports or formal PDF reports, read .skills/latex_skill.md first and follow its template. Run the compiler twice if the document uses references or a table of contents.
For PPT, presentation, slides, or deck requests, read .skills/ppt_skill.md first. Prefer editable .pptx with python-pptx unless the user explicitly asks for PDF slides.
""",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Shell command to execute"
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Session ID for workspace isolation"
                            }
                        },
                        "required": ["command", "session_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read contents of a text file from the local workspace. Use for: reading code files, logs, generated reports.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "File path relative to the local workspace, or an absolute path inside it"
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Session ID for workspace isolation"
                            }
                        },
                        "required": ["path", "session_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write text content to a file in the local workspace. Use for: saving reports, exporting data as CSV/JSON, writing code files.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "File path relative to the local workspace, or an absolute path inside it"
                            },
                            "content": {
                                "type": "string",
                                "description": "Text content to write"
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Session ID for workspace isolation"
                            }
                        },
                        "required": ["path", "content", "session_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "edit_file",
                    "description": "Edit an existing text file by replacing a specific string. Use for: modifying code, updating configuration files.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "File path relative to the local workspace, or an absolute path inside it"
                            },
                            "old_string": {
                                "type": "string",
                                "description": "Exact text to find and replace"
                            },
                            "new_string": {
                                "type": "string",
                                "description": "Replacement text"
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Session ID for workspace isolation"
                            }
                        },
                        "required": ["path", "old_string", "new_string", "session_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "glob_files",
                    "description": "Find files in the local workspace using a glob pattern. Use before reading unknown file names or locating generated artifacts.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "Glob pattern, e.g. *.csv, **/*.png, report*.md"
                            },
                            "path": {
                                "type": "string",
                                "description": "Directory or file to search. Defaults to the local workspace."
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of matches to return, capped at 500"
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Session ID for workspace isolation"
                            }
                        },
                        "required": ["pattern", "session_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "grep_files",
                    "description": "Search text file contents in the local workspace. Use to inspect code, logs, reports, CSV headers, or generated text.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "Regex or literal text to search for"
                            },
                            "path": {
                                "type": "string",
                                "description": "File or directory to search. Defaults to the local workspace."
                            },
                            "include_glob": {
                                "type": "string",
                                "description": "Only search matching file names, e.g. *.py or *.md"
                            },
                            "case_sensitive": {
                                "type": "boolean",
                                "description": "Whether matching is case-sensitive"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of matches to return, capped at 500"
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Session ID for workspace isolation"
                            }
                        },
                        "required": ["pattern", "session_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_todo",
                    "description": "Create or update a concise todo list for long multi-step analysis. Use only when the task likely needs 5+ meaningful steps; otherwise proceed directly.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "todos": {
                                "type": "array",
                                "description": "Todo items with content and status",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "content": {
                                            "type": "string",
                                            "description": "Task description"
                                        },
                                        "status": {
                                            "type": "string",
                                            "enum": ["pending", "in_progress", "completed"],
                                            "description": "Task status"
                                        }
                                    },
                                    "required": ["content", "status"]
                                }
                            },
                            "session_id": {
                                "type": "string",
                                "description": "Session ID for todo isolation"
                            }
                        },
                        "required": ["todos", "session_id"]
                    }
                }
            }
        ]
        
        return tools
