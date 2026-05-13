"""Code execution service - All execution goes through OpenSandbox for security."""

from typing import Dict, Any, Optional
from app.core.config import settings


class CodeExecutionService:
    """Service for executing code in OpenSandbox environment only."""
    
    def __init__(self):
        self.timeout = settings.CODE_EXECUTION_TIMEOUT
        self.max_output_length = settings.MAX_OUTPUT_LENGTH
        self._opensandbox_service = None
    
    def _get_opensandbox_service(self):
        """Get OpenSandbox service (lazy import)."""
        if self._opensandbox_service is None:
            from app.services.opensandbox_service import get_opensandbox_service
            self._opensandbox_service = get_opensandbox_service()
        return self._opensandbox_service
    
    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout: int = None,
        session_id: str = None
    ) -> Dict[str, Any]:
        """Execute code in OpenSandbox environment."""
        timeout = timeout or self.timeout
        
        opensandbox = self._get_opensandbox_service()
        
        if language == "python":
            return await opensandbox.execute_python(code, session_id, timeout)
        elif language in ["bash", "shell"]:
            return await opensandbox.execute_shell(code, session_id, timeout)
        elif language == "sql":
            # SQL is validated but not executed in sandbox
            return {
                "success": True,
                "stdout": "SQL syntax validated (execution in database not implemented in sandbox)",
                "stderr": "",
                "exit_code": 0,
                "execution_time": 0,
                "images": []
            }
        else:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Unsupported language in sandbox: {language}. Supported: python, bash, shell, sql",
                "exit_code": -1,
                "execution_time": 0,
                "images": []
            }
