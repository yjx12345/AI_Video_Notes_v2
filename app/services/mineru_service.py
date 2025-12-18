import asyncio
import io
import logging
import mimetypes
import os
from typing import List, Optional, Tuple
import zipfile

import httpx
from sqlmodel import Session

from app.core.config import settings
from app.database import engine
from app.models import SystemConfig
from app.services.engine import get_current_api_key

logger = logging.getLogger("uvicorn.error")


class MineruService:
    """MinerU 文档解析服务封装"""

    BASE_URL = "https://mineru.net/api/v4"
    FILE_URL_ENDPOINT = f"{BASE_URL}/file-urls/batch"
    EXTRACT_TASK_ENDPOINT = f"{BASE_URL}/extract/task"
    # RESULT_ENDPOINT = f"{BASE_URL}/extract-results/batch/{{batch_id}}"
    RESULT_ENDPOINT = f"{BASE_URL}/extract-results/batch/{{batch_id}}"

    MAX_FILE_SIZE = 200 * 1024 * 1024  # 200MB
    POLL_INTERVAL_SECONDS = 10
    MAX_POLL_ATTEMPTS = 60  # 最长轮询 10 分钟

    @classmethod
    def _get_model_mode(cls, override: Optional[str] = None) -> str:
        if override:
            return override
        try:
            with Session(engine) as session:
                config = session.get(SystemConfig, "mineru_model_mode")
                if config and config.value:
                    return config.value
        except Exception as exc:  # pragma: no cover - just logging safeguard
            logger.error(f"读取 MinerU 模式配置失败，使用默认值: {exc}")
        return settings.MINERU_MODEL_MODE

    @classmethod
    def _get_token(cls) -> str:
        token = get_current_api_key("mineru_api_token", settings.MINERU_API_TOKEN)
        if not token:
            raise ValueError("未配置 MinerU API Token，请在设置中填写。")
        return token

    @classmethod
    async def parse_document(cls, file_path: str, model_mode: Optional[str] = None) -> Tuple[str, str]:
        """解析本地文档（使用 Batch 自动流程），返回 (markdown, batch_id)"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"附件文件不存在: {file_path}")

        file_size = os.path.getsize(file_path)
        if file_size > cls.MAX_FILE_SIZE:
            raise ValueError("文件超出 200MB 限制，无法上传到 MinerU")

        token = cls._get_token()
        # 注意：Batch 接口不需要 model_mode 参数，它在申请上传 URL 时指定，或者默认处理
        # 如果需要在 batch 中指定 model，需修改 _apply_upload_url 的 payload，但通常默认即可

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        mime_type, _ = mimetypes.guess_type(file_path)
        mime_type = mime_type or "application/octet-stream"

        async with httpx.AsyncClient(timeout=600.0, trust_env=False) as client:
            # 1. 申请上传 URL (这一步会返回 batch_id)
            upload_meta = await cls._apply_upload_url(
                client=client,
                headers=headers,
                file_path=file_path,
                file_size=file_size,
                mime_type=mime_type,
            )

            # 从返回结果中提取关键信息
            upload_url = upload_meta["upload_url"]
            # 注意：这里直接获取 batch_id，而不是后面的 task_id
            # _apply_upload_url 的返回值字典里需要包含 batch_id，我们稍后检查一下 _apply_upload_url
            batch_id = upload_meta.get("batch_id")

            if not batch_id:
                raise RuntimeError("MinerU 申请上传未返回 batch_id")

            # 2. 上传文件
            await cls._upload_file(
                client=client,
                upload_url=upload_url,
                file_path=file_path,
                mime_type=mime_type,
            )

            logger.info(f"✅ 文件上传完成，系统将自动开始解析 (Batch ID: {batch_id})")

            # === [核心修改] 删除了 _create_extract_task 步骤 ===
            # 文档说明：文件上传完成后，系统会自动提交解析任务

            # 3. 轮询结果 (直接查 batch_id)
            markdown = await cls._poll_and_collect_markdown(
                client=client,
                headers=headers,
                batch_id=batch_id,
            )

        return markdown, batch_id

    @classmethod
    async def _apply_upload_url(
            cls,
            client: httpx.AsyncClient,
            headers: dict,
            file_path: str,
            file_size: int,
            mime_type: str,
    ) -> dict:
        filename = os.path.basename(file_path)
        # 构造请求体：告诉 MinerU 我们要传什么文件
        payload = {
            "files": [
                {
                    "name": filename,
                    "file_name": filename,
                    "originalName": filename,
                    "size": file_size,
                    "content_type": mime_type,
                    "contentType": mime_type,
                }
            ],
            # 如果需要指定模型版本（vlm 或 pipeline），可以在这里加
            # "model_version": "vlm"
        }

        logger.info(f"📤 向 MinerU 申请上传地址: {filename}")
        response = await client.post(cls.FILE_URL_ENDPOINT, headers=headers, json=payload)

        resp_json = response.json()
        if response.status_code != 200:
            logger.error(f"MinerU API Error: {response.text}")
            raise RuntimeError(f"申请上传链接失败({response.status_code}): {response.text}")

        data = resp_json.get("data") or {}

        # === [关键点 1] 获取 batch_id ===
        # 批量接口会直接返回一个 batch_id，后续我们直接用它查进度
        batch_id = data.get("batch_id")

        # === [关键点 2] 获取 upload_url ===
        file_urls = data.get("file_urls")
        files = data.get("files") or data.get("items")

        upload_url = None

        # 情况 A: 新版格式 (直接是 URL 字符串列表)
        if file_urls and isinstance(file_urls, list) and len(file_urls) > 0:
            upload_url = file_urls[0]
            logger.info("✅ 识别到 MinerU 新版 file_urls 格式")

        # 情况 B: 旧版格式 (对象列表)
        elif files and isinstance(files, list) and len(files) > 0:
            file_info = files[0]
            upload_url = (
                    file_info.get("upload_url")
                    or file_info.get("uploadUrl")
                    or file_info.get("signedUrl")
                    or file_info.get("put_url")
            )
            logger.info("✅ 识别到 MinerU 旧版 files/items 格式")

        # === 校验 ===
        if not upload_url:
            logger.warning(f"⚠️ MinerU 响应解析失败(缺上传链接)，完整报文: {resp_json}")
            raise RuntimeError(f"MinerU 返回的上传链接为空...")

        if not batch_id:
            logger.warning(f"⚠️ MinerU 响应解析失败(缺 batch_id)，完整报文: {resp_json}")
            raise RuntimeError("MinerU 申请上传未返回 batch_id")

        # 返回包含两者的字典
        return {"upload_url": upload_url, "batch_id": batch_id}

    @classmethod
    async def _upload_file(
            cls,
            client: httpx.AsyncClient,
            upload_url: str,
            file_path: str,
            mime_type: str,
    ) -> None:
        logger.info(f"⬆️  开始上传附件到 MinerU (signed URL)...")

        # === [修改点 1: 删除 Content-Type] ===
        # 原代码: headers = {"Content-Type": mime_type}
        # 修改后: 不设置 Content-Type，让 OSS 签名校验通过
        headers = {}
        # ===================================

        try:
            # === [修改点 2: 保持之前的 bytes 读取方案] ===
            with open(file_path, "rb") as fp:
                file_content = fp.read()

            response = await client.put(upload_url, content=file_content, headers=headers)
            # ===========================================

            if response.status_code not in (200, 201):
                # 增加更详细的错误日志打印，方便排查 XML
                logger.error(f"上传响应报文: {response.text}")
                raise RuntimeError(f"上传文件失败({response.status_code}): {response.text}")
        except Exception as exc:
            logger.error(f"上传附件失败: {exc}")
            raise

    @classmethod
    async def _create_extract_task(
            cls,
            client: httpx.AsyncClient,
            headers: dict,
            resource_url: str,
            model_mode: str,
    ) -> str:
        payload = {
            "url": resource_url,
            "model_version": model_mode or "pipeline",  # 默认 pipeline
            # "is_ocr": True,       # 可选：如果需要更强的 OCR
            # "language": "ch",     # 可选：指定语言
        }
        logger.info(f"🧾 创建 MinerU 解析任务，模式={model_mode}，URL={resource_url[:50]}...")

        response = await client.post(cls.EXTRACT_TASK_ENDPOINT, headers=headers, json=payload)

        # === [DEBUG 修改 START] ===
        resp_json = response.json()

        # 1. 打印完整的响应体，这样我们就能看到 ID 到底藏在哪里，或者有什么错误消息
        logger.info(f"🔍 MinerU 创建任务响应: {resp_json}")

        if response.status_code != 200:
            raise RuntimeError(f"创建 MinerU 任务失败({response.status_code}): {response.text}")

        data = resp_json.get("data")

        # 兼容性处理：如果 data 为空，尝试直接从根节点找，或者 data 就是 None
        if not data:
            data = {}

        # 尝试各种可能的 ID 字段名
        batch_id = (
                data.get("batch_id")
                or data.get("batchId")
                or data.get("id")
                or data.get("task_id")
                # 备用：有时候 ID 可能直接在根节点
                or resp_json.get("batch_id")
                or resp_json.get("data_id")
        )
        # === [DEBUG 修改 END] ===

        if not batch_id:
            # 抛出包含完整响应的错误，方便调试
            raise RuntimeError(f"MinerU 未返回 batch_id。完整响应: {resp_json}")

        return batch_id

    @classmethod
    async def _poll_and_collect_markdown(
            cls,
            client: httpx.AsyncClient,
            headers: dict,
            batch_id: str,
    ) -> str:
        logger.info(f"🔁 等待 MinerU 解析完成，batch_id={batch_id}")
        for attempt in range(1, cls.MAX_POLL_ATTEMPTS + 1):
            response = await client.get(
                cls.RESULT_ENDPOINT.format(batch_id=batch_id), headers=headers
            )
            if response.status_code != 200:
                raise RuntimeError(f"查询 MinerU 结果失败({response.status_code}): {response.text}")

            payload = response.json()
            # logger.info(f"🔍 MinerU 轮询响应详情: {payload}") # 调试完可以注释掉

            data = payload.get("data") or {}

            # === [核心修复: 解包 Batch 响应结构] ===
            # 如果存在 extract_result 列表，说明是 Batch 接口返回的
            # 我们取出第一个文件的状态信息覆盖 data，这样后续逻辑就能读懂了
            extract_result = data.get("extract_result")
            if extract_result and isinstance(extract_result, list) and len(extract_result) > 0:
                data = extract_result[0]
            # ====================================

            status_raw = (
                    data.get("status")
                    or data.get("state")
                    or data.get("task_status")
                    or data.get("taskStatus")
                    or ""
            )
            status = str(status_raw).lower()

            if status in {"success", "succeed", "done", "finished", "completed"}:
                logger.info(f"✅ MinerU 任务成功 (状态: {status})，开始提取 Markdown...")
                markdown = await cls._extract_markdown(client, data)
                if markdown:
                    return markdown
                raise RuntimeError("未能在 MinerU 结果中解析出 Markdown 内容")

            if status in {"failed", "error", "timeout"}:
                err_msg = data.get("err_msg") or "未知错误"
                raise RuntimeError(f"MinerU 任务失败，状态: {status_raw}, 原因: {err_msg}")

            # 只有在还没完成时打印等待日志
            await asyncio.sleep(cls.POLL_INTERVAL_SECONDS)
            logger.info(f"MinerU 解析中... 状态: [{status_raw}] (attempt {attempt}/{cls.MAX_POLL_ATTEMPTS})")

        raise TimeoutError("MinerU 解析超时，请稍后重试")

    @classmethod
    def _contains_result(cls, data: dict) -> bool:
        if not data:
            return False
        for key in ("results", "files", "items", "list"):
            if key in data and data[key]:
                return True
        return False

    @classmethod
    async def _extract_markdown(cls, client: httpx.AsyncClient, data: dict) -> str:
        # 1) 如果 data 本身就包含 markdown 字段
        direct_md = data.get("markdown") or data.get("md")
        if isinstance(direct_md, str) and direct_md.strip():
            return direct_md

        # 2) 收集所有潜在链接
        urls = []

        def collect(obj):
            if isinstance(obj, dict):
                for value in obj.values():
                    collect(value)
            elif isinstance(obj, list):
                for item in obj:
                    collect(item)
            elif isinstance(obj, str) and obj.startswith("http"):
                urls.append(obj)

        collect(data)

        seen = set()
        markdown_chunks: List[str] = []
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            try:
                if url.lower().endswith(('.md', '.markdown')):
                    md_text = await cls._download_text(client, url)
                    if md_text:
                        markdown_chunks.append(md_text)
                elif url.lower().endswith('.zip'):
                    markdown_chunks.extend(await cls._download_markdown_from_zip(client, url))
            except Exception as exc:
                logger.warning(f"下载 MinerU 结果失败 ({url}): {exc}")

        return "\n\n".join(chunk.strip() for chunk in markdown_chunks if chunk.strip())

    @staticmethod
    async def _download_text(client: httpx.AsyncClient, url: str) -> str:
        response = await client.get(url)
        if response.status_code != 200:
            raise RuntimeError(f"下载 Markdown 失败({response.status_code})")
        return response.text

    @staticmethod
    async def _download_markdown_from_zip(client: httpx.AsyncClient, url: str) -> List[str]:
        response = await client.get(url)
        if response.status_code != 200:
            raise RuntimeError(f"下载 MinerU ZIP 失败({response.status_code})")

        results: List[str] = []
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            for name in zf.namelist():
                if name.lower().endswith((".md", ".markdown")):
                    with zf.open(name) as fp:
                        results.append(fp.read().decode("utf-8"))
        return results