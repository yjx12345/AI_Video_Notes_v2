import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # === 基础信息 ===
    PROJECT_NAME: str = "AI Video Note Taker"
    VERSION: str = "1.0.0"

    # === 存储路径配置 ===
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    DATA_DIR: str = os.path.join(BASE_DIR, "data")
    UPLOAD_DIR: str = os.path.join(DATA_DIR, "uploads")
    DB_PATH: str = os.path.join(DATA_DIR, "database.db")

    # === [P0 重构] 工具目录配置 ===
    BIN_DIR: str = os.path.join(BASE_DIR, "bin")

    # 动态获取 FFmpeg 路径：优先使用本地 bin 目录，否则尝试系统 PATH
    @property
    def FFMPEG_PATH(self) -> str:
        local_ffmpeg = os.path.join(self.BIN_DIR, "ffmpeg.exe")
        if os.path.exists(local_ffmpeg):
            return local_ffmpeg
        return "ffmpeg"  # 回退到系统环境变量

    # === API 密钥配置 ===
    SILICONFLOW_API_KEY: str = "sk-sfomgfztneniuxbmwrzonjetmksdtxltbjqetbvxsvxwfpxd"
    CREC_API_KEY: str = "sk-ypyAh4NQw0DT95UGcHlRlHyDV76zKEmg8wZuXkNQpwV4V4LF"
    MINERU_API_TOKEN: str = (
        "eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFM1MTIifQ.eyJqdGkiOiI5ODkwMDMyMyIsInJvbCI6IlJPTEVfUkVHSVNURVIiLCJpc3MiOiJPcGVuWExhYiIsImlhdCI6MTc2NTk1NzYyMCwiY2xpZW50SWQiOiJsa3pkeDU3bnZ5MjJqa3BxOXgydyIsInBob25lIjoiIiwib3BlbklkIjpudWxsLCJ1dWlkIjoiYWZjZTgyMzUtNDUyMS00N2IzLTk3OGEtN2JjMzgyNmY3ODMyIiwiZW1haWwiOiIiLCJleHAiOjE3NjcxNjcyMjB9.OkT5qUJRWi8sZkuOhnP9fGglImKryoHP1Lkt58jNTlBb6JJKkbK8SdSi981Naj2QaZ4SKICmSQ93_PATkvI8Gg"
    )
    MINERU_MODEL_MODE: str = "vlm"

    # === 并发控制 ===
    MAX_FFMPEG_WORKERS: int = 2
    MAX_API_WORKERS: int = 10

    # === Obsidian 配置 ===
    OBSIDIAN_VAULT_PATH: str = ""

    class Config:
        env_file = ".env"

    def init_dirs(self):
        """初始化必要的目录"""
        os.makedirs(self.DATA_DIR, exist_ok=True)
        os.makedirs(self.UPLOAD_DIR, exist_ok=True)
        # 确保 bin 目录结构存在（虽然 exe 需要用户放进去）
        os.makedirs(self.BIN_DIR, exist_ok=True)


settings = Settings()
