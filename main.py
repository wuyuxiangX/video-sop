from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import logging

from api.v1 import router as api_v1_router


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 创建临时目录
os.makedirs("./temp", exist_ok=True)

app = FastAPI(
    title="Video Download Service",
    version="1.0.0",
    description="视频下载服务，支持Bilibili和TikTok"
)

# CORS中间件 - 优化配置以支持国内访问国外服务器
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # 明确指定方法
    allow_headers=["*"],  # 允许所有头部
    expose_headers=["*"],  # 暴露所有响应头
    max_age=3600,  # 预检请求缓存时间
)

# 包含API路由
app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/")
async def root():
    try:
        return {
            "message": "Video Download Service is running",
            "version": "4.0.0",
            "description": "🎯 专注base64编码URL下载，优先Audio Only",
            "features": [
                "✅ 支持base64编码的URL",
                "🎵 优先下载Audio Only格式",
                "📺 支持Bilibili、YouTube、TikTok等平台",
                "⚡ 基于video-downloader的高效架构",
                "🔄 流式下载和传输"
            ],
            "core_endpoints": {
                "video_download": "POST /api/v1/video/download?url=<base64编码或普通URL>",
                "creator_videos": "POST /api/v1/video/creator?url=<base64编码或普通URL>"
            },
            "supported_inputs": {
                "base64编码URL": "自动检测和解码base64编码的视频链接",
                "普通URL": "支持所有平台的完整URL格式"
            },
            "examples": {
                "🎵 base64编码视频下载": "POST /api/v1/video/download?url=aHR0cHM6Ly93d3cueW91dHViZS5jb20vd2F0Y2g/dj1kUXc0dzlXZ1hjUQ==",
                "📺 普通URL下载": "POST /api/v1/video/download?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "🎬 创作者视频列表": "POST /api/v1/video/creator?url=<base64编码的创作者页面URL>"
            },
            "download_priority": {
                "1st": "🎵 Audio Only (最高质量音频)",
                "2nd": "📹 Lowest Quality Video (如果没有纯音频)"
            }
        }
    except Exception as e:
        logger.error(f"Root endpoint error: {e}")
        return {
            "message": "Video Download Service is running (with errors)",
            "version": "4.0.0",
            "status": "error",
            "error": str(e)
        }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=3667,
        timeout_keep_alive=30,  # 保持连接时间
        timeout_graceful_shutdown=60,  # 优雅关闭超时
        limit_concurrency=10,  # 限制并发数
        limit_max_requests=1000  # 限制最大请求数
    )
