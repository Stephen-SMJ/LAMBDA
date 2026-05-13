"""LaTeX compilation service for generating PDFs."""

import subprocess
import tempfile
import shutil
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.core.config import settings


class LatexService:
    """Service for compiling LaTeX to PDF."""
    
    def __init__(self):
        self.work_dir = Path("./data/latex")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir = Path("./data/images")
    
    async def compile_latex(
        self,
        latex_content: str,
        session_id: str = None,
        references: List[str] = None
    ) -> Dict[str, Any]:
        """
        Compile LaTeX content to PDF.
        
        Args:
            latex_content: The LaTeX source code
            session_id: Session ID for organizing files
            references: List of file paths to include (images, etc.)
            
        Returns:
            Dict with success status, pdf_path, and logs
        """
        # Create session directory
        if session_id:
            session_dir = self.work_dir / session_id
        else:
            session_dir = Path(tempfile.mkdtemp(dir=self.work_dir))
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy referenced files to session directory
        if references:
            for ref_path in references:
                src = Path(ref_path)
                if src.exists():
                    dst = session_dir / src.name
                    if not dst.exists():
                        shutil.copy2(src, dst)
        
        # Write LaTeX file
        tex_file = session_dir / "document.tex"
        tex_file.write_text(latex_content, encoding='utf-8')
        
        # Compile with pdflatex
        try:
            # Run pdflatex twice for references
            for _ in range(2):
                process = subprocess.run(
                    ['pdflatex', '-interaction=nonstopmode', '-output-directory', str(session_dir), str(tex_file)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=str(session_dir)
                )
            
            pdf_file = session_dir / "document.pdf"
            
            if pdf_file.exists():
                return {
                    "success": True,
                    "pdf_path": str(pdf_file),
                    "session_dir": str(session_dir),
                    "stdout": process.stdout,
                    "stderr": process.stderr,
                    "exit_code": process.returncode
                }
            else:
                return {
                    "success": False,
                    "pdf_path": None,
                    "stdout": process.stdout,
                    "stderr": process.stderr,
                    "exit_code": process.returncode
                }
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "pdf_path": None,
                "stdout": "",
                "stderr": "LaTeX compilation timed out after 60 seconds",
                "exit_code": -1
            }
        except Exception as e:
            return {
                "success": False,
                "pdf_path": None,
                "stdout": "",
                "stderr": f"Compilation error: {str(e)}",
                "exit_code": -1
            }
    
    def list_session_files(self, session_id: str) -> List[Dict[str, Any]]:
        """List all files in a session directory."""
        session_dir = self.work_dir / session_id
        if not session_dir.exists():
            return []
        
        files = []
        for file_path in session_dir.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "path": str(file_path),
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "type": file_path.suffix.lower()
                })
        
        return sorted(files, key=lambda x: x["modified"], reverse=True)
    
    def create_zip_package(self, session_id: str, files: List[str] = None) -> str:
        """Create a ZIP package of session files."""
        import zipfile
        
        session_dir = self.work_dir / session_id
        if not session_dir.exists():
            raise FileNotFoundError(f"Session directory not found: {session_id}")
        
        # Create zip file
        zip_path = session_dir / f"{session_id}_package.zip"
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            if files:
                # Include specified files
                for filename in files:
                    file_path = session_dir / filename
                    if file_path.exists():
                        zf.write(file_path, file_path.name)
            else:
                # Include all files
                for file_path in session_dir.iterdir():
                    if file_path.is_file() and file_path.name != zip_path.name:
                        zf.write(file_path, file_path.name)
        
        return str(zip_path)


# Check if pdflatex is available
def check_latex_installation() -> bool:
    """Check if LaTeX is installed.
    
    Note: In OpenSandbox mode, LaTeX is pre-installed in the sandbox container,
    not on the host. We always return True here because:
    1. The custom sandbox image (lambda-sandbox) includes texlive
    2. LaTeX compilation runs inside the sandbox, not on the host
    """
    from app.core.config import settings
    
    # In OpenSandbox mode, LaTeX is in the container
    if settings.CODE_EXECUTION_MODE == "opensandbox":
        return True
    
    # For local mode, check host installation
    try:
        subprocess.run(['pdflatex', '--version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
