from fastapi import APIRouter
from .endpoints import video, platforms

router = APIRouter()

# 包含所有端点路由
router.include_router(video.router, prefix="/video", tags=["video"])
router.include_router(platforms.router, prefix="/platforms", tags=["platforms"])
