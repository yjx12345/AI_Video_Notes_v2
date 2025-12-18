import os
import uvicorn
import mimetypes
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.database import init_db, engine
from app.core.config import settings
from app.models import Task, TaskStatus
from app.routers import tasks, settings as settings_router

import logging

# ================== Service 专用日志配置 ==================
log_dir = os.path.join(settings.BASE_DIR, "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "service.log")

file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
file_handler.setFormatter(formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.handlers.clear()
logger.addHandler(file_handler)

# ================== MIME 类型修复 ==================
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")

# ================== 僵尸任务清理 ==================
def fix_zombie_tasks():
    try:
        with Session(engine) as session:
            zombies = session.exec(
                select(Task).where(
                    Task.status.in_([
                        TaskStatus.PROCESSING_AUDIO,
                        TaskStatus.TRANSCRIBING,
                        TaskStatus.ATTACHMENT_PARSING,
                        TaskStatus.POLISHING,
                        TaskStatus.FUSION,
                        TaskStatus.PENDING
                    ])
                )
            ).all()

            if zombies:
                logger.warning("发现 %d 个异常中断的任务，正在重置状态...", len(zombies))
                for task in zombies:
                    try:
                        task.status = TaskStatus.FAILED
                        task.error_message = "系统服务重启或异常中断，任务自动终止。请手动重试。"
                        session.add(task)
                    except Exception as e_task:
                        logger.error("处理任务 %s 出现错误: %s", getattr(task, "id", "unknown"), e_task)
                try:
                    session.commit()
                    logger.info("已清理 %d 个僵尸任务。", len(zombies))
                except Exception as e_commit:
                    logger.error("提交僵尸任务状态变更失败: %s", e_commit)
            else:
                logger.info("系统状态健康，无异常任务。")
    except Exception as e:
        logger.error("自检过程出现错误（可能是首次运行）: %s", e)

# ================== 生命周期管理 ==================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1️⃣ 初始化数据库
    try:
        init_db()
        logger.info("数据库初始化完成: %s", settings.DB_PATH)
    except Exception as e_db:
        logger.error("数据库初始化失败: %s", e_db)

    # 2️⃣ 执行僵尸任务清理
    fix_zombie_tasks()

    # 3️⃣ 确认数据目录
    try:
        for dir_path in [settings.DATA_DIR, settings.BIN_DIR]:
            os.makedirs(dir_path, exist_ok=True)
            logger.info("确认目录存在: %s", dir_path)
    except Exception as e_dir:
        logger.error("创建数据目录失败: %s", e_dir)

    yield
    logger.info("服务正在关闭...")

# ================== FastAPI 应用 ==================
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(settings_router.router)

# ================== 静态文件挂载 ==================
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
assets_dir = os.path.join(static_dir, "assets")
for d in [static_dir, assets_dir]:
    try:
        os.makedirs(d, exist_ok=True)
        logger.info("确认静态目录存在: %s", d)
    except Exception as e:
        logger.error("创建静态目录失败: %s", e)

app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ================== 根路由 ==================
@app.get("/")
async def root():
    index_file = os.path.join(static_dir, "index.html")
    if not os.path.exists(index_file):
        logger.warning("前端文件未生成，请先运行 'cd frontend && npm run build'")
        return {"error": "前端文件未生成，请先运行 'cd frontend && npm run build'"}
    return FileResponse(index_file)

# ================== 主入口 ==================
if __name__ == "__main__":
    settings.init_dirs()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=1314,
        reload=False  # Service 下必须禁用
    )
