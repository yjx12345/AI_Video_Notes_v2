📚 AI Video Notes v2 (AI 视频笔记助手)

一个基于 FastAPI + Vue 3 的全栈 AI 笔记助手，支持视频/音频转写、文档解析以及“音视频+课件”多模态融合笔记生成。

✨ 项目简介

AI Video Notes v2 旨在解决网课学习、会议记录整理难的问题。它不仅仅是一个简单的语音转文字工具，更是一个多模态的知识整合系统。

核心功能

🎙️ 音视频转写: 利用 SiliconFlow (SenseVoiceSmall) 模型，将课程视频或会议录音快速转写为文字。

📄 文档智能解析: 集成 MinerU (PDF-Extract-Kit)，支持 PDF/Word/PPT 等课件的高精度 Markdown 还原（支持公式、表格识别）。

🧩 多模态融合: 独有的“融合任务”模式，能将视频转写内容与课件文档自动对齐，由 LLM 生成内容详实、结构清晰的最终笔记。

🤖 AI 润色与总结: 内置 DeepSeek (via CREC API) 模型，支持自定义 Prompt 模板（如：会议纪要、学习笔记、通用总结）。

📝 强大的编辑器: 支持原始文本、润色文本、文档解析结果的对比查看与实时编辑。

🔗 Obsidian 深度集成: 一键将生成的笔记导出到本地 Obsidian 知识库，打通知识管理闭环。

⚡ 自动保存与容错: 内置防抖自动保存机制，后台任务支持断点状态恢复与僵尸任务清理。

🛠️ 技术栈

后端 (Backend)

框架: FastAPI (Python)

数据库: SQLite + SQLModel (SQLAlchemy)

异步处理: Python asyncio + httpx (高并发 API 调用)

多媒体处理: FFmpeg

AI 服务集成:

ASR: SiliconFlow API

LLM: CREC API (DeepSeek-Chat)

OCR/Doc: MinerU / OpenDataLab API

前端 (Frontend)

框架: Vue 3 (Script Setup)

UI 组件库: Element Plus

HTTP 客户端: Axios

工具: Vite

🚀 快速开始

1. 环境准备

确保您的系统已安装：

Python 3.10+

Node.js 16+

FFmpeg (必须安装并添加到系统环境变量 PATH 中，用于音频提取)

2. 后端部署

# 进入后端目录（假设在根目录）
cd backend

# 安装依赖
pip install -r requirements.txt

# 启动服务 (默认端口 1314)
# 注意：生产环境建议使用 nohup 或 supervisor
python main.py


后端服务启动后，会自动初始化 sqlite.db 数据库及相关上传目录。

3. 前端部署

# 进入前端目录
cd frontend

# 安装依赖
npm install

# 开发模式运行
npm run dev

# 或者构建生产环境代码
npm run build


⚙️ 配置说明 (Settings)

项目首次运行后，请点击左下角的 设置 (⚙️) 按钮进行 API 配置：

配置项

说明

获取方式

SiliconFlow Key

用于语音转写 (ASR)

SiliconFlow 官网

CREC Key

用于文本润色与总结 (LLM)

CREC AI 平台

MinerU Token

用于文档解析 (PDF/Doc)

MinerU / OpenDataLab

Obsidian 库路径

本地 Obsidian 仓库的绝对路径

例如 D:\MyNotes

注意: MinerU 解析模式推荐选择 VLM (视觉大模型) 以获得最佳的图表解析效果。

📖 使用指南

1. 新建任务

点击侧边栏“+”号或欢迎页的“新建任务”：

音视频任务: 上传 .mp4, .mp3 等文件，仅进行转写和润色。

文档任务: 上传 .pdf, .docx 等文件，使用 MinerU 解析为 Markdown。

融合任务 (推荐): 同时上传视频和对应的课件。系统将分别处理后，利用 AI 将两者内容融合。

2. 笔记生成

任务处理完成后，进入 “最终笔记” 标签页：

选择一个 模板（如“学习笔记”）。

点击 “AI 生成”。

等待数秒，AI 将根据视频内容和文档内容生成结构化的笔记。

3. 导出

点击 “导出 Obsidian”，笔记将自动保存为 Markdown 文件到您配置的 Obsidian 文件夹中。

❓ 常见问题 (FAQ)

Q: 为什么上传文档时提示 "SignatureDoesNotMatch"？
A: 这是因为 OSS 上传时设置了错误的 Content-Type。最新版本代码已修复此问题，上传时会自动处理签名头。

Q: MinerU 解析一直显示 "Pending"？
A: MinerU 是公共云服务，高峰期需要排队。任务会自动轮询状态，通常耗时 1-5 分钟，请耐心等待。

Q: 点击“复制全文”提示失败？
A: 浏览器的剪贴板 API 出于安全考虑，通常只允许在 https:// 或 localhost 环境下使用。如果通过局域网 IP 访问，最新版本已内置兼容模式，会自动尝试降级方案进行复制。

Q: 任务卡在 "处理中" 很久不动怎么办？
A: 尝试刷新页面。如果状态仍未改变，重启后端服务 (main.py)。系统启动时会自动运行“僵尸任务清理”程序，将异常中断的任务标记为失败，以便您可以重新开始。

📄 许可证

本项目采用 MIT License 开源。