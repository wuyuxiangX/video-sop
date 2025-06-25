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
            "version": "2.0.0",
            "description": "🎉 全新升级！现在支持简化输入格式，无需完整URL",
            "core_endpoints": {
                "video_info": "POST /api/v1/video/info?video_path=@crazydaywithshay/video/7517350403659369759",
                "video_download": "POST /api/v1/video/download?video_path=@crazydaywithshay/video/7517350403659369759",
                "creator_videos": "POST /api/v1/video/creator?username=@crazydaywithshay"
            },
            "supported_formats": {
                "用户名": ["crazydaywithshay", "@crazydaywithshay"],
                "视频路径": ["@crazydaywithshay/video/7517350403659369759", "crazydaywithshay/video/7517350403659369759"],
                "完整URL": ["https://www.tiktok.com/@crazydaywithshay", "https://www.tiktok.com/@crazydaywithshay/video/7517350403659369759"]
            },
            "examples": {
                "获取用户视频列表": "POST /api/v1/video/creator?username=crazydaywithshay&max_count=10",
                "获取视频信息": "POST /api/v1/video/info?video_path=@crazydaywithshay/video/7517350403659369759",
                "下载视频": "POST /api/v1/video/download?video_path=@crazydaywithshay/video/7517350403659369759"
            },
            "note": "✨ 现在可以直接使用用户名，系统会自动转换为完整URL！"
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
        port=8001,
        timeout_keep_alive=30,  # 保持连接时间
        timeout_graceful_shutdown=60,  # 优雅关闭超时
        limit_concurrency=10,  # 限制并发数
        limit_max_requests=1000  # 限制最大请求数
    )
