from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
from app.database import get_session
from app.models import NoteTemplate, SystemConfig
from app.core.config import settings

router = APIRouter(prefix="/settings", tags=["设置管理"])


# === 数据模型 ===
class ConfigUpdate(BaseModel):
    obsidian_path: str
    siliconflow_key: Optional[str] = None
    crec_key: Optional[str] = None
    mineru_api_token: Optional[str] = None
    mineru_model_mode: Optional[str] = None


class TemplateCreate(BaseModel):
    name: str
    prompt_content: str


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    prompt_content: Optional[str] = None


# === 配置接口 ===
@router.get("/config")
def get_config(session: Session = Depends(get_session)):
    """获取当前系统配置"""
    obsidian_conf = session.get(SystemConfig, "obsidian_vault_path")
    silicon_conf = session.get(SystemConfig, "siliconflow_key")
    crec_conf = session.get(SystemConfig, "crec_key")
    mineru_token_conf = session.get(SystemConfig, "mineru_api_token")
    mineru_mode_conf = session.get(SystemConfig, "mineru_model_mode")

    return {
        "obsidian_path": obsidian_conf.value if obsidian_conf else "",
        "siliconflow_key": silicon_conf.value if silicon_conf else settings.SILICONFLOW_API_KEY,
        "crec_key": crec_conf.value if crec_conf else settings.CREC_API_KEY,
        "mineru_api_token": mineru_token_conf.value if mineru_token_conf else settings.MINERU_API_TOKEN,
        "mineru_model_mode": mineru_mode_conf.value if mineru_mode_conf else settings.MINERU_MODEL_MODE,
    }


@router.post("/config")
def update_config(data: ConfigUpdate, session: Session = Depends(get_session)):
    """更新系统配置"""

    def upsert(key: str, value: Optional[str]):
        if value is None:
            return
        item = session.get(SystemConfig, key)
        if not item:
            item = SystemConfig(key=key, value=value)
        else:
            item.value = value
        session.add(item)

    mineru_mode = data.mineru_model_mode.lower() if data.mineru_model_mode else None
    if mineru_mode and mineru_mode not in {"vlm", "pipeline"}:
        raise HTTPException(status_code=400, detail="MinerU 模式仅支持 vlm 或 pipeline")

    upsert("obsidian_vault_path", data.obsidian_path)
    upsert("siliconflow_key", data.siliconflow_key)
    upsert("crec_key", data.crec_key)
    upsert("mineru_api_token", data.mineru_api_token)
    if mineru_mode:
        upsert("mineru_model_mode", mineru_mode)

    session.commit()
    return {"ok": True}


# === 模板接口 ===
@router.get("/templates", response_model=List[NoteTemplate])
def list_templates(session: Session = Depends(get_session)):
    templates = session.exec(select(NoteTemplate)).all()
    if not templates:
        defaults = [
            NoteTemplate(name="通用总结",
                         prompt_content="请将文本总结为Markdown格式，包含：\n## 核心观点\n## 关键细节\n## 待办事项"),
            NoteTemplate(name="会议纪要",
                         prompt_content="请整理为会议纪要，包含：\n- 会议主题\n- 决议事项\n- 任务分工\n- 下一步计划"),
            NoteTemplate(name="学习笔记",
                         prompt_content="请整理为学习笔记，提取：\n1. 知识点架构\n2. 重要概念解释\n3. 案例分析")
        ]
        for t in defaults:
            session.add(t)
        session.commit()
        templates = session.exec(select(NoteTemplate)).all()
    return templates


@router.post("/templates", response_model=NoteTemplate)
def create_template(data: TemplateCreate, session: Session = Depends(get_session)):
    existing = session.exec(select(NoteTemplate).where(NoteTemplate.name == data.name)).first()
    if existing:
        raise HTTPException(status_code=400, detail="模板名称已存在")

    tpl = NoteTemplate(name=data.name, prompt_content=data.prompt_content)
    session.add(tpl)
    session.commit()
    session.refresh(tpl)
    return tpl


# [新增] 更新模板接口
@router.patch("/templates/{template_id}", response_model=NoteTemplate)
def update_template(template_id: int, data: TemplateUpdate, session: Session = Depends(get_session)):
    tpl = session.get(NoteTemplate, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")

    # 如果修改了名称，检查是否与其他模板重名
    if data.name and data.name != tpl.name:
        existing = session.exec(select(NoteTemplate).where(NoteTemplate.name == data.name)).first()
        if existing:
            raise HTTPException(status_code=400, detail="模板名称已存在")
        tpl.name = data.name

    if data.prompt_content:
        tpl.prompt_content = data.prompt_content

    session.add(tpl)
    session.commit()
    session.refresh(tpl)
    return tpl


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, session: Session = Depends(get_session)):
    tpl = session.get(NoteTemplate, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    session.delete(tpl)
    session.commit()
    return {"ok": True}
