import os
import shutil
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session, select
from pydantic import BaseModel
from app.database import get_session
from app.models import (
    AttachmentStatus,
    Task,
    TaskStatus,
    TaskSourceType,
    NoteTemplate,
    SystemConfig,
)
from app.services.workflow import TaskWorkflow
from app.services.engine import AIEngine
from app.core.config import settings

router = APIRouter(prefix="/tasks", tags=["任务管理"])


class NoteGenerationRequest(BaseModel):
    template_id: int


# ... (upload_task, create_text_task, list_tasks, get_task 保持不变) ...
# 为节省篇幅，这里仅展示 upload_task 等头部引用，请保留原文件中的其他接口

@router.post("/upload", response_model=Task)
async def upload_task(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(None),
        attachment_file: UploadFile = File(None),
        source_type: TaskSourceType = Form(...),
        title: Optional[str] = Form(None),
        session: Session = Depends(get_session)
):
    def store_upload(upload: UploadFile) -> str:
        upload.file.seek(0)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
        safe_filename = f"{timestamp}_{upload.filename}"
        file_path = os.path.join(settings.UPLOAD_DIR, safe_filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(upload.file, buffer)
        return file_path

    if source_type == TaskSourceType.DOCUMENT:
        doc_upload = attachment_file or file
        if not doc_upload:
            raise HTTPException(status_code=400, detail="文档任务需要上传一个文件")
        doc_path = store_upload(doc_upload)
        task = Task(
            title=title or doc_upload.filename,
            source_type=TaskSourceType.DOCUMENT,
            status=TaskStatus.PENDING,
            original_file_path=doc_path,
            attachment_path=doc_path,
            attachment_status=AttachmentStatus.PENDING,
        )
    else:
        if not file:
            raise HTTPException(status_code=400, detail="请提供主文件")
        main_path = store_upload(file)
        attachment_path = None
        attachment_status = AttachmentStatus.NONE
        if attachment_file:
            attachment_path = store_upload(attachment_file)
            attachment_status = AttachmentStatus.PENDING
        task = Task(
            title=title or file.filename,
            source_type=source_type,
            status=TaskStatus.PENDING,
            original_file_path=main_path,
            attachment_path=attachment_path,
            attachment_status=attachment_status,
        )

    session.add(task)
    session.commit()
    session.refresh(task)
    background_tasks.add_task(TaskWorkflow.process_task, task.id)
    return task


@router.post("/create_text", response_model=Task)
async def create_text_task(
        background_tasks: BackgroundTasks,
        title: str = Form(...),
        content: str = Form(...),
        session: Session = Depends(get_session)
):
    # ... (保持原代码不变) ...
    new_task = Task(title=title, source_type=TaskSourceType.TEXT, status=TaskStatus.PENDING, raw_text=content)
    session.add(new_task)
    session.commit()
    session.refresh(new_task)
    background_tasks.add_task(TaskWorkflow.process_task, new_task.id)
    return new_task


@router.get("/", response_model=List[Task])
async def list_tasks(session: Session = Depends(get_session)):
    statement = select(Task).order_by(Task.created_at.desc())
    return session.exec(statement).all()


@router.get("/{task_id}", response_model=Task)
async def get_task(task_id: int, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task: raise HTTPException(status_code=404, detail="Task not found")
    return task


# === [修改点] 支持修改 title ===
@router.patch("/{task_id}", response_model=Task)
async def update_task_content(
        task_id: int,
        title: Optional[str] = None,  # 新增
        raw_text: Optional[str] = None,
        polished_text: Optional[str] = None,
        final_note: Optional[str] = None,
        session: Session = Depends(get_session)
):
    """
    支持前端可视化编辑：更新任务的标题或文本内容
    """
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if title is not None:
        task.title = title
    if raw_text is not None:
        task.raw_text = raw_text
    if polished_text is not None:
        task.polished_text = polished_text
    if final_note is not None:
        task.final_note = final_note

    task.updated_at = datetime.now()
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


@router.delete("/{task_id}")
async def delete_task(task_id: int, session: Session = Depends(get_session)):
    # ... (保持原代码不变) ...
    task = session.get(Task, task_id)
    if not task: raise HTTPException(status_code=404, detail="Task not found")
    paths_to_remove = set()
    if task.original_file_path:
        paths_to_remove.add(task.original_file_path)
    if task.audio_file_path:
        paths_to_remove.add(task.audio_file_path)
    if task.attachment_path:
        paths_to_remove.add(task.attachment_path)

    for p in paths_to_remove:
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
    session.delete(task)
    session.commit()
    return {"ok": True}


@router.post("/{task_id}/generate_note")
async def generate_note(task_id: int, request: NoteGenerationRequest, session: Session = Depends(get_session)):
    # ... (保持原代码不变) ...
    task = session.get(Task, task_id)
    if not task: raise HTTPException(status_code=404, detail="任务不存在")
    template = session.get(NoteTemplate, request.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    segments = []
    if task.polished_text:
        segments.append("【润色文本】\n" + task.polished_text)
    elif task.raw_text:
        segments.append("【原始文本】\n" + task.raw_text)
    if task.attachment_content:
        segments.append("【文档解析】\n" + task.attachment_content)

    source_text = "\n\n".join(segments)
    if not source_text:
        raise HTTPException(status_code=400, detail="该任务没有可用的文本内容")
    try:
        note_content = await AIEngine.generate_note(source_text, template.prompt_content)
        task.final_note = note_content
        task.updated_at = datetime.now()
        session.add(task)
        session.commit()
        return {"final_note": note_content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/export_obsidian")
async def export_to_obsidian(task_id: int, session: Session = Depends(get_session)):
    # ... (保持原代码不变) ...
    task = session.get(Task, task_id)
    if not task: raise HTTPException(status_code=404, detail="任务不存在")
    config = session.get(SystemConfig, "obsidian_vault_path")
    if not config or not config.value: raise HTTPException(status_code=400, detail="未设置 Obsidian 库路径")
    vault_path = config.value
    if not os.path.exists(vault_path): raise HTTPException(status码=400, detail=f"Obsidian 路径不存在: {vault_path}")
    if not task.final_note: raise HTTPException(status_code=400, detail="没有可导出的笔记内容")
    safe_title = "".join([c for c in task.title if c.isalpha() or c.isdigit() or c in (' ', '-', '_')]).strip()
    filename = f"{datetime.now().strftime('%Y%m%d')}_{safe_title}.md"
    file_path = os.path.join(vault_path, filename)
    try:
        content = f"# {task.title}\n\nCreated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{task.final_note}"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"ok": True, "path": file_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入文件失败: {str(e)}")
