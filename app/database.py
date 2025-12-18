from sqlalchemy import inspect, text
from sqlmodel import SQLModel, create_engine, Session
from app.core.config import settings

# SQLite 连接字符串
sqlite_url = f"sqlite:///{settings.DB_PATH}"

# check_same_thread=False 是为了让 FastAPI 的异步线程也能访问 SQLite
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})


def _run_migrations() -> None:
    """执行轻量级字段迁移，保证旧数据表兼容新增字段"""
    inspector = inspect(engine)

    try:
        task_columns = {col["name"] for col in inspector.get_columns("task")}
    except Exception:
        task_columns = set()

    statements = []

    if "attachment_path" not in task_columns:
        statements.append("ALTER TABLE task ADD COLUMN attachment_path VARCHAR")

    if "attachment_status" not in task_columns:
        # 新增列默认值改为大写 'NONE'
        statements.append("ALTER TABLE task ADD COLUMN attachment_status VARCHAR DEFAULT 'NONE'")
        statements.append("UPDATE task SET attachment_status = 'NONE' WHERE attachment_status IS NULL")

    if "attachment_content" not in task_columns:
        statements.append("ALTER TABLE task ADD COLUMN attachment_content TEXT")

    if "attachment_error" not in task_columns:
        statements.append("ALTER TABLE task ADD COLUMN attachment_error TEXT")

    # [关键修复] 强制将现有数据中的附件状态转为大写，修复 LookupError
    # 这条语句会确保 'none' -> 'NONE', 'pending' -> 'PENDING'
    statements.append("UPDATE task SET attachment_status = UPPER(attachment_status) WHERE attachment_status IS NOT NULL")

    if statements:
        with engine.begin() as conn:
            for stmt in statements:
                try:
                    conn.execute(text(stmt))
                except Exception as e:
                    # 忽略部分重复执行可能导致的错误 (如列已存在)，但 UPDATE 应该总是安全的
                    print(f"Migration warning: {e}")


def init_db():
    """初始化数据库表结构"""
    # 1. 确保数据目录存在
    settings.init_dirs()
    # 2. 根据 models.py 中的定义创建数据库表
    SQLModel.metadata.create_all(engine)
    # 3. 补充新增字段并修复数据
    _run_migrations()

def get_session():
    """FastAPI 依赖注入使用的 Session 生成器"""
    with Session(engine) as session:
        yield session