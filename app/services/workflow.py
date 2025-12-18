import asyncio
import logging
import traceback
from datetime import datetime
from typing import Any, Dict, Optional

from sqlmodel import Session

from app.core.config import settings
from app.database import engine
from app.models import (
    AttachmentStatus,
    Task,
    TaskSourceType,
    TaskStatus,
)
from app.services.engine import AIEngine, MediaEngine
from app.services.mineru_service import MineruService

logger = logging.getLogger("uvicorn.error")


class TaskWorkflow:
    """任务工作流管理器，负责并发控制、状态流转、错误处理"""

    _ffmpeg_semaphore = asyncio.Semaphore(settings.MAX_FFMPEG_WORKERS)
    _api_semaphore = asyncio.Semaphore(settings.MAX_API_WORKERS)

    @classmethod
    async def process_task(cls, task_id: int) -> None:
        logger.info(f"🚀 开始处理任务 ID: {task_id}")

        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                logger.error(f"任务 {task_id} 不存在")
                return
            task.error_message = None
            session.add(task)
            session.commit()

            # === [新增/修改部分 START] ===
            session.refresh(task)  # 1. 刷新：重新加载数据，防止 commit 后属性过期
            session.expunge(task)  # 2. 移除：将对象与 Session 解绑，使其在 Session 关闭后仍可访问数据
            # === [新增/修改部分 END] ===

        try:
            # 这里现在可以安全访问 task.source_type 了，因为数据已经加载且对象已解绑
            if task.source_type == TaskSourceType.TEXT:
                await cls._handle_text_task(task_id)
                logger.info(f"🏁 文本任务 {task_id} 处理完成")
                return

            if task.source_type == TaskSourceType.DOCUMENT:
                attachment_result = await cls._process_attachment(task_id, mark_task_status=True)
                await cls._complete_document_task(task_id, attachment_result.get("attachment_content", ""))
                logger.info(f"🏁 文档任务 {task_id} 处理完成")
                return

            audio_task = None
            if task.source_type in {TaskSourceType.VIDEO, TaskSourceType.AUDIO}:
                audio_task = asyncio.create_task(cls._process_audio(task_id))

            attachment_task = None
            if task.attachment_path:
                attachment_task = asyncio.create_task(cls._process_attachment(task_id))

            audio_result: Optional[Dict[str, Any]] = None
            attachment_result: Optional[Dict[str, Any]] = None
            attachment_error: Optional[BaseException] = None

            if audio_task and attachment_task:
                audio_result, attachment_result = await asyncio.gather(
                    audio_task, attachment_task, return_exceptions=True
                )
            elif audio_task:
                audio_result = await audio_task
            elif attachment_task:
                attachment_result = await attachment_task

            if isinstance(audio_result, Exception):
                raise audio_result

            if isinstance(attachment_result, Exception):
                attachment_error = attachment_result
                attachment_result = None

            await cls._finalize_multimodal_task(
                task_id=task_id,
                audio_result=audio_result,
                attachment_result=attachment_result,
                attachment_error=attachment_error,
            )

            logger.info(f"🏁 任务 {task_id} 全流程完成！")

        except Exception as exc:  # noqa: BLE001
            logger.error(f"处理任务 {task_id} 异常: {exc}\n{traceback.format_exc()}")
            cls._handle_failure(task_id, str(exc))

    # ------------------------------------------------------------------
    # 基础流程分支
    # ------------------------------------------------------------------
    @classmethod
    async def _handle_text_task(cls, task_id: int) -> None:
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                return
            text_to_polish = task.raw_text or ""
            task.status = TaskStatus.POLISHING
            task.updated_at = datetime.now()
            session.add(task)
            session.commit()

        async with cls._api_semaphore:
            polished = await AIEngine.polish_text(text_to_polish)

        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                return
            task.polished_text = polished
            if not task.final_note:
                task.final_note = polished
            task.status = TaskStatus.COMPLETED
            task.updated_at = datetime.now()
            session.add(task)
            session.commit()

    @classmethod
    async def _complete_document_task(cls, task_id: int, markdown: str) -> None:
        async with cls._api_semaphore:
            polished = await AIEngine.polish_document(markdown)

        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                return
            task.raw_text = markdown
            task.polished_text = polished
            task.final_note = polished
            task.status = TaskStatus.COMPLETED
            task.updated_at = datetime.now()
            session.add(task)
            session.commit()

    # ------------------------------------------------------------------
    # 音频与附件子流程
    # ------------------------------------------------------------------
    @classmethod
    async def _process_audio(cls, task_id: int) -> Dict[str, str]:
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                raise ValueError(f"任务 {task_id} 不存在")

            if task.source_type == TaskSourceType.VIDEO:
                task.status = TaskStatus.PROCESSING_AUDIO
                task.updated_at = datetime.now()
                session.add(task)
                session.commit()

                async with cls._ffmpeg_semaphore:
                    audio_path = await MediaEngine.extract_audio(
                        task.original_file_path, settings.UPLOAD_DIR
                    )
                task.audio_file_path = audio_path
                task.updated_at = datetime.now()
                session.add(task)
                session.commit()

            elif task.source_type == TaskSourceType.AUDIO and task.original_file_path:
                task.audio_file_path = task.original_file_path
                task.updated_at = datetime.now()
                session.add(task)
                session.commit()

            if task.source_type in {TaskSourceType.VIDEO, TaskSourceType.AUDIO}:
                task.status = TaskStatus.TRANSCRIBING
                task.updated_at = datetime.now()
                session.add(task)
                session.commit()

                async with cls._api_semaphore:
                    raw_text = await AIEngine.transcribe_audio(task.audio_file_path)

                task.raw_text = raw_text
                task.updated_at = datetime.now()
                session.add(task)
                session.commit()
            else:
                raw_text = task.raw_text or ""

            task.status = TaskStatus.POLISHING
            task.updated_at = datetime.now()
            session.add(task)
            session.commit()

        async with cls._api_semaphore:
            polished = await AIEngine.polish_text(raw_text)

        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                return {"raw_text": raw_text, "polished_text": polished}
            task.polished_text = polished
            task.updated_at = datetime.now()
            session.add(task)
            session.commit()

        return {"raw_text": raw_text, "polished_text": polished}

    @classmethod
    async def _process_attachment(cls, task_id: int, mark_task_status: bool = False) -> Dict[str, str]:
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                raise ValueError(f"任务 {task_id} 不存在")
            doc_path = task.attachment_path or task.original_file_path
            source_type = task.source_type
            if not doc_path:
                raise ValueError("未找到可解析的附件路径")

        cls._update_attachment_state(
            task_id,
            AttachmentStatus.UPLOADING,
            update_task_status=mark_task_status,
        )
        cls._update_attachment_state(task_id, AttachmentStatus.PROCESSING)

        try:
            async with cls._api_semaphore:
                markdown, batch_id = await MineruService.parse_document(doc_path)
        except Exception as exc:  # noqa: BLE001
            cls._mark_attachment_failure(
                task_id,
                str(exc),
                fatal=(mark_task_status and source_type == TaskSourceType.DOCUMENT),
            )
            raise

        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                return {"attachment_content": markdown, "batch_id": batch_id}
            task.attachment_status = AttachmentStatus.DONE
            task.attachment_content = markdown
            task.attachment_error = None
            if mark_task_status and task.source_type == TaskSourceType.DOCUMENT:
                task.status = TaskStatus.POLISHING
            task.updated_at = datetime.now()
            session.add(task)
            session.commit()

        return {"attachment_content": markdown, "batch_id": batch_id}

    # ------------------------------------------------------------------
    # 汇总阶段
    # ------------------------------------------------------------------
    @classmethod
    async def _finalize_multimodal_task(
        cls,
        task_id: int,
        audio_result: Optional[Dict[str, str]],
        attachment_result: Optional[Dict[str, str]],
        attachment_error: Optional[BaseException],
    ) -> None:
        if attachment_result and audio_result:
            await cls._generate_fusion_notes(
                task_id,
                transcript=audio_result.get("polished_text") or audio_result.get("raw_text") or "",
                doc_markdown=attachment_result.get("attachment_content") or "",
            )
            return

        await cls._complete_audio_only_task(task_id, audio_result, attachment_error)

    @classmethod
    async def _generate_fusion_notes(
        cls,
        task_id: int,
        transcript: str,
        doc_markdown: str,
    ) -> None:
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                return
            task.status = TaskStatus.FUSION
            task.updated_at = datetime.now()
            session.add(task)
            session.commit()

        async with cls._api_semaphore:
            fusion_note = await AIEngine.generate_fusion_notes(doc_markdown, transcript)

        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                return
            task.final_note = fusion_note
            task.status = TaskStatus.COMPLETED
            task.updated_at = datetime.now()
            session.add(task)
            session.commit()

    @classmethod
    async def _complete_audio_only_task(
        cls,
        task_id: int,
        audio_result: Optional[Dict[str, str]],
        attachment_error: Optional[BaseException],
    ) -> None:
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                return

            if attachment_error:
                message = ("⚠️ 文档解析失败，仅使用音频内容生成。\n" + str(attachment_error))
                task.attachment_status = AttachmentStatus.FAILED
                task.attachment_error = str(attachment_error)
                base_text = task.final_note or task.polished_text or task.raw_text or ""
                if base_text:
                    note = f"{base_text}\n\n> {message}"
                else:
                    note = f"> {message}"
                task.final_note = note
            else:
                if audio_result and not task.final_note:
                    task.final_note = audio_result.get("polished_text") or audio_result.get("raw_text")

            task.status = TaskStatus.COMPLETED
            task.updated_at = datetime.now()
            session.add(task)
            session.commit()

    # ------------------------------------------------------------------
    # 状态更新工具
    # ------------------------------------------------------------------
    @classmethod
    def _update_attachment_state(
        cls,
        task_id: int,
        status: AttachmentStatus,
        *,
        update_task_status: bool = False,
    ) -> None:
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                return
            task.attachment_status = status
            if status in {AttachmentStatus.UPLOADING, AttachmentStatus.PROCESSING}:
                task.attachment_error = None
            if update_task_status:
                task.status = TaskStatus.ATTACHMENT_PARSING
            task.updated_at = datetime.now()
            session.add(task)
            session.commit()

    @classmethod
    def _mark_attachment_failure(cls, task_id: int, error_message: str, *, fatal: bool = False) -> None:
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                return
            task.attachment_status = AttachmentStatus.FAILED
            task.attachment_error = error_message
            task.updated_at = datetime.now()
            if fatal:
                task.status = TaskStatus.FAILED
                task.error_message = error_message
            session.add(task)
            session.commit()

    @classmethod
    def _handle_failure(cls, task_id: int, error_message: str) -> None:
        with Session(engine) as session:
            task = session.get(Task, task_id)
            if not task:
                return
            task.status = TaskStatus.FAILED
            task.error_message = error_message
            task.updated_at = datetime.now()
            session.add(task)
            session.commit()