from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings
from typing import Optional, List


class Settings(BaseSettings):
    # Local-first defaults. The open-source build stores data under ./data.
    DATABASE_URL: str = "sqlite:///./data/lambda_local.db"
    LOCAL_MODE: bool = True
    LOCAL_USER_EMAIL: str = "local@lambda.local"
    LOCAL_USER_NAME: str = "Local User"
    
    # Security
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days
    
    # LLM Configuration
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    XIAOMI_API_KEY: str = ""
    XIAOMI_BASE_URL: str = "https://token-plan-sgp.xiaomimimo.com/v1"
    DEFAULT_MODEL: str = Field(
        default="deepseek-v4-flash",
        validation_alias=AliasChoices("DEFAULT_MODEL", "MODEL"),
    )
    
    # Available Models
    AVAILABLE_MODELS: List[str] = [
        "deepseek-v4-pro",
        "deepseek-v4-flash",
        "claude-sonnet-4-6",
        "openai/gpt-5.3-codex",
        "mimo-v2.5-pro",
        "mimo-v2.5",
    ]
    MULTIMODAL_MODELS: List[str] = [
        "claude-sonnet-4-6",
        "openai/gpt-5.3-codex",
        "mimo-v2.5",
    ]
    MULTIMODAL_IMAGE_DETAIL: str = "high"
    MULTIMODAL_IMAGE_MAX_BYTES: int = 8 * 1024 * 1024
    
    # Code Execution
    CODE_EXECUTION_TIMEOUT: int = 900
    MAX_OUTPUT_LENGTH: int = 1000000
    
    # Local open-source build executes tools in a local workspace directory.
    CODE_EXECUTION_MODE: str = "local"
    LOCAL_WORKSPACE_ROOT: str = "./data/workspaces"
    
    # OpenSandbox Configuration
    # Custom sandbox image with additional packages (e.g., LaTeX)
    # Build custom image: cd sandbox-docker && docker build -t lambda-sandbox:latest .
    SANDBOX_IMAGE: str = "opensandbox/code-interpreter:v1.0.2"
    
    # OpenSandbox container max lifetime. OpenSandbox treats this as container
    # TTL, not app-level idle timeout, so keep it comfortably above user work.
    SANDBOX_CONTAINER_TIMEOUT_MINUTES: int = 180

    # App-level idle timeout. The backend reaps sessions after this much
    # inactivity, while active sandboxes can live longer than 30 minutes.
    SANDBOX_IDLE_TIMEOUT_MINUTES: int = 30
    SANDBOX_CLEANUP_ORPHANS_ON_STARTUP: bool = True
    SANDBOX_PREINSTALLED_PACKAGES: bool = False
    
    # CORS
    FRONTEND_URL: str = "http://localhost:3000"
    
    # Agent Configuration
    MAX_AGENT_ITERATIONS: int = 50  # Maximum tool execution iterations per conversation
    
    # Aliyun OSS Configuration (unused in local mode)
    ALIYUN_OSS_ACCESS_KEY_ID: str = ""
    ALIYUN_OSS_ACCESS_KEY_SECRET: str = ""
    ALIYUN_OSS_BUCKET_NAME: str = "lambda-app-prod"
    ALIYUN_OSS_ENDPOINT: str = "oss-cn-hongkong.aliyuncs.com"
    ALIYUN_OSS_BASE_URL: str = "https://lambda-app-prod.oss-cn-hongkong.aliyuncs.com"
    
    # File Storage Mode
    FILE_STORAGE_MODE: str = "local"
    
    class Config:
        env_file = ".env"


settings = Settings()
