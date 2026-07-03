from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import List
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
import re

from app.api.deps import get_current_active_user
from app.core.config import settings
from app.core.database import get_db
from app.core.hashid import decode_id
from app.models.models import Conversation, Message, User, UploadedFile
from app.services.notebook_service import NotebookService
from app.services.report_service import ReportService
from app.services.llm_service import LLMService
from app.services.pdf_service import PDFService
from app.api.v1.files import BackgroundTask, build_proxy_object_url, extract_oss_object_name, package_markdown_bytes, read_content_from_reference

router = APIRouter()
notebook_service = NotebookService()
report_service = ReportService()
llm_service = LLMService()
pdf_service = PDFService()

EXPORTS_DIR = Path("./data/exports")
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


def infer_visual_description(filename: str) -> str:
    stem = Path(filename).stem.replace("-", "_")
    parts = [part for part in stem.split("_") if part]
    replacements = {
        "corr": "correlation",
        "cfm": "confusion matrix",
        "cm": "confusion matrix",
        "dist": "distribution",
        "hist": "histogram",
        "boxplot": "box plot",
        "scatterplot": "scatter plot",
        "heatmap": "heatmap",
        "trend": "trend",
        "roc": "ROC curve",
        "pr": "precision-recall curve",
        "ts": "time series",
        "aqi": "AQI",
    }
    return " ".join(replacements.get(part.lower(), part) for part in parts) or "generated chart"


def rewrite_oss_urls_to_proxy(markdown: str) -> str:
    pattern = r'https://lambda-app-prod\.oss-cn-hongkong\.aliyuncs\.com/[^)\s]+'

    def replace(match):
        object_name = extract_oss_object_name(match.group(0))
        return build_proxy_object_url(object_name, absolute=False)

    return re.sub(pattern, replace, markdown)


async def get_latest_session_markdown_report(db: Session, user_id: int, session_id: int) -> tuple[str, str] | None:
    """Return the latest generated markdown file content for a conversation, if present."""
    markdown_files = db.query(UploadedFile).filter(
        UploadedFile.user_id == user_id,
        UploadedFile.conversation_id == str(session_id),
        UploadedFile.filename.like("generated/%")
    ).order_by(UploadedFile.created_at.desc()).all()

    for file in markdown_files:
        name = (file.original_name or file.filename or "").lower()
        mime = (file.mime_type or "").lower()
        if not (name.endswith(".md") or name.endswith(".markdown") or "markdown" in mime):
            continue

        try:
            markdown_bytes, _ = await read_content_from_reference(file.file_path)
            markdown_text = markdown_bytes.decode("utf-8", errors="replace")
            return markdown_text, file.original_name or f"lambda_report_{session_id}.md"
        except Exception as e:
            print(f"Failed to read existing markdown report {file.original_name}: {e}")

    return None


@router.post("/notebook/{conversation_id}")
async def export_notebook(
    conversation_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Export conversation as Jupyter Notebook."""
    real_id = decode_id(conversation_id)
    if real_id is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Get conversation
    conversation = db.query(Conversation).filter(
        Conversation.id == real_id,
        Conversation.user_id == current_user.id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Get messages
    messages = db.query(Message).filter(
        Message.conversation_id == real_id
    ).order_by(Message.created_at.asc()).all()
    
    # Convert to dict
    messages_list = [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "tool_calls": m.tool_calls,
            "tool_call_id": m.tool_call_id,
            "created_at": m.created_at.isoformat() if m.created_at else None
        }
        for m in messages
    ]
    
    # Extract tool calls from messages
    tool_calls = []
    for msg in messages_list:
        if msg.get("tool_calls"):
            try:
                tc_list = json.loads(msg["tool_calls"]) if isinstance(msg["tool_calls"], str) else msg["tool_calls"]
                for tc in tc_list:
                    # Try to find matching tool result
                    tool_result = tc.get("result")
                    if not tool_result:
                        for m in messages_list:
                            if m.get("role") == "tool" and m.get("tool_call_id") == tc.get("id"):
                                raw_content = m.get("content", "")
                                try:
                                    parsed_content = json.loads(raw_content)
                                    tool_result = parsed_content if isinstance(parsed_content, dict) else {"output": raw_content}
                                except Exception:
                                    tool_result = {"output": raw_content}
                                break
                    
                    tool_calls.append({
                        "id": tc.get("id"),
                        "name": tc.get("function", {}).get("name", ""),
                        "arguments": tc.get("function", {}).get("arguments", ""),
                        "result": tool_result
                    })
            except:
                pass
    
    # Generate notebook
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"lambda_notebook_{real_id}_{timestamp}.ipynb"
    filepath = EXPORTS_DIR / filename
    
    notebook_service.export_notebook(
        conversation_title=conversation.title,
        messages=messages_list,
        tool_calls=tool_calls,
        output_path=str(filepath)
    )
    
    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type="application/json"
    )


@router.post("/report/{conversation_id}")
async def export_report(
    conversation_id: str,
    format: str = Query(default="md", enum=["md", "pdf", "zip", "slides"]),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Export conversation as a comprehensive report (Markdown or PDF with embedded images)."""
    real_id = decode_id(conversation_id)
    if real_id is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Get conversation
    conversation = db.query(Conversation).filter(
        Conversation.id == real_id,
        Conversation.user_id == current_user.id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Get messages
    messages = db.query(Message).filter(
        Message.conversation_id == real_id
    ).order_by(Message.created_at.asc()).all()
    
    # Convert to dict
    messages_list = [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "tool_calls": m.tool_calls,
            "tool_call_id": m.tool_call_id,
            "created_at": m.created_at.isoformat() if m.created_at else None
        }
        for m in messages
    ]
    
    # Get user query (first user message)
    user_query = ""
    for msg in messages_list:
        if msg.get("role") == "user":
            user_query = msg.get("content", "")
            break
    
    # Extract tool calls
    tool_calls = []
    for msg in messages_list:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            try:
                tc_list = json.loads(msg["tool_calls"]) if isinstance(msg["tool_calls"], str) else msg["tool_calls"]
                for tc in tc_list:
                    # Find matching result
                    result = None
                    for m in messages_list:
                        if m.get("role") == "tool" and m.get("tool_call_id") == tc.get("id"):
                            result = {"output": m.get("content", "")}
                            break
                    
                    tool_calls.append({
                        "id": tc.get("id"),
                        "name": tc.get("function", {}).get("name", ""),
                        "arguments": tc.get("function", {}).get("arguments", ""),
                        "result": result
                    })
            except:
                pass

    generated_files = []
    db_generated_files = db.query(UploadedFile).filter(
        UploadedFile.user_id == current_user.id,
        UploadedFile.conversation_id == str(real_id),
        UploadedFile.filename.like("generated/%")
    ).order_by(UploadedFile.created_at.asc()).all()

    for file in db_generated_files:
        object_name = extract_oss_object_name(file.file_path)
        generated_files.append({
            "name": file.original_name,
            "description": infer_visual_description(file.original_name),
            "url": build_proxy_object_url(object_name, absolute=False),
            "object_name": object_name,
        })
    
    existing_markdown = await get_latest_session_markdown_report(db, current_user.id, real_id)
    if existing_markdown:
        report_content, source_markdown_name = existing_markdown
    else:
        source_markdown_name = None
        # Generate report using LLM only when the session has no markdown report file.
        try:
            prompt = report_service.generate_report_prompt(
                conversation_title=conversation.title,
                user_query=user_query,
                messages=messages_list,
                tool_calls=tool_calls,
                generated_files=generated_files
            )
            
            # Call LLM to generate report
            report_content = await llm_service.chat([
                {"role": "system", "content": "You are a professional data scientist writing comprehensive analysis reports."},
                {"role": "user", "content": prompt}
            ], model=conversation.model or settings.DEFAULT_MODEL)
            
        except Exception as e:
            # Fallback to basic report
            report_content = report_service.create_report_markdown(
                conversation_title=conversation.title,
                messages=messages_list,
                tool_calls=tool_calls,
                generated_files=generated_files
            )

    report_content = rewrite_oss_urls_to_proxy(report_content)
    
    # Generate timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if format == "pdf":
        # Generate PDF with embedded images
        filename = f"lambda_report_{real_id}_{timestamp}.pdf"
        filepath = EXPORTS_DIR / filename
        
        try:
            pdf_service.markdown_to_pdf(
                markdown_content=report_content,
                conversation_title=conversation.title,
                output_path=str(filepath),
                tool_calls=tool_calls
            )
            
            return FileResponse(
                path=str(filepath),
                filename=filename,
                media_type="application/pdf"
            )
        except Exception as e:
            import traceback
            print(f"PDF generation error: {e}\n{traceback.format_exc()}")
            # Fallback to markdown if PDF fails
            filename = f"lambda_report_{real_id}_{timestamp}.md"
            filepath = EXPORTS_DIR / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(report_content)
            
            return FileResponse(
                path=str(filepath),
                filename=filename,
                media_type="text/markdown"
            )
    elif format == "slides":
        filename = f"lambda_slides_{real_id}_{timestamp}.pdf"
        filepath = EXPORTS_DIR / filename
        
        try:
            pdf_service.markdown_to_slides_pdf(
                markdown_content=report_content,
                conversation_title=conversation.title,
                output_path=str(filepath)
            )
            
            return FileResponse(
                path=str(filepath),
                filename=filename,
                media_type="application/pdf"
            )
        except Exception as e:
            import traceback
            print(f"Slides PDF generation error: {e}\n{traceback.format_exc()}")
            # Fallback to regular PDF if slides fails
            try:
                filename = f"lambda_report_{real_id}_{timestamp}.pdf"
                filepath = EXPORTS_DIR / filename
                pdf_service.markdown_to_pdf(
                    markdown_content=report_content,
                    conversation_title=conversation.title,
                    output_path=str(filepath),
                    tool_calls=tool_calls
                )
                return FileResponse(
                    path=str(filepath),
                    filename=filename,
                    media_type="application/pdf"
                )
            except Exception:
                # Final fallback to markdown
                filename = f"lambda_report_{real_id}_{timestamp}.md"
                filepath = EXPORTS_DIR / filename
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(report_content)
                return FileResponse(
                    path=str(filepath),
                    filename=filename,
                    media_type="text/markdown"
                )
    elif format == "zip":
        filename = source_markdown_name or f"lambda_report_{real_id}_{timestamp}.md"
        temp_dir, zip_name = await package_markdown_bytes(report_content, filename)
        return FileResponse(
            path=str(temp_dir / zip_name),
            filename=zip_name,
            media_type="application/zip",
            background=BackgroundTask(lambda: shutil.rmtree(temp_dir))
        )
    else:
        # Generate Markdown
        filename = source_markdown_name or f"lambda_report_{real_id}_{timestamp}.md"
        filepath = EXPORTS_DIR / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        return FileResponse(
            path=str(filepath),
            filename=filename,
            media_type="text/markdown"
        )


@router.get("/list/{conversation_id}")
def list_exports(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List available exports for a conversation."""
    real_id = decode_id(conversation_id)
    if real_id is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Verify conversation ownership
    conversation = db.query(Conversation).filter(
        Conversation.id == real_id,
        Conversation.user_id == current_user.id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Find exports
    exports = []
    prefix = f"lambda_notebook_{real_id}_"
    for file in EXPORTS_DIR.glob(f"*{real_id}*"):
        exports.append({
            "filename": file.name,
            "type": "notebook" if file.suffix == ".ipynb" else "report",
            "created": datetime.fromtimestamp(file.stat().st_mtime).isoformat(),
            "size": file.stat().st_size
        })
    
    return {"exports": sorted(exports, key=lambda x: x["created"], reverse=True)}
