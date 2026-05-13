from fastapi import APIRouter, Depends, HTTPException, status
from app.api.deps import get_current_active_user
from app.models.models import User
from app.models.schemas import CodeExecutionRequest, CodeExecutionResponse
from app.services.code_execution_service import CodeExecutionService
from app.services.local_code_execution import get_local_code_execution_service
from app.core.config import settings

router = APIRouter()
code_service = get_local_code_execution_service() if settings.CODE_EXECUTION_MODE == "local" else CodeExecutionService()


@router.post("/execute", response_model=CodeExecutionResponse)
async def execute_code(
    request: CodeExecutionRequest,
    current_user: User = Depends(get_current_active_user)
):
    """Execute code in the configured local workspace."""
    try:
        result = await code_service.execute(
            code=request.code,
            language=request.language,
            timeout=request.timeout
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Code execution failed: {str(e)}"
        )


@router.get("/languages")
def get_supported_languages(
    current_user: User = Depends(get_current_active_user)
):
    """Get list of supported programming languages for code execution."""
    return {
        "languages": [
            {"id": "python", "name": "Python", "version": "3.12", "enabled": True},
            {"id": "javascript", "name": "JavaScript", "version": "Node.js 20", "enabled": True},
            {"id": "bash", "name": "Bash", "version": "5.0", "enabled": True},
            {"id": "r", "name": "R", "version": "4.3", "enabled": False},
            {"id": "sql", "name": "SQL", "version": "SQLite", "enabled": True}
        ]
    }
