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

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 包含API路由
app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/")
async def root():
    try:
        return {
            "message": "Video Download Service is running",
            "version": "1.0.0",
            "note": "精简的API，所有端点均使用POST请求",
            "core_endpoints": {
                "video_info": "POST /api/v1/video/info - 获取视频信息",
                "video_download": "POST /api/v1/video/download - 流式下载视频",
                "creator_videos": "POST /api/v1/video/creator - 获取博主视频列表"
            },
            "test_endpoints": {
                "test_get": "GET /api/v1/video/test?a=value - GET测试端点",
                "test_post": "POST /api/v1/video/test?a=value - POST测试端点", 
                "test2_post": "POST /api/v1/video/test2?a=value - POST测试端点(返回JSON)"
            }
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
