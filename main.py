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
            "version": "3.0.0",
            "description": "🚀 全平台支持！Bilibili、TikTok、YouTube 统一使用 yt-dlp，支持简化输入格式",
            "supported_platforms": {
                "Bilibili": "支持单视频和用户频道，使用 yt-dlp 引擎",
                "TikTok": "支持单视频和用户频道，使用 yt-dlp 引擎", 
                "YouTube": "支持单视频和频道，使用 yt-dlp 引擎"
            },
            "core_endpoints": {
                "video_info": "POST /api/v1/video/info?video_path=<视频路径>",
                "video_download": "POST /api/v1/video/download?video_path=<视频路径>",
                "creator_videos": "POST /api/v1/video/creator?username=<用户名>"
            },
            "supported_formats": {
                "🎵 TikTok": {
                    "用户名": ["@crazydaywithshay", "@username"],
                    "视频": ["@crazydaywithshay/video/7517350403659369759"]
                },
                "📺 YouTube": {
                    "用户名": ["#pewdiepie", "#@pewdiepie", "#username"],
                    "视频": ["#pewdiepie/watch?v=VIDEO_ID", "#@pewdiepie/watch?v=VIDEO_ID"]
                },
                "📹 Bilibili": {
                    "用户名": ["。946974", "。username"],
                    "视频": ["。BV1ccNQzGEZ5"]
                },
                "🌐 完整URL": ["支持所有平台的完整URL格式"],
                "📋 前缀规则": "# = YouTube | @ = TikTok | 。= Bilibili"
            },
            "examples": {
                "🎵 TikTok用户视频": "POST /api/v1/video/creator?username=@crazydaywithshay&max_count=10",
                "📺 YouTube频道视频": "POST /api/v1/video/creator?username=#pewdiepie&max_count=10", 
                "📹 Bilibili用户视频": "POST /api/v1/video/creator?username=。946974&max_count=10",
                "🎵 TikTok视频下载": "POST /api/v1/video/download?video_path=@crazydaywithshay/video/7517350403659369759",
                "📺 YouTube视频下载": "POST /api/v1/video/download?video_path=#pewdiepie/watch?v=VIDEO_ID",
                "📹 Bilibili视频下载": "POST /api/v1/video/download?video_path=。BV1ccNQzGEZ5"
            },
            "note": "🚀 新平台前缀系统：简单明了的符号区分 | # = YouTube | @ = TikTok | 。= Bilibili"
        }
    except Exception as e:
        logger.error(f"Root endpoint error: {e}")
        return {
            "message": "Video Download Service is running (with errors)",
            "version": "1.0.0",
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
