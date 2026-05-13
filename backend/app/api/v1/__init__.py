from fastapi import APIRouter
from app.api.v1 import admin, announcements, auth, users, conversations, chat, files, code_execution, export

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(announcements.router, prefix="/announcements", tags=["announcements"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(code_execution.router, prefix="/code", tags=["code-execution"])
api_router.include_router(export.router, prefix="/export", tags=["export"])
