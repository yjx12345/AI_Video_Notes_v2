from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field
from enum import Enum


class TaskSourceType(str, Enum):
    """任务来源类型枚举"""
    VIDEO = "video"  # 视频文件
    AUDIO = "audio"  # 音频文件
    TEXT = "text"  # 纯文本输入
    DOCUMENT = "document"  # 纯文档解析任务


class TaskStatus(str, Enum):
    """任务处理状态枚举"""
    PENDING = "pending"  # 等待中 (队列)
    PROCESSING_AUDIO = "processing_audio"  # 正在提取音频 (FFmpeg)
    TRANSCRIBING = "transcribing"  # 正在转写 (ASR API)
    ATTACHMENT_PARSING = "attachment_parsing"  # 正在解析附加文档 (MinerU)
    POLISHING = "polishing"  # 正在润色 (LLM API)
    FUSION = "fusion"  # 正在进行多模态融合
    COMPLETED = "completed"  # 处理完成
    FAILED = "failed"  # 失败


class AttachmentStatus(str, Enum):
    """附件解析状态 (统一大写)"""
    NONE = "NONE"
    PENDING = "PENDING"
    UPLOADING = "UPLOADING"
    PROCESSING = "PROCESSING"
    DONE = "DONE"
    FAILED = "FAILED"


class Task(SQLModel, table=True):
    """核心任务表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    source_type: TaskSourceType
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    original_file_path: Optional[str] = None
    audio_file_path: Optional[str] = None
    attachment_path: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    # 注意：这里默认值也改为了 AttachmentStatus.NONE (即 "NONE")
    attachment_status: AttachmentStatus = Field(default=AttachmentStatus.NONE, sa_column_kwargs={"nullable": False})
    attachment_content: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    attachment_error: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})

    raw_text: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    polished_text: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})
    final_note: Optional[str] = Field(default=None, sa_column_kwargs={"nullable": True})

    error_message: Optional[str] = None


class NoteTemplate(SQLModel, table=True):
    """笔记模板表"""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)
    prompt_content: str
    is_default: bool = False


class SystemConfig(SQLModel, table=True):
    """系统配置表 (如 Obsidian 路径)"""
    key: str = Field(primary_key=True)
    value: str