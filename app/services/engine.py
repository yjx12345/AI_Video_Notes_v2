import os
import asyncio
import subprocess
import httpx
import logging
from functools import partial
from sqlmodel import Session
from app.core.config import settings
from app.database import engine as db_engine
from app.models import SystemConfig
# [P2 重构] 引入 tenacity 重试模块
from tenacity import retry, stop_after_attempt, wait_exponential, before_sleep_log

# 配置日志
logger = logging.getLogger("uvicorn.error")


def get_current_api_key(key_name: str, default_value: str) -> str:
    """辅助函数：获取当前生效的 API Key (数据库优先 > 配置文件)"""
    try:
        with Session(db_engine) as session:
            conf = session.get(SystemConfig, key_name)
            if conf and conf.value:
                return conf.value
    except Exception as e:
        logger.error(f"读取数据库配置失败: {e}，回退到默认配置")
    return default_value


class MediaEngine:
    """媒体处理引擎 (FFmpeg)"""

    @staticmethod
    async def extract_audio(video_path: str, output_dir: str) -> str:
        filename = os.path.basename(video_path)
        audio_filename = f"optimized_{os.path.splitext(filename)[0]}.wav"
        audio_path = os.path.join(output_dir, audio_filename)

        ffmpeg_exe = settings.FFMPEG_PATH

        logger.info(f"🎬 FFmpeg 开始提取: {video_path} -> {audio_path}")

        command = [
            ffmpeg_exe, "-y", "-i", video_path,
            "-vn", "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le",
            audio_path
        ]

        loop = asyncio.get_running_loop()

        try:
            await loop.run_in_executor(
                None,
                partial(
                    subprocess.run,
                    command,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            )
            logger.info(f"✅ 音频提取完成: {audio_path}")
            return audio_path

        except FileNotFoundError:
            err_msg = f"未找到 FFmpeg 可执行文件，请检查 {ffmpeg_exe} 是否存在"
            logger.error(f"❌ 系统错误: {err_msg}")
            raise Exception(err_msg)
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            logger.error(f"❌ FFmpeg 失败: {err_msg}")
            raise Exception(f"FFmpeg 转码失败: {err_msg}")
        except Exception as e:
            logger.error(f"❌ FFmpeg 未知错误: {str(e)}")
            raise e


class AIEngine:
    """AI 服务引擎 (API 调用) - 已增加自动重试机制"""

    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    async def transcribe_audio(audio_path: str) -> str:
        api_key = get_current_api_key("siliconflow_key", settings.SILICONFLOW_API_KEY)

        url = "https://api.siliconflow.cn/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {api_key}"}

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        # [核心修复] 添加 trust_env=False 以忽略系统代理，防止 VPN 干扰连接
        async with httpx.AsyncClient(timeout=300.0, verify=False, trust_env=False) as client:
            with open(audio_path, "rb") as f:
                files = {'file': (os.path.basename(audio_path), f, "audio/wav")}
                data = {'model': "FunAudioLLM/SenseVoiceSmall"}

                logger.info(f"☁️ 开始调用 ASR API (Key: {api_key[:8]}...): {os.path.basename(audio_path)}")
                response = await client.post(url, headers=headers, files=files, data=data)

                if response.status_code != 200:
                    raise Exception(f"ASR API 错误 ({response.status_code}): {response.text}")

                return response.json().get("text", "")

    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    async def polish_text(raw_text: str) -> str:
        if not raw_text:
            return ""

        api_key = get_current_api_key("crec_key", settings.CREC_API_KEY)

        url = "https://ai-api.crec.cn/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        system_prompt = (
            "你是一名专业的文本编辑。请对以下语音识别生成的原始文本进行润色。"
            "要求：1. 修正错别字和口语化表达；2. 添加正确的标点符号；3. 合理分段；"
            "4. 保持原意不变，不要随意删减重要信息;5. 仅提供润色后的内容，不增加其他描述"
        )

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text}
            ],
            "temperature": 0.1
        }
        model1 = payload.get("model")

        logger.info(f"🧠 开始调用 {model1}润色 (Key: {api_key[:8]}...)...")
        async with httpx.AsyncClient(timeout=120.0, verify=False, trust_env=False) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                raise Exception(f"LLM API 错误 ({response.status_code}): {response.text}")
            return response.json()['choices'][0]['message']['content']

    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    async def polish_document(doc_markdown: str) -> str:
        if not doc_markdown:
            return ""

        api_key = get_current_api_key("crec_key", settings.CREC_API_KEY)
        url = "https://ai-api.crec.cn/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        system_prompt = (
            "你是一位专业的学习资料整理助手。请在保持原有章节结构的前提下，"
            "对以下通过 MinerU 解析得到的文档内容进行润色："
            "1) 修正 OCR 可能带来的错字；2) 完善句子并补充必要的说明；"
            "3) 使用 Markdown 层级展示结果；4) 保留图表及公式的文字描述。"
        )

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": doc_markdown}
            ],
            "temperature": 0.15
        }

        logger.info(f"📚 调用文档润色模型 (Key: {api_key[:8]}...)")
        async with httpx.AsyncClient(timeout=180.0, verify=False, trust_env=False) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                raise Exception(f"LLM API 错误 ({response.status_code}): {response.text}")
            return response.json()['choices'][0]['message']['content']

    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    async def generate_fusion_notes(doc_markdown: str, transcript: str) -> str:
        if not (doc_markdown or transcript):
            return ""

        api_key = get_current_api_key("crec_key", settings.CREC_API_KEY)
        url = "https://ai-api.crec.cn/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        system_prompt = (
            "你是一位专业的课程助教。现在需要根据讲义内容（来源：MinerU Markdown）"
            "与课堂录音转写文本（来源：ASR）生成一份融合笔记："
            "- 以讲义的章节与层级为骨架；"
            "- 将录音中的解释、举例和拓展补充到对应的小节；"
            "- 对关键公式/图表给出简要解释；"
            "- 输出结构化 Markdown，层次清晰，可直接用于学习复习。"
        )

        user_content = (
            "资料 1：讲义内容\n" + doc_markdown +
            "\n\n资料 2：课堂录音转写\n" + transcript
        )

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.2
        }

        logger.info(f"🧩 调用融合笔记生成模型 (Key: {api_key[:8]}...)")
        async with httpx.AsyncClient(timeout=240.0, verify=False, trust_env=False) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                raise Exception(f"LLM API 错误 ({response.status_code}): {response.text}")
            return response.json()["choices"][0]["message"]["content"]

    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )
    async def generate_note(text: str, template_prompt: str) -> str:
        if not text:
            return ""

        api_key = get_current_api_key("crec_key", settings.CREC_API_KEY)

        url = "https://ai-api.crec.cn/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": template_prompt},
                {"role": "user", "content": f"请根据上述要求，总结以下文本：\n\n{text}"}
            ],
            "temperature": 0.3
        }
        model2 = payload.get("model")

        logger.info(f"📝 调用{model2}开始生成最终笔记...")
        async with httpx.AsyncClient(timeout=120.0, verify=False, trust_env=False) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                raise Exception(f"LLM API 错误 ({response.status_code}): {response.text}")
            return response.json()['choices'][0]['message']['content']
